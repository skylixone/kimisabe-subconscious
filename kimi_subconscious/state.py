"""State management for Kimi Subconscious."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any

from platformdirs import user_data_dir

from .atomic import atomic_write_json, atomic_write_text, file_lock


class StateManager:
    """Manages state for Kimi Subconscious."""
    
    APP_NAME = "kimi-subconscious"
    APP_AUTHOR = "kimi-subconscious"
    
    def __init__(self):
        self.data_dir = Path(user_data_dir(self.APP_NAME, self.APP_AUTHOR))
        self.data_dir.mkdir(parents=True, exist_ok=True)
        
        self.config_path = self.data_dir / "config.json"
        self._config: dict[str, Any] | None = None
    
    # ============ Config ============
    
    def get_config(self) -> dict[str, Any]:
        """Get the config, loading from disk if needed."""
        if self._config is None:
            if self.config_path.exists():
                with open(self.config_path, "r") as f:
                    self._config = json.load(f)
            else:
                self._config = {}
        return self._config
    
    def save_config(self, config: dict[str, Any] | None = None) -> None:
        """Save config to disk atomically."""
        if config is not None:
            self._config = config
        atomic_write_json(self.config_path, self._config or {}, indent=2)
    
    def get_api_key(self) -> str | None:
        """Get Letta API key."""
        return self.get_config().get("letta_api_key")
    
    def set_api_key(self, api_key: str) -> None:
        """Set Letta API key."""
        config = self.get_config()
        config["letta_api_key"] = api_key
        self.save_config()
    
    def get_agent_id(self) -> str | None:
        """Get configured agent ID."""
        return self.get_config().get("agent_id")
    
    def set_agent_id(self, agent_id: str) -> None:
        """Set agent ID."""
        config = self.get_config()
        config["agent_id"] = agent_id
        self.save_config()
    
    def get_letta_base_url(self) -> str:
        """Get Letta base URL."""
        return self.get_config().get("letta_base_url", "https://api.letta.com")
    
    # ============ Project State ============
    
    def get_project_hash(self, project_path: Path | str) -> str:
        """Get the hash for a project path (matches Kimi's algorithm)."""
        path_str = str(project_path)
        return hashlib.md5(path_str.encode()).hexdigest()
    
    def get_project_dir(self, project_hash: str) -> Path:
        """Get the state directory for a project."""
        project_dir = self.data_dir / "projects" / project_hash
        project_dir.mkdir(parents=True, exist_ok=True)
        return project_dir
    
    def get_kimi_sessions_dir(self) -> Path | None:
        """Get Kimi's sessions directory."""
        kimi_sessions = Path.home() / ".kimi" / "sessions"
        if kimi_sessions.exists():
            return kimi_sessions
        return None
    
    def find_project_path(self, project_hash: str) -> Path | None:
        """Try to find the project path for a given hash."""
        # Check if we have it stored
        index = self._load_project_index()
        if project_hash in index:
            path = Path(index[project_hash])
            if path.exists():
                return path
        
        # Try to find by looking at Kimi's sessions
        kimi_sessions = self.get_kimi_sessions_dir()
        if not kimi_sessions:
            return None
        
        project_session_dir = kimi_sessions / project_hash
        if not project_session_dir.exists():
            return None
        
        # Look at the most recent session to find the working directory
        sessions = sorted(project_session_dir.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True)
        
        for session_dir in sessions:
            wire_path = session_dir / "wire.jsonl"
            if wire_path.exists():
                try:
                    with open(wire_path, "r") as f:
                        first_line = f.readline()
                        if first_line:
                            data = json.loads(first_line)
                            # First line is metadata, second line has the working dir
                            second_line = f.readline()
                            if second_line:
                                data = json.loads(second_line)
                                msg = data.get("message", {})
                                payload = msg.get("payload", {})
                                user_input = payload.get("user_input", [])
                                if user_input:
                                    text = user_input[0].get("text", "")
                                    # Look for Working Directory in handoff context
                                    if "Working Directory" in text:
                                        import re
                                        match = re.search(r"Working Directory\s*\|\s*`([^`]+)`", text)
                                        if match:
                                            path = Path(match.group(1))
                                            # Store for future use
                                            self._update_project_index(project_hash, str(path))
                                            return path
                except Exception:
                    continue
        
        return None
    
    def _load_project_index(self) -> dict[str, str]:
        """Load the project path index."""
        index_path = self.data_dir / "project_index.json"
        if index_path.exists():
            with open(index_path, "r") as f:
                return json.load(f)
        return {}
    
    def _update_project_index(self, project_hash: str, path: str) -> None:
        """Update the project path index atomically."""
        index = self._load_project_index()
        index[project_hash] = path
        index_path = self.data_dir / "project_index.json"
        atomic_write_json(index_path, index, indent=2)
    
    # ============ Session State ============
    
    def get_conversations_path(self, project_hash: str) -> Path:
        """Get the conversations mapping file path."""
        return self.get_project_dir(project_hash) / "conversations.json"
    
    def load_conversations(self, project_hash: str) -> dict[str, dict]:
        """Load the session -> Letta conversation mapping."""
        path = self.get_conversations_path(project_hash)
        if path.exists():
            with open(path, "r") as f:
                return json.load(f)
        return {}
    
    def save_conversations(self, project_hash: str, conversations: dict) -> None:
        """Save the session -> Letta conversation mapping atomically."""
        path = self.get_conversations_path(project_hash)
        atomic_write_json(path, conversations, indent=2)
    
    def get_conversation_id(self, project_hash: str, session_id: str) -> str | None:
        """Get the Letta conversation ID for a Kimi session."""
        conversations = self.load_conversations(project_hash)
        entry = conversations.get(session_id)
        if isinstance(entry, dict):
            return entry.get("conversation_id")
        elif isinstance(entry, str):
            return entry
        return None
    
    def set_conversation_id(
        self,
        project_hash: str,
        session_id: str,
        conversation_id: str,
        agent_id: str | None = None,
    ) -> None:
        """Set the Letta conversation ID for a Kimi session."""
        conversations = self.load_conversations(project_hash)
        conversations[session_id] = {
            "conversation_id": conversation_id,
            "agent_id": agent_id,
            "created_at": datetime.now().isoformat(),
        }
        self.save_conversations(project_hash, conversations)
    
    def get_last_read_path(self, project_hash: str, session_id: str) -> Path:
        """Get the last read offset file path."""
        return self.get_project_dir(project_hash) / f"last_read_{session_id}.json"
    
    def load_last_read(self, project_hash: str, session_id: str) -> dict[str, Any]:
        """Load the last read state for a session."""
        path = self.get_last_read_path(project_hash, session_id)
        if path.exists():
            with open(path, "r") as f:
                return json.load(f)
        return {
            "offset": 0,
            "last_message_id": None,
            "last_check": None,
        }
    
    def save_last_read(
        self,
        project_hash: str,
        session_id: str,
        offset: int,
        last_message_id: str | None = None,
    ) -> None:
        """Save the last read state for a session atomically."""
        path = self.get_last_read_path(project_hash, session_id)
        atomic_write_json(path, {
            "offset": offset,
            "last_message_id": last_message_id,
            "last_check": datetime.now().isoformat(),
        }, indent=2)
    
    def get_last_seen_message(self, project_hash: str, session_id: str) -> str | None:
        """Get the last seen Letta message ID."""
        return self.load_last_read(project_hash, session_id).get("last_message_id")
    
    def set_last_seen_message(self, project_hash: str, session_id: str, message_id: str) -> None:
        """Set the last seen Letta message ID atomically."""
        state = self.load_last_read(project_hash, session_id)
        state["last_message_id"] = message_id
        state["last_check"] = datetime.now().isoformat()
        path = self.get_last_read_path(project_hash, session_id)
        atomic_write_json(path, state, indent=2)
    
    # ============ Insights Database ============
    
    def get_insights_db_path(self, project_hash: str) -> Path:
        """Get the insights database path for a project."""
        return self.get_project_dir(project_hash) / "insights.db"
    
    def init_insights_db(self, project_hash: str) -> sqlite3.Connection:
        """Initialize the insights database with WAL mode for safety."""
        db_path = self.get_insights_db_path(project_hash)
        # Use timeout for busy waiting, isolation_level for auto-commit
        conn = sqlite3.connect(str(db_path), timeout=30.0, isolation_level=None)
        
        # Enable WAL mode for better concurrency and corruption resistance
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")  # Balance safety and speed
        conn.execute("PRAGMA cache_size=10000")  # 10MB cache
        
        conn.execute("""
            CREATE TABLE IF NOT EXISTS file_operations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                file_path TEXT NOT NULL,
                operation TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                session_id TEXT NOT NULL
            )
        """)
        
        conn.execute("""
            CREATE TABLE IF NOT EXISTS detected_insights (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                type TEXT NOT NULL,
                confidence REAL NOT NULL,
                description TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                session_id TEXT NOT NULL,
                sent_to_letta BOOLEAN DEFAULT FALSE
            )
        """)
        
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_file_ops_path ON file_operations(file_path)
        """)
        
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_insights_sent ON detected_insights(sent_to_letta)
        """)
        
        return conn
    
    def record_file_operation(
        self,
        project_hash: str,
        file_path: str,
        operation: str,
        session_id: str,
    ) -> None:
        """Record a file operation."""
        conn = self.init_insights_db(project_hash)
        try:
            conn.execute("BEGIN")
            conn.execute(
                "INSERT INTO file_operations (file_path, operation, timestamp, session_id) VALUES (?, ?, ?, ?)",
                (file_path, operation, datetime.now().isoformat(), session_id),
            )
            conn.execute("COMMIT")
        except Exception:
            conn.execute("ROLLBACK")
            raise
        finally:
            conn.close()
    
    def get_file_operation_count(self, project_hash: str, file_path: str, hours: int = 24) -> int:
        """Get the number of operations on a file in the last N hours."""
        conn = self.init_insights_db(project_hash)
        cursor = conn.execute(
            """
            SELECT COUNT(*) FROM file_operations
            WHERE file_path = ? AND timestamp > datetime('now', '-{} hours')
            """.format(hours),
            (file_path,),
        )
        count = cursor.fetchone()[0]
        conn.close()
        return count
    
    def record_insight(
        self,
        project_hash: str,
        insight_type: str,
        confidence: float,
        description: str,
        session_id: str,
        sent_to_letta: bool = False,
    ) -> int:
        """Record a detected insight. Returns the insight ID."""
        conn = self.init_insights_db(project_hash)
        try:
            conn.execute("BEGIN")
            cursor = conn.execute(
                """
                INSERT INTO detected_insights (type, confidence, description, timestamp, session_id, sent_to_letta)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (insight_type, confidence, description, datetime.now().isoformat(), session_id, sent_to_letta),
            )
            insight_id = cursor.lastrowid
            conn.execute("COMMIT")
            return insight_id
        except Exception:
            conn.execute("ROLLBACK")
            raise
        finally:
            conn.close()
    
    def get_unsent_insights(self, project_hash: str, limit: int = 100) -> list[dict]:
        """Get insights that haven't been sent to Letta yet."""
        conn = self.init_insights_db(project_hash)
        cursor = conn.execute(
            """
            SELECT id, type, confidence, description, timestamp, session_id
            FROM detected_insights
            WHERE sent_to_letta = FALSE
            ORDER BY timestamp ASC
            LIMIT ?
            """,
            (limit,),
        )
        rows = cursor.fetchall()
        conn.close()
        
        return [
            {
                "id": row[0],
                "type": row[1],
                "confidence": row[2],
                "description": row[3],
                "timestamp": row[4],
                "session_id": row[5],
            }
            for row in rows
        ]
    
    def mark_insights_sent(self, project_hash: str, insight_ids: list[int]) -> None:
        """Mark insights as sent to Letta."""
        conn = self.init_insights_db(project_hash)
        try:
            conn.execute("BEGIN")
            conn.executemany(
                "UPDATE detected_insights SET sent_to_letta = TRUE WHERE id = ?",
                [(i,) for i in insight_ids],
            )
            conn.execute("COMMIT")
        except Exception:
            conn.execute("ROLLBACK")
            raise
        finally:
            conn.close()
    
    # ============ SUBCONSCIOUS.md ============
    
    def get_subconscious_path(self, project_hash: str, project_path: Path | None = None) -> Path:
        """Get the SUBCONSCIOUS.md path.
        
        Strategy C: Try project root first, fall back to data dir.
        """
        if project_path:
            project_file = project_path / "SUBCONSCIOUS.md"
            # Check if we can write to it (or it doesn't exist yet)
            if not project_file.exists() or project_file.stat().st_mode & 0o200:
                return project_file
        
        # Fall back to data directory
        return self.get_project_dir(project_hash) / "SUBCONSCIOUS.md"
    
    def get_subconscious_content(self, project_hash: str, project_path: Path | None = None) -> str:
        """Get the current SUBCONSCIOUS.md content."""
        path = self.get_subconscious_path(project_hash, project_path)
        if path.exists():
            with open(path, "r") as f:
                return f.read()
        return ""
    
    def write_subconscious(
        self,
        project_hash: str,
        content: str,
        project_path: Path | None = None,
    ) -> Path:
        """Write SUBCONSCIOUS.md content atomically."""
        path = self.get_subconscious_path(project_hash, project_path)
        
        # Ensure directory exists
        path.parent.mkdir(parents=True, exist_ok=True)
        
        # Atomic write
        atomic_write_text(path, content)
        
        # If written to data dir and project path exists, create/update symlink
        if project_path and path.parent == self.get_project_dir(project_hash):
            project_file = project_path / "SUBCONSCIOUS.md"
            try:
                if project_file.exists() or project_file.is_symlink():
                    project_file.unlink()
                project_file.symlink_to(path)
            except OSError:
                # Symlink failed, that's ok
                pass
        
        return path
    
    def ensure_gitignore(self, project_path: Path) -> None:
        """Ensure SUBCONSCIOUS.md is in .gitignore."""
        gitignore = project_path / ".gitignore"
        entry = "SUBCONSCIOUS.md"
        
        if gitignore.exists():
            with open(gitignore, "r") as f:
                content = f.read()
            if entry not in content:
                with open(gitignore, "a") as f:
                    f.write(f"\n# Kimi Subconscious memory file\n{entry}\n")
        else:
            with open(gitignore, "w") as f:
                f.write(f"# Kimi Subconscious memory file\n{entry}\n")
