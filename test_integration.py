#!/usr/bin/env python3
"""Integration tests for Kimi Subconscious insight→block flow.

These tests verify the end-to-end flow from insight detection to memory block updates.

Usage:
    python test_integration.py <test_name>

Tests:
    agent_config         - Verify agent is correctly configured with Subconscious.af blocks
    block_read           - Test reading memory blocks from Letta
    insight_format       - Test insight formatting for Letta messages
    message_send         - Test sending messages to Letta conversation
    full_flow            - Test full flow: detect → send → verify receipt
    all                  - Run all tests
"""

from __future__ import annotations

import sys
import time
from datetime import datetime, timezone
from pathlib import Path

# Add package to path
sys.path.insert(0, str(Path(__file__).parent))

from kimi_subconscious.letta_client import LettaClient, SubconsciousAgent
from kimi_subconscious.models import ConversationTurn, DetectedInsight, InsightType
from kimi_subconscious.parser import format_for_letta
from kimi_subconscious.state import StateManager


class Colors:
    GREEN = "\033[92m"
    RED = "\033[91m"
    YELLOW = "\033[93m"
    RESET = "\033[0m"


def log_pass(msg: str) -> None:
    print(f"{Colors.GREEN}✓ PASS:{Colors.RESET} {msg}")


def log_fail(msg: str) -> None:
    print(f"{Colors.RED}✗ FAIL:{Colors.RESET} {msg}")


def log_info(msg: str) -> None:
    print(f"  {msg}")


def get_test_agent() -> tuple[SubconsciousAgent, StateManager, LettaClient]:
    """Get configured agent for testing."""
    state = StateManager()
    client = LettaClient(api_key=state.get_api_key(), base_url=state.get_letta_base_url())
    agent = SubconsciousAgent(client, agent_id=state.get_agent_id())
    return agent, state, client


