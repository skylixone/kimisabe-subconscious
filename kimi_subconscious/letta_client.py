"""Letta API client for Kimi Subconscious."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

import httpx

from .models import DetectedInsight, LettaMessage, MemoryBlock


class LettaError(Exception):
    """Error from Letta API."""
    pass


class LettaClient:
    """Client for Letta API."""
    
    DEFAULT_BASE_URL = "https://api.letta.com"
    
    def __init__(self, api_key: str | None = None, base_url: str | None = None):
        self.api_key = api_key
        self.base_url = base_url or self.DEFAULT_BASE_URL
        self.client = httpx.Client(
            base_url=f"{self.base_url}/v1",
            headers=self._headers(),
            timeout=60.0,
        )
    
    def _headers(self) -> dict[str, str]:
        """Get request headers."""
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers
    
    def _request(self, method: str, path: str, **kwargs) -> Any:
        """Make an API request."""
        response = self.client.request(method, path, **kwargs)
        
        if response.status_code == 409:
            # Conversation busy - not an error, just need to retry later
            raise LettaError("Conversation busy (409)")
        
        response.raise_for_status()
        
        if response.content:
            return response.json()
        return None
    
    # ============ Agent Management ============
    
    def get_agent(self, agent_id: str) -> dict[str, Any]:
        """Get agent details including memory blocks."""
        return self._request("GET", f"/agents/{agent_id}?include=agent.blocks")
    
    def list_agents(self) -> list[dict[str, Any]]:
        """List all agents."""
        return self._request("GET", "/agents")
    
    def import_agent(self, af_file: Path) -> str:
        """Import an agent from .af file. Returns agent ID."""
        with open(af_file, "rb") as f:
            files = {"file": (af_file.name, f, "application/json")}
            
            # Use multipart/form-data for file upload
            response = self.client.post(
                "/agents/import",
                files=files,
                headers={"Authorization": f"Bearer {self.api_key}"} if self.api_key else {},
            )
            response.raise_for_status()
            result = response.json()
            
        if not result.get("agent_ids"):
            raise LettaError("Import succeeded but no agent ID returned")
            
        return result["agent_ids"][0]
    
    def update_agent_memory(self, agent_id: str, block_label: str, new_value: str) -> None:
        """Update a memory block on the agent."""
        # Get current blocks
        agent = self.get_agent(agent_id)
        blocks = agent.get("blocks", [])
        
        # Find the block
        block_id = None
        for block in blocks:
            if block.get("label") == block_label:
                block_id = block.get("id")
                break
        
        if not block_id:
            raise LettaError(f"Block '{block_label}' not found on agent")
        
        # Update the block
        self._request(
            "PATCH",
            f"/blocks/{block_id}",
            json={"value": new_value},
        )
    
    # ============ Conversation Management ============
    
    def create_conversation(self, agent_id: str) -> str:
        """Create a new conversation for an agent. Returns conversation ID."""
        result = self._request(
            "POST",
            f"/conversations?agent_id={agent_id}",
        )
        return result["id"]
    
    def send_message(
        self,
        conversation_id: str,
        content: str,
        role: str = "user",
        skip_if_busy: bool = True,
    ) -> bool:
        """Send a message to a conversation.
        
        Returns True if sent successfully, False if skipped due to busy.
        """
        try:
            response = self.client.post(
                f"/conversations/{conversation_id}/messages",
                json={"messages": [{"role": role, "content": content}]},
            )
            
            if response.status_code == 409:
                # Conversation busy
                return False
                
            response.raise_for_status()
            
            # Consume the stream minimally (just check it started)
            # The API returns a streaming response
            return True
            
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 409 and skip_if_busy:
                return False
            raise
        except LettaError as e:
            if "busy" in str(e).lower() and skip_if_busy:
                return False
            raise
    
    def get_messages(
        self,
        conversation_id: str,
        limit: int = 50,
        message_type: str | None = None,
    ) -> list[LettaMessage]:
        """Get messages from a conversation."""
        params = {"limit": limit}
        if message_type:
            params["message_type"] = message_type
            
        data = self._request("GET", f"/conversations/{conversation_id}/messages", params=params)
        
        messages = []
        for msg in data:
            try:
                messages.append(LettaMessage(
                    id=msg.get("id", ""),
                    role=msg.get("role", ""),
                    content=msg.get("content") or msg.get("text", ""),
                    created_at=None,  # Parse if available
                ))
            except Exception:
                continue
                
        return messages
    
    def get_assistant_messages(
        self,
        conversation_id: str,
        since_message_id: str | None = None,
        limit: int = 50,
    ) -> tuple[list[LettaMessage], str | None]:
        """Get new assistant messages since a specific message ID.
        
        Returns (messages, newest_message_id).
        """
        all_messages = self.get_messages(
            conversation_id,
            limit=limit * 2,  # Get more to ensure we have what we need
        )
        
        # Filter to assistant messages
        assistant_msgs = [m for m in all_messages if m.role == "assistant"]
        
        if not assistant_msgs:
            return [], since_message_id
        
        # Find index of last seen message
        if since_message_id:
            try:
                # Messages are returned newest first
                seen_idx = next(
                    i for i, m in enumerate(assistant_msgs) if m.id == since_message_id
                )
                # Return messages newer than seen (indices before seen_idx)
                new_msgs = assistant_msgs[:seen_idx]
            except StopIteration:
                # Message ID not found, return all
                new_msgs = assistant_msgs
        else:
            new_msgs = assistant_msgs
        
        newest_id = assistant_msgs[0].id if assistant_msgs else since_message_id
        return new_msgs, newest_id
    
    # ============ Model Management ============
    
    def list_models(self) -> list[dict[str, Any]]:
        """List available models on the server."""
        return self._request("GET", "/models/")
    
    def update_agent_model(self, agent_id: str, model_handle: str) -> None:
        """Update the model for an agent."""
        models = self.list_models()
        
        # Find the model
        model_info = None
        for m in models:
            handle = m.get("handle") or f"{m.get('provider_type')}/{m.get('model')}"
            if handle == model_handle:
                model_info = m
                break
        
        if not model_info:
            raise LettaError(f"Model '{model_handle}' not available on server")
        
        # Build llm_config
        slash_idx = model_handle.index("/")
        provider = model_handle[:slash_idx]
        model = model_handle[slash_idx + 1:]
        
        llm_config = {
            "model": model,
            "handle": model_handle,
            "provider_name": provider,
            "model_endpoint_type": model_info.get("provider_type"),
        }
        
        self._request("PATCH", f"/agents/{agent_id}", json={"llm_config": llm_config})


class SubconsciousAgent:
    """High-level interface to the Subconscious Letta agent."""
    
    # Preferred models in order
    PREFERRED_MODELS = [
        "anthropic/claude-sonnet-4-5",
        "openai/gpt-4.1-mini",
        "anthropic/claude-haiku-4-5",
        "openai/gpt-5.2",
        "google_ai/gemini-3-flash",
        "google_ai/gemini-2.5-flash",
    ]
    
    def __init__(self, client: LettaClient, agent_id: str | None = None):
        self.client = client
        self.agent_id = agent_id
        self._agent_data: dict | None = None
    
    def resolve_agent(self, config_path: Path | None = None) -> str:
        """Resolve agent ID from config or create new one."""
        # TODO: Implement config-based resolution
        if self.agent_id:
            return self.agent_id
        raise LettaError("No agent ID configured")
    
    def import_default_agent(self, af_path: Path) -> str:
        """Import the default Subconscious agent."""
        self.agent_id = self.client.import_agent(af_path)
        return self.agent_id
    
    def ensure_model_available(self) -> str | None:
        """Ensure the agent's model is available, auto-select if not.
        
        Returns the model that was selected, or None if no change.
        """
        if not self.agent_id:
            raise LettaError("No agent ID")
        
        agent = self.client.get_agent(self.agent_id)
        current_model = self._get_model_handle(agent)
        
        models = self.client.list_models()
        available_handles = [
            m.get("handle") or f"{m.get('provider_type')}/{m.get('model')}"
            for m in models
        ]
        
        # Check if current model is available
        if current_model and current_model in available_handles:
            return None
        
        # Select best available model
        selected = None
        for preferred in self.PREFERRED_MODELS:
            if preferred in available_handles:
                selected = preferred
                break
        
        if not selected and available_handles:
            selected = available_handles[0]
        
        if selected:
            self.client.update_agent_model(self.agent_id, selected)
            return selected
        
        raise LettaError("No models available on server")
    
    def get_memory_blocks(self) -> list[MemoryBlock]:
        """Get all memory blocks from the agent."""
        if not self.agent_id:
            raise LettaError("No agent ID")
        
        agent = self.client.get_agent(self.agent_id)
        blocks = agent.get("blocks", [])
        
        return [
            MemoryBlock(
                label=b.get("label", ""),
                value=b.get("value", ""),
                description=b.get("description"),
                limit=b.get("limit", 20000),
            )
            for b in blocks
        ]
    
    def get_block(self, label: str) -> MemoryBlock | None:
        """Get a specific memory block by label."""
        for block in self.get_memory_blocks():
            if block.label == label:
                return block
        return None
    
    def update_block(self, label: str, new_value: str) -> None:
        """Update a memory block."""
        if not self.agent_id:
            raise LettaError("No agent ID")
        self.client.update_agent_memory(self.agent_id, label, new_value)
    
    def send_session_update(
        self,
        conversation_id: str,
        content: str,
        insights: list[DetectedInsight] | None = None,
    ) -> bool:
        """Send a session update to the agent."""
        return self.client.send_message(conversation_id, content)
    
    def get_new_guidance(
        self,
        conversation_id: str,
        since_message_id: str | None = None,
    ) -> tuple[list[str], str | None]:
        """Get new guidance messages from the agent.
        
        Returns (list of guidance texts, newest_message_id).
        """
        messages, newest_id = self.client.get_assistant_messages(
            conversation_id,
            since_message_id=since_message_id,
        )
        
        guidance = [m.content for m in messages if m.content]
        return guidance, newest_id
    
    def _get_model_handle(self, agent: dict) -> str | None:
        """Extract model handle from agent data."""
        llm_config = agent.get("llm_config", {})
        
        if llm_config.get("handle"):
            return llm_config["handle"]
        
        if llm_config.get("provider_name") and llm_config.get("model"):
            return f"{llm_config['provider_name']}/{llm_config['model']}"
        
        return llm_config.get("model")
