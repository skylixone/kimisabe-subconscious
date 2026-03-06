"""Pydantic models for Kimi Subconscious."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field


class WireMessageType(str, Enum):
    """Types of messages in wire.jsonl."""
    
    METADATA = "metadata"
    TURN_BEGIN = "TurnBegin"
    STEP_BEGIN = "StepBegin"
    CONTENT_PART = "ContentPart"
    TOOL_CALL = "ToolCall"
    TOOL_RESULT = "ToolResult"
    STEP_END = "StepEnd"
    TURN_END = "TurnEnd"


class ContentType(str, Enum):
    """Types of content parts."""
    
    TEXT = "text"
    THINK = "think"
    TOOL_CALL = "tool_call"
    TOOL_RESULT = "tool_result"


class UserInput(BaseModel):
    """User input in a TurnBegin message."""
    
    type: str
    text: str | None = None


class TurnBeginPayload(BaseModel):
    """Payload for TurnBegin message."""
    
    user_input: list[UserInput]


class ContentPartPayload(BaseModel):
    """Payload for ContentPart message."""
    
    type: str
    text: str | None = None
    think: str | None = None
    tool_call: dict[str, Any] | None = None
    tool_result: dict[str, Any] | None = None
    encrypted: str | None = None


class ToolCallPayload(BaseModel):
    """Payload for ToolCall message."""
    
    type: str | None = None
    id: str | None = None
    tool_call_id: str | None = None  # Alternative field
    function: dict[str, Any] | None = None
    name: str | None = None  # Alternative field
    arguments: dict[str, Any] | None = None  # Alternative field
    extras: dict[str, Any] | None = None
    
    def get_id(self) -> str:
        """Get the tool call ID."""
        return self.id or self.tool_call_id or "unknown"
    
    def get_name(self) -> str:
        """Get the function name."""
        if self.function and isinstance(self.function, dict):
            return self.function.get("name", "unknown")
        return self.name or "unknown"
    
    def get_arguments(self) -> dict[str, Any]:
        """Get the function arguments."""
        if self.function and isinstance(self.function, dict):
            args = self.function.get("arguments")
            if isinstance(args, str):
                import json
                try:
                    return json.loads(args)
                except json.JSONDecodeError:
                    return {}
            return args or {}
        return self.arguments or {}


class ToolResultPayload(BaseModel):
    """Payload for ToolResult message."""
    
    type: str | None = None
    tool_use_id: str | None = Field(default=None, alias="tool_call_id")
    tool_call_id: str | None = None  # Alternative field name
    content: str | dict[str, Any] | None = None
    is_error: bool = False
    return_value: dict[str, Any] | None = None  # Kimi's format
    
    def get_tool_id(self) -> str:
        """Get the tool ID, handling different field names."""
        return self.tool_use_id or self.tool_call_id or "unknown"
    
    def get_is_error(self) -> bool:
        """Check if this is an error, handling Kimi's format."""
        if self.is_error:
            return True
        if self.return_value and isinstance(self.return_value, dict):
            return self.return_value.get("is_error", False)
        return False


class WireMessage(BaseModel):
    """A single message from wire.jsonl."""
    
    timestamp: float
    message: dict[str, Any]
    
    @property
    def msg_type(self) -> str | None:
        """Get the message type."""
        return self.message.get("type")
    
    @property
    def datetime(self) -> datetime:
        """Get timestamp as datetime."""
        return datetime.fromtimestamp(self.timestamp)


class ConversationTurn(BaseModel):
    """A single turn in the conversation (user input + assistant response)."""
    
    turn_number: int
    timestamp: datetime
    user_input: str
    assistant_thinking: list[str] = Field(default_factory=list)
    assistant_response: list[str] = Field(default_factory=list)
    tool_calls: list[dict] = Field(default_factory=list)
    tool_results: list[dict] = Field(default_factory=list)
    has_errors: bool = False


class SessionInfo(BaseModel):
    """Information about a Kimi session."""
    
    project_hash: str
    session_id: str
    project_path: Path | None = None
    wire_path: Path | None = None
    state_path: Path | None = None
    
    @property
    def is_active(self) -> bool:
        """Check if session is still active (wire.jsonl exists and is being written)."""
        if not self.wire_path:
            return False
        return self.wire_path.exists()


class InsightType(str, Enum):
    """Types of insights that can be detected."""
    
    EXPLICIT_MEMORY = "explicit_memory_request"
    CORRECTION = "correction_detected"
    REPEATED_ERRORS = "repeated_errors"
    FILE_HOTSPOT = "file_hotspot"
    LONG_SESSION = "long_session"
    BREAKTHROUGH = "breakthrough_detected"
    DAILY_CONSOLIDATION = "daily_consolidation"


class DetectedInsight(BaseModel):
    """An insight detected from conversation."""
    
    type: InsightType
    confidence: float = Field(ge=0.0, le=1.0)
    description: str
    messages: list[int] = Field(default_factory=list)  # Indices of relevant messages
    extracted_data: dict[str, Any] = Field(default_factory=dict)


class MemoryBlock(BaseModel):
    """A memory block from Letta."""
    
    label: str
    value: str
    description: str | None = None
    limit: int = 20000


class LettaMessage(BaseModel):
    """A message from Letta agent."""
    
    id: str
    role: str
    content: str
    created_at: datetime | None = None