def test_agent_config():
    """TEST 1: Verify agent is correctly configured with Subconscious.af blocks.
    
    Checks:
        - Agent has exactly 8 blocks
        - All expected blocks exist (core_directives, guidance, etc.)
        - Block content is populated for template blocks
    """
    print("=" * 60)
    print("TEST 1: Agent Configuration")
    print("=" * 60)
    
    try:
        agent, state, client = get_test_agent()
        agent_id = state.get_agent_id()
        
        log_info(f"Agent ID: {agent_id}")
        
        # Get raw agent data
        agent_data = client.get_agent(agent_id)
        log_info(f"Agent name: {agent_data.get('name', 'N/A')}")
        
        # Get blocks
        blocks = agent.get_memory_blocks()
        log_info(f"Number of blocks: {len(blocks)}")
        
        # Expected blocks
        expected_blocks = {
            "core_directives",
            "guidance",
            "pending_items",
            "project_context",
            "self_improvement",
            "session_patterns",
            "tool_guidelines",
            "user_preferences",
        }
        
        actual_blocks = {b.label for b in blocks}
        
        # Check count
        if len(blocks) != 8:
            log_fail(f"Expected 8 blocks, got {len(blocks)}")
            return False
        log_pass(f"Agent has exactly 8 blocks")
        
        # Check expected blocks exist
        missing = expected_blocks - actual_blocks
        if missing:
            log_fail(f"Missing blocks: {missing}")
            return False
        log_pass(f"All expected blocks present")
        
        # Check core blocks are populated (not just templates)
        core_directives = agent.get_block("core_directives")
        if not core_directives or len(core_directives.value) < 1000:
            log_fail(f"core_directives block appears empty or too small")
            return False
        log_pass(f"core_directives populated ({len(core_directives.value)} chars)")
        
        tool_guidelines = agent.get_block("tool_guidelines")
        if not tool_guidelines or len(tool_guidelines.value) < 1000:
            log_fail(f"tool_guidelines block appears empty or too small")
            return False
        log_pass(f"tool_guidelines populated ({len(tool_guidelines.value)} chars)")
        
        # Check guidance block exists (even if template)
        guidance = agent.get_block("guidance")
        if not guidance:
            log_fail("guidance block not found")
            return False
        log_pass(f"guidance block exists ({len(guidance.value)} chars)")
        
        print()
        return True
        
    except Exception as e:
        log_fail(f"Exception: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_block_read():
    """TEST 2: Test reading memory blocks from Letta.
    
    Verifies the SubconsciousAgent.get_memory_blocks() and get_block() methods
    work correctly with the configured agent.
    """
    print("=" * 60)
    print("TEST 2: Block Reading")
    print("=" * 60)
    
    try:
        agent, state, _ = get_test_agent()
        
        # Test get_memory_blocks
        log_info("Fetching all memory blocks...")
        blocks = agent.get_memory_blocks()
        
        if not blocks:
            log_fail("No blocks returned")
            return False
        log_pass(f"Retrieved {len(blocks)} blocks")
        
        # Test get_block for each
        for block_label in ["core_directives", "guidance", "user_preferences"]:
            log_info(f"Fetching individual block: {block_label}")
            block = agent.get_block(block_label)
            if not block:
                log_fail(f"Could not retrieve block: {block_label}")
                return False
            if block.label != block_label:
                log_fail(f"Block label mismatch: expected {block_label}, got {block.label}")
                return False
        log_pass("Individual block retrieval works for all tested blocks")
        
        # Test non-existent block
        log_info("Testing non-existent block lookup...")
        nonexistent = agent.get_block("nonexistent_block_xyz")
        if nonexistent is not None:
            log_fail("Should return None for non-existent block")
            return False
        log_pass("Non-existent block returns None")
        
        print()
        return True
        
    except Exception as e:
        log_fail(f"Exception: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_insight_format():
    """TEST 3: Test insight formatting for Letta messages.
    
    Verifies that insights are correctly formatted into the XML structure
    expected by the Subconscious agent.
    """
    print("=" * 60)
    print("TEST 3: Insight Formatting")
    print("=" * 60)
    
    try:
        # Create test insights
        insights = [
            DetectedInsight(
                type=InsightType.CORRECTION,
                confidence=0.9,
                description="User prefers laconic communication",
                source_turn=1,
            ),
            DetectedInsight(
                type=InsightType.BREAKTHROUGH,
                confidence=0.85,
                description="Found root cause of agent mismatch bug",
                source_turn=2,
            ),
            DetectedInsight(
                type=InsightType.EXPLICIT_MEMORY,
                confidence=1.0,
                description="Always use uppercase with letter-spacing",
                source_turn=3,
            ),
        ]
        
        # Create mock ConversationTurn objects
        now = datetime.now(timezone.utc)
        mock_turns = [
            ConversationTurn(
                turn_number=1,
                timestamp=now,
                user_input="Make this shorter",
                assistant_response=["Here's a detailed explanation..."],
                assistant_thinking=[],
                tool_calls=[],
                tool_results=[],
            ),
            ConversationTurn(
                turn_number=2,
                timestamp=now,
                user_input="Why aren't memory blocks updating?",
                assistant_response=["Let me investigate..."],
                assistant_thinking=[],
                tool_calls=[],
                tool_results=[],
            ),
        ]
        
        log_info("Formatting insights for Letta...")
        formatted = format_for_letta(mock_turns, insights)
        
        # Check structure
        if "<kimi_session_update>" not in formatted:
            log_fail("Missing <kimi_session_update> root element")
            return False
        log_pass("Contains <kimi_session_update> root element")
        
        if "<transcript>" not in formatted:
            log_fail("Missing <transcript> section")
            return False
        log_pass("Contains <transcript> section")
        
        if "<detected_insights>" not in formatted or "</detected_insights>" not in formatted:
            log_fail("Missing <detected_insights> section")
            return False
        log_pass("Contains <detected_insights> section")
        
        if "correction_detected" not in formatted:
            log_fail("Missing correction_detected insight type")
            return False
        log_pass("Contains correction_detected insight")
        
        if "breakthrough_detected" not in formatted:
            log_fail("Missing breakthrough_detected insight type")
            return False
        log_pass("Contains breakthrough_detected insight")
        
        if "User prefers laconic communication" not in formatted:
            log_fail("Missing insight description")
            return False
        log_pass("Contains insight descriptions")
        
        # Check content size
        if len(formatted) < 200:
            log_fail(f"Formatted content suspiciously short: {len(formatted)} chars")
            return False
        log_pass(f"Formatted content length: {len(formatted)} chars")
        
        print()
        return True
        
    except Exception as e:
        log_fail(f"Exception: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_message_send():
    """TEST 4: Test sending messages to Letta conversation.
    
    Creates a conversation, sends a test message, and verifies it was received.
    """
    print("=" * 60)
    print("TEST 4: Message Send/Receive")
    print("=" * 60)
    
    try:
        agent, state, client = get_test_agent()
        agent_id = state.get_agent_id()
        
        # Create conversation
        log_info("Creating test conversation...")
        conversation_id = client.create_conversation(agent_id)
        log_info(f"Conversation ID: {conversation_id}")
        log_pass("Conversation created")
        
        # Send test message
        test_content = f"""<kimi_session>
<timestamp>{datetime.now().isoformat()}</timestamp>
<test_message>
This is a test message from the integration test suite.
Purpose: Verify message sending works correctly.
</test_message>
</kimi_session>"""
        
        log_info("Sending test message...")
        success = client.send_message(conversation_id, test_content)
        
        if not success:
            log_fail("Failed to send message (conversation busy or error)")
            return False
        log_pass("Message sent successfully")
        
        # Wait for processing
        log_info("Waiting for agent processing...")
        time.sleep(5)
        
        # Verify message appears in conversation
        log_info("Retrieving conversation messages...")
        messages = client.get_messages(conversation_id, limit=10)
        
        if not messages:
            log_fail("No messages found in conversation")
            return False
        log_pass(f"Found {len(messages)} messages in conversation")
        
        # Check messages exist
        if not messages:
            log_fail("No messages retrieved")
            return False
        log_info(f"Message roles found: {set(m.role for m in messages)}")
        log_pass(f"Found {len(messages)} total messages")
        
        print()
        return True
        
    except Exception as e:
        log_fail(f"Exception: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_full_flow():
    """TEST 5: Test full flow from insight to agent processing.
    
    This test simulates what the daemon does:
    1. Format insights as message
    2. Send to Letta
    3. Wait for processing
    4. Check for guidance response
    """
    print("=" * 60)
    print("TEST 5: Full Insight→Block Flow")
    print("=" * 60)
    
    try:
        agent, state, client = get_test_agent()
        agent_id = state.get_agent_id()
        
        # Create conversation
        log_info("Creating conversation...")
        conversation_id = client.create_conversation(agent_id)
        log_info(f"Conversation ID: {conversation_id}")
        
        # Create test insight message
        insights = [
            DetectedInsight(
                type=InsightType.EXPLICIT_MEMORY,
                confidence=1.0,
                description="Integration test: User wants tests for insight flow",
                source_turn=1,
            ),
        ]
        
        mock_turns = [
            ConversationTurn(
                turn_number=1,
                timestamp=datetime.now(timezone.utc),
                user_input="Create tests for the subconscious system",
                assistant_response=["I'll design comprehensive tests..."],
                assistant_thinking=[],
                tool_calls=[],
                tool_results=[],
            ),
        ]
        
        formatted = format_for_letta(mock_turns, insights)
        
        # Send message
        log_info("Sending insight message to agent...")
        success = client.send_message(conversation_id, formatted)
        
        if not success:
            log_fail("Failed to send insight message")
            return False
        log_pass("Insight message sent")
        
        # Wait for agent processing
        log_info("Waiting for agent processing (10s)...")
        time.sleep(10)
        
        # Check for response
        log_info("Checking for agent response...")
        messages, newest_id = agent.get_new_guidance(conversation_id)
        
        if messages:
            log_pass(f"Agent responded with {len(messages)} message(s)")
            for i, msg in enumerate(messages[:2], 1):
                preview = msg[:100].replace('\n', ' ') if msg else "(empty)"
                log_info(f"  Response {i}: {preview}...")
        else:
            log_info("No response yet (this is OK - agent may not always respond)")
        
        # Check that blocks can still be read
        log_info("Verifying block access still works...")
        blocks = agent.get_memory_blocks()
        if len(blocks) != 8:
            log_fail(f"Block count changed: expected 8, got {len(blocks)}")
            return False
        log_pass("All 8 blocks accessible after message send")
        
        print()
        return True
        
    except Exception as e:
        log_fail(f"Exception: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        print("\nAvailable tests:")
        print("  agent_config    - Verify agent configuration")
        print("  block_read      - Test reading memory blocks")
        print("  insight_format  - Test insight formatting")
        print("  message_send    - Test message sending")
        print("  full_flow       - Test complete insight→block flow")
        print("  all             - Run all tests")
        sys.exit(1)
    
    test_name = sys.argv[1]
    
    tests = {
        "agent_config": test_agent_config,
        "block_read": test_block_read,
        "insight_format": test_insight_format,
        "message_send": test_message_send,
        "full_flow": test_full_flow,
    }
    
    if test_name == "all":
        results = {}
        for name, func in tests.items():
            results[name] = func()
            print("\n" + "=" * 60 + "\n")
            time.sleep(1)
        
        print("=" * 60)
        print("SUMMARY")
        print("=" * 60)
        all_pass = True
        for name, result in results.items():
            status = f"{Colors.GREEN}✓ PASS{Colors.RESET}" if result else f"{Colors.RED}✗ FAIL{Colors.RESET}"
            print(f"{status}: {name}")
            if not result:
                all_pass = False
        
        sys.exit(0 if all_pass else 1)
    
    elif test_name in tests:
        result = tests[test_name]()
        sys.exit(0 if result else 1)
    
    else:
        print(f"Unknown test: {test_name}")
        sys.exit(1)


if __name__ == "__main__":
    main()
