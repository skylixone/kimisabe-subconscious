"""Parser for Kimi's wire.jsonl format."""

from __future__ import annotations

import json
import re
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any

from .models import (
    ContentPartPayload,
    ConversationTurn,
    DetectedInsight,
    InsightType,
    ToolCallPayload,
    ToolResultPayload,
    TurnBeginPayload,
    WireMessage,
)


class WireParser:
    """Parser for Kimi's wire.jsonl format."""
    
    def __init__(self, wire_path: Path):
        self.wire_path = wire_path
        self.messages: list[WireMessage] = []
        self.turns: list[ConversationTurn] = []
        self._file_offset = 0
        
    def parse_all(self) -> list[WireMessage]:
        """Parse all messages from wire.jsonl."""
        self.messages = []
        
        if not self.wire_path.exists():
            return self.messages
            
        with open(self.wire_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    data = json.loads(line)
                    # Skip metadata line
                    if data.get("type") == "metadata":
                        continue
                    msg = WireMessage(**data)
                    self.messages.append(msg)
                except (json.JSONDecodeError, TypeError, Exception):
                    continue
                    
        return self.messages
    
    def parse_new(self, last_offset: int = 0) -> tuple[list[WireMessage], int]:
        """Parse only new messages since last_offset. Returns (messages, new_offset)."""
        new_messages = []
        
        if not self.wire_path.exists():
            return new_messages, 0
            
        with open(self.wire_path, "r", encoding="utf-8") as f:
            f.seek(last_offset)
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    data = json.loads(line)
                    # Skip metadata line (first line in wire.jsonl)
                    if data.get("type") == "metadata":
                        continue
                    msg = WireMessage(**data)
                    new_messages.append(msg)
                except (json.JSONDecodeError, TypeError, Exception):
                    # Skip malformed lines
                    continue
            new_offset = f.tell()
                    
        self.messages.extend(new_messages)
        return new_messages, new_offset
    
    def build_turns(self) -> list[ConversationTurn]:
        """Build conversation turns from messages."""
        self.turns = []
        current_turn: ConversationTurn | None = None
        turn_number = 0
        
        for msg in self.messages:
            msg_type = msg.msg_type
            
            if msg_type == "TurnBegin":
                turn_number += 1
                payload = TurnBeginPayload(**msg.message.get("payload", {}))
                user_input = " ".join(
                    inp.text or "" for inp in payload.user_input if inp.type == "text"
                )
                
                current_turn = ConversationTurn(
                    turn_number=turn_number,
                    timestamp=msg.datetime,
                    user_input=user_input,
                )
                
            elif msg_type == "ContentPart" and current_turn:
                payload = ContentPartPayload(**msg.message.get("payload", {}))
                
                if payload.type == "think" and payload.think:
                    current_turn.assistant_thinking.append(payload.think)
                elif payload.type == "text" and payload.text:
                    current_turn.assistant_response.append(payload.text)
                    
            elif msg_type == "ToolCall" and current_turn:
                try:
                    payload = ToolCallPayload(**msg.message.get("payload", {}))
                    current_turn.tool_calls.append({
                        "id": payload.get_id(),
                        "name": payload.get_name(),
                        "arguments": payload.get_arguments(),
                    })
                except Exception:
                    # Skip malformed tool calls
                    pass
                
            elif msg_type == "ToolResult" and current_turn:
                try:
                    payload = ToolResultPayload(**msg.message.get("payload", {}))
                    current_turn.tool_results.append({
                        "tool_use_id": payload.get_tool_id(),
                        "content": payload.content or payload.return_value,
                        "is_error": payload.get_is_error(),
                    })
                    if payload.get_is_error():
                        current_turn.has_errors = True
                except Exception:
                    # Skip malformed tool results
                    pass
                    
            elif msg_type == "TurnEnd" and current_turn:
                self.turns.append(current_turn)
                current_turn = None
                
        # Add incomplete turn if session is still active
        if current_turn:
            self.turns.append(current_turn)
            
        return self.turns


class InsightDetector:
    """Detects insights worth sending to Letta."""
    
    # Keywords that trigger insights
    EXPLICIT_MEMORY_KEYWORDS = [
        "remember", "don't forget", "note that", "important",
        "keep in mind", "make sure to", "always", "never",
    ]
    
    CORRECTION_KEYWORDS = [
        "no,", "wrong", "actually", "not quite", "incorrect",
        "that's not", "you misunderstood", "i meant", "i said",
    ]
    
    BREAKTHROUGH_KEYWORDS = [
        "finally", "works!", "figured it out", "solved it",
        "got it working", "that did it", "perfect!", "exactly",
    ]
    
    def __init__(self, turns: list[ConversationTurn]):
        self.turns = turns
        
    def detect_insights(self, new_turns_only: list[ConversationTurn] | None = None) -> list[DetectedInsight]:
        """Detect insights from conversation turns."""
        insights = []
        turns_to_analyze = new_turns_only or self.turns
        
        for insight in [
            self._detect_explicit_memory(turns_to_analyze),
            self._detect_corrections(turns_to_analyze),
            self._detect_repeated_errors(turns_to_analyze),
            self._detect_file_hotspots(turns_to_analyze),
            self._detect_breakthrough(turns_to_analyze),
        ]:
            if insight:
                insights.append(insight)
                
        return insights
    
    def _detect_explicit_memory(self, turns: list[ConversationTurn]) -> DetectedInsight | None:
        """Detect explicit requests to remember something."""
        for i, turn in enumerate(turns):
            user_lower = turn.user_input.lower()
            
            for keyword in self.EXPLICIT_MEMORY_KEYWORDS:
                if keyword in user_lower:
                    return DetectedInsight(
                        type=InsightType.EXPLICIT_MEMORY,
                        confidence=0.9,
                        description=f"Explicit memory request: '{keyword}'",
                        messages=[i],
                        extracted_data={"keyword": keyword, "context": turn.user_input},
                    )
        return None
    
    def _detect_corrections(self, turns: list[ConversationTurn]) -> DetectedInsight | None:
        """Detect user corrections."""
        corrections = []
        
        for i, turn in enumerate(turns):
            user_lower = turn.user_input.lower()
            
            for keyword in self.CORRECTION_KEYWORDS:
                if keyword in user_lower:
                    corrections.append((i, keyword, turn.user_input))
                    
        if len(corrections) >= 2:
            # Multiple corrections in this batch - strong signal
            return DetectedInsight(
                type=InsightType.CORRECTION,
                confidence=min(0.5 + len(corrections) * 0.15, 0.9),
                description=f"Multiple corrections detected ({len(corrections)})",
                messages=[c[0] for c in corrections],
                extracted_data={"corrections": corrections},
            )
        elif len(corrections) == 1:
            return DetectedInsight(
                type=InsightType.CORRECTION,
                confidence=0.6,
                description=f"Correction: '{corrections[0][1]}'",
                messages=[corrections[0][0]],
                extracted_data={"correction": corrections[0]},
            )
        return None
    
    def _detect_repeated_errors(self, turns: list[ConversationTurn]) -> DetectedInsight | None:
        """Detect repeated tool errors."""
        error_count = 0
        error_messages = []
        
        for i, turn in enumerate(turns):
            if turn.has_errors:
                error_count += 1
                # Get the error details
                errors = [r for r in turn.tool_results if r.get("is_error")]
                for err in errors:
                    error_messages.append({
                        "turn": i,
                        "tool": err.get("tool_use_id"),
                        "content": str(err.get("content", ""))[:200],
                    })
                    
        if error_count >= 3:
            return DetectedInsight(
                type=InsightType.REPEATED_ERRORS,
                confidence=min(0.6 + error_count * 0.1, 0.95),
                description=f"Repeated errors ({error_count} turns with errors)",
                messages=list(range(len(turns))),
                extracted_data={"error_count": error_count, "errors": error_messages},
            )
        return None
    
    def _detect_file_hotspots(self, turns: list[ConversationTurn]) -> DetectedInsight | None:
        """Detect files being edited repeatedly."""
        file_counts: dict[str, int] = defaultdict(int)
        file_operations: dict[str, list[dict]] = defaultdict(list)
        
        for i, turn in enumerate(turns):
            for tool_call in turn.tool_calls:
                name = tool_call.get("name", "")
                args = tool_call.get("arguments", {})
                
                if name in ("ReadFile", "WriteFile", "StrReplaceFile", "Edit"):
                    if isinstance(args, dict):
                        file_path = args.get("path") or args.get("file_path")
                        if file_path:
                            file_counts[file_path] += 1
                            file_operations[file_path].append({
                                "turn": i,
                                "tool": name,
                                "timestamp": turn.timestamp.isoformat(),
                            })
                            
        # Find hotspots
        hotspots = [(f, c) for f, c in file_counts.items() if c >= 3]
        
        if hotspots:
            hotspots.sort(key=lambda x: x[1], reverse=True)
            top_file, top_count = hotspots[0]
            
            return DetectedInsight(
                type=InsightType.FILE_HOTSPOT,
                confidence=min(0.5 + top_count * 0.1, 0.9),
                description=f"File hotspot: {top_file} ({top_count} operations)",
                messages=[],
                extracted_data={
                    "hotspots": hotspots,
                    "operations": {f: file_operations[f] for f, _ in hotspots},
                },
            )
        return None
    
    def _detect_breakthrough(self, turns: list[ConversationTurn]) -> DetectedInsight | None:
        """Detect breakthrough moments."""
        for i, turn in enumerate(turns):
            user_lower = turn.user_input.lower()
            
            for keyword in self.BREAKTHROUGH_KEYWORDS:
                if keyword in user_lower:
                    return DetectedInsight(
                        type=InsightType.BREAKTHROUGH,
                        confidence=0.8,
                        description=f"Breakthrough: '{keyword}'",
                        messages=[i],
                        extracted_data={
                            "keyword": keyword,
                            "user_message": turn.user_input,
                            "assistant_response": " ".join(turn.assistant_response),
                        },
                    )
        return None
    
    def check_long_session(self, session_start: datetime, session_end: datetime | None = None) -> DetectedInsight | None:
        """Check if session has been running for a long time (>2 hours)."""
        end = session_end or datetime.now()
        duration = end - session_start
        
        if duration.total_seconds() > 7200:  # 2 hours
            return DetectedInsight(
                type=InsightType.LONG_SESSION,
                confidence=0.7,
                description=f"Long session: {duration.total_seconds() / 3600:.1f} hours",
                messages=[],
                extracted_data={"duration_hours": duration.total_seconds() / 3600},
            )
        return None


def format_for_letta(turns: list[ConversationTurn], insights: list[DetectedInsight] | None = None) -> str:
    """Format conversation turns for Letta agent."""
    lines = ["<kimi_session_update>"]
    
    if insights:
        lines.append("\n<detected_insights>")
        for insight in insights:
            lines.append(f"  <insight type=\"{insight.type.value}\" confidence=\"{insight.confidence}\">")
            lines.append(f"    {insight.description}")
            if insight.extracted_data:
                lines.append(f"    <data>{json.dumps(insight.extracted_data, default=str)[:500]}</data>")
            lines.append("  </insight>")
        lines.append("</detected_insights>")
    
    lines.append("\n<transcript>")
    
    for turn in turns:
        # User message
        if turn.user_input:
            escaped = _escape_xml(turn.user_input)
            lines.append(f'<message role="user" turn="{turn.turn_number}">')
            lines.append(f"  {escaped}")
            lines.append('</message>')
        
        # Assistant thinking (summarized)
        if turn.assistant_thinking:
            thinking = " ".join(turn.assistant_thinking)
            if len(thinking) > 500:
                thinking = thinking[:500] + "... [truncated]"
            escaped = _escape_xml(thinking)
            lines.append(f'<message role="assistant" type="thinking">')
            lines.append(f"  {escaped}")
            lines.append('</message>')
        
        # Tool calls
        for tool in turn.tool_calls:
            name = tool.get("name", "unknown")
            args = tool.get("arguments", {})
            summary = _summarize_tool_call(name, args)
            lines.append(f'<message role="assistant" type="tool_call">')
            lines.append(f"  [{name}] {summary}")
            lines.append('</message>')
        
        # Tool results (errors only, truncated)
        for result in turn.tool_results:
            if result.get("is_error"):
                content = str(result.get("content", ""))[:200]
                lines.append(f'<message role="system" type="tool_error">')
                lines.append(f"  [Error] {content}")
                lines.append('</message>')
        
        # Assistant response
        if turn.assistant_response:
            response = " ".join(turn.assistant_response)
            escaped = _escape_xml(response)
            lines.append(f'<message role="assistant">')
            lines.append(f"  {escaped}")
            lines.append('</message>')
    
    lines.append("</transcript>")
    lines.append("\n<instructions>")
    lines.append("  You are a subconscious memory layer for Kimi Code sessions.")
    lines.append("  Process this transcript update and update your memory blocks accordingly.")
    lines.append("  Focus on: user preferences, corrections, patterns, and pending items.")
    lines.append("  Write to the 'guidance' block if you have actionable advice for the next session.")
    lines.append("</instructions>")
    lines.append("</kimi_session_update>")
    
    return "\n".join(lines)


def _escape_xml(text: str) -> str:
    """Escape XML special characters."""
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _summarize_tool_call(name: str, args: Any) -> str:
    """Summarize a tool call for brevity."""
    if not isinstance(args, dict):
        return str(args)[:100]
    
    if name == "ReadFile" and "path" in args:
        return f"Read {args['path']}"
    elif name == "WriteFile" and "path" in args:
        return f"Write {args['path']}"
    elif name == "StrReplaceFile" and "path" in args:
        return f"Edit {args['path']}"
    elif name == "Bash" and "command" in args:
        cmd = args["command"][:80]
        return f"Bash: {cmd}"
    elif name == "Glob" and "pattern" in args:
        return f"Glob: {args['pattern']}"
    elif name == "Grep" and "pattern" in args:
        return f"Grep: {args['pattern']}"
    else:
        # Generic summary
        args_str = str(args)[:100]
        return f"{name}: {args_str}"
