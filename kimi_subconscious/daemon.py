"""Background daemon for watching Kimi sessions."""

from __future__ import annotations

import os
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer

from .git_committer import get_committer, init_git_committer
from .letta_client import LettaClient, SubconsciousAgent
from .models import DetectedInsight
from .observability import get_logger, get_liveness, get_metrics, init_observability, LivenessMonitor, MetricsCollector
from .parser import WireParser, InsightDetector, format_for_letta
from .phoenix import PhoenixController, should_auto_restart
from .retry import wrap_letta_client
from .state import StateManager


class SessionWatcher(FileSystemEventHandler):
    """Watches for changes to Kimi session files."""
    
    def __init__(self, state: StateManager, client: LettaClient, agent: SubconsciousAgent):
        self.state = state
        self.client = client
        self.agent = agent
        self.phoenix = PhoenixController(state)
        self._last_check: dict[str, float] = {}
        self._cooldown = 10  # Minimum seconds between syncs for a session
        self._phoenix_enabled = should_auto_restart()
        self.logger = get_logger()
        self.metrics = get_metrics()
    
    def on_modified(self, event):
        if event.is_directory:
            return
        
        if event.src_path.endswith("wire.jsonl"):
            self._handle_wire_change(Path(event.src_path))
    
    def on_created(self, event):
        if event.is_directory:
            # New session directory
            return
        
        if event.src_path.endswith("wire.jsonl"):
            self._handle_wire_change(Path(event.src_path), is_new=True)
    
    def _handle_wire_change(self, wire_path: Path, is_new: bool = False):
        """Handle a change to wire.jsonl."""
        # Extract session info from path
        # ~/.kimi/sessions/{project_hash}/{session_id}/wire.jsonl
        parts = wire_path.parts
        try:
            sessions_idx = parts.index("sessions")
            project_hash = parts[sessions_idx + 1]
            session_id = parts[sessions_idx + 2]
        except (ValueError, IndexError):
            return
        
        # Cooldown check
        now = time.time()
        key = f"{project_hash}:{session_id}"
        if key in self._last_check:
            if now - self._last_check[key] < self._cooldown:
                return
        self._last_check[key] = now
        
        # Sync this session
        try:
            self._sync_session(project_hash, session_id, wire_path)
        except Exception as e:
            self.logger.error(f"Error syncing session {session_id}", component="watcher", error=e)
            self.metrics.gauge("sync_errors_total", self.metrics.get_gauge("sync_errors_total") or 0 + 1)
    
    def _sync_session(self, project_hash: str, session_id: str, wire_path: Path):
        """Sync a single session."""
        # Load last read position
        last_read = self.state.load_last_read(project_hash, session_id)
        
        # Parse new messages
        parser = WireParser(wire_path)
        new_messages, new_offset = parser.parse_new(last_read["offset"])
        
        if not new_messages:
            return
        
        # Build turns and detect insights
        parser.parse_all()
        turns = parser.build_turns()
        detector = InsightDetector(turns)
        insights = detector.detect_insights()
        
        # Only send if insights detected
        if not insights:
            # Still update offset so we don't re-parse
            self.state.save_last_read(project_hash, session_id, new_offset, last_read.get("last_message_id"))
            return
        
        self.logger.info(f"Detected {len(insights)} insights", component="watcher", session_id=session_id, insight_count=len(insights))
        self.metrics.gauge("insights_detected", len(insights))
        self.metrics.record("insights_detected_total", len(insights), session_id=session_id)
        
        # Get or create conversation
        conversation_id = self.state.get_conversation_id(project_hash, session_id)
        if not conversation_id:
            conversation_id = self.client.create_conversation(self.agent.agent_id)
            self.state.set_conversation_id(project_hash, session_id, conversation_id, self.agent.agent_id)
        
        # Format and send
        content = format_for_letta(turns, insights)
        
        # Record insights
        for insight in insights:
            self.state.record_insight(
                project_hash,
                insight.type.value,
                insight.confidence,
                insight.description,
                session_id,
                sent_to_letta=True,
            )
        
        # Send to Letta (with retry)
        from .retry import RetryableLettaClient
        retry_client = RetryableLettaClient(self.client)
        
        start_time = time.time()
        try:
            success = retry_client.send_message_with_retry(conversation_id, content)
            latency_ms = (time.time() - start_time) * 1000
            
            if success:
                self.state.save_last_read(project_hash, session_id, new_offset, last_read.get("last_message_id"))
                self.logger.info("Sent to Letta", component="watcher", session_id=session_id, latency_ms=latency_ms)
                self.metrics.record("letta_latency_ms", latency_ms, operation="send_message")
                
                # Check for guidance after a short delay
                time.sleep(3)
                self._check_guidance(project_hash, session_id, conversation_id)
            else:
                self.logger.warn("Conversation busy, will retry later", component="watcher", session_id=session_id)
                self.metrics.gauge("letta_busy_count", self.metrics.get_gauge("letta_busy_count") or 0 + 1)
        except Exception as e:
            latency_ms = (time.time() - start_time) * 1000
            self.logger.error("Failed to send to Letta after retries", component="watcher", session_id=session_id, error=e, latency_ms=latency_ms)
            self.metrics.record("letta_send_failures", 1, session_id=session_id)
    
    def _check_guidance(self, project_hash: str, session_id: str, conversation_id: str):
        """Check for new guidance from Letta."""
        last_seen = self.state.get_last_seen_message(project_hash, session_id)
        guidance_messages, newest_id = self.agent.get_new_guidance(conversation_id, last_seen)
        
        if guidance_messages:
            self.logger.info(f"Received {len(guidance_messages)} guidance messages", component="watcher", session_id=session_id)
            self.metrics.record("guidance_received", len(guidance_messages), session_id=session_id)
            
            # Update SUBCONSCIOUS.md
            self._update_subconscious(project_hash, guidance_messages)
            self.state.set_last_seen_message(project_hash, session_id, newest_id)
            
            # Auto-commit guidance
            committer = get_committer()
            if committer and guidance_messages:
                committer.commit_guidance(guidance_messages[0])
            
            # Trigger auto-restart if Phoenix mode enabled
            if self._phoenix_enabled:
                reason = f"New guidance: {guidance_messages[0][:50]}..." if guidance_messages else "Memory updated"
                self.phoenix.request_restart(project_hash, session_id, reason)
    
    def _update_subconscious(self, project_hash: str, guidance: list[str]):
        """Update SUBCONSCIOUS.md with new guidance."""
        from .injector import SubconsciousInjector
        
        # Find project path
        project_path = self.state.find_project_path(project_hash)
        
        # Get memory blocks
        try:
            blocks = self.agent.get_memory_blocks()
        except Exception:
            blocks = []
        
        # Generate content
        injector = SubconsciousInjector()
        content = injector.generate(
            memory_blocks=blocks,
            guidance_messages=guidance,
            agent_id=self.agent.agent_id,
            is_hosted="localhost" not in self.client.base_url,
        )
        
        # Write file
        self.state.write_subconscious(project_hash, content, project_path)
        if project_path:
            self.state.ensure_gitignore(project_path)
        
        self.logger.info("Updated SUBCONSCIOUS.md", component="watcher", project_hash=project_hash)
        self.metrics.record("subconscious_updated", 1, project_hash=project_hash)


def start_daemon(foreground: bool = False) -> int:
    """Start the background daemon.
    
    Returns the PID of the daemon process.
    """
    state = StateManager()
    
    # Initialize observability
    logger, liveness, metrics = init_observability(state.data_dir)
    
    # Initialize git committer
    init_git_committer()
    
    # Setup check
    api_key = state.get_api_key()
    agent_id = state.get_agent_id()
    
    if not api_key or not agent_id:
        logger.fatal("Daemon not configured", component="daemon")
        print("Error: Kimi Subconscious not configured. Run 'kimisub setup' first.", file=sys.stderr)
        sys.exit(1)
    
    # Daemonize if not foreground
    if not foreground:
        pid = os.fork()
        if pid > 0:
            # Parent process - just return the child's PID
            return pid
        
        # Child process - daemonize
        os.setsid()
        os.umask(0)
        
        # Second fork to prevent reacquiring terminal
        pid = os.fork()
        if pid > 0:
            os._exit(0)
        
        # Grandchild (actual daemon) - write our own PID
        pid_file = state.data_dir / "daemon.pid"
        with open(pid_file, "w") as f:
            f.write(str(os.getpid()))
        
        # Redirect stdin/stdout/stderr
        sys.stdout.flush()
        sys.stderr.flush()
        
        with open(os.devnull, "r") as f:
            os.dup2(f.fileno(), sys.stdin.fileno())
        with open(os.devnull, "a+") as f:
            os.dup2(f.fileno(), sys.stdout.fileno())
            os.dup2(f.fileno(), sys.stderr.fileno())
    
    logger.info("Daemon starting", component="daemon", foreground=foreground, pid=os.getpid())
    
    # Setup client and agent
    client = LettaClient(api_key=api_key, base_url=state.get_letta_base_url())
    agent = SubconsciousAgent(client, agent_id=agent_id)
    
    # Setup watcher
    kimi_sessions = state.get_kimi_sessions_dir()
    if not kimi_sessions:
        logger.fatal("Kimi sessions directory not found", component="daemon")
        print("Error: Kimi sessions directory not found.", file=sys.stderr)
        sys.exit(1)
    
    watcher = SessionWatcher(state, client, agent)
    observer = Observer()
    observer.schedule(watcher, str(kimi_sessions), recursive=True)
    observer.start()
    
    logger.info("File watcher started", component="daemon", watch_path=str(kimi_sessions))
    metrics.gauge("daemon_started", 1)
    metrics.gauge("watcher_active", 1)
    
    # Setup Phoenix controller for queued restarts
    phoenix = PhoenixController(state)
    
    if foreground:
        print(f"Daemon started, watching {kimi_sessions}")
        phoenix_status = "enabled" if should_auto_restart() else "disabled"
        print(f"Phoenix mode: {phoenix_status}")
        print("Press Ctrl+C to stop")
    
    last_heartbeat = 0
    last_metrics_save = 0
    
    try:
        while True:
            time.sleep(1)
            now = time.time()
            
            # Update heartbeat every 30 seconds
            if now - last_heartbeat >= 30:
                liveness.touch()
                last_heartbeat = now
                logger.debug("Heartbeat", component="daemon")
            
            # Save metrics every 60 seconds
            if now - last_metrics_save >= 60:
                metrics.save()
                last_metrics_save = now
                logger.debug("Metrics saved", component="daemon")
            
            # Check for queued Phoenix restarts every 5 seconds
            # (only if Phoenix mode is enabled)
            if should_auto_restart():
                # Check all active projects for queued restarts
                if hasattr(watcher, '_pending_restart'):
                    for key in list(watcher._pending_restart.keys()):
                        if watcher._pending_restart.get(key):
                            parts = key.split(":")
                            if len(parts) == 2:
                                project_hash, session_id = parts
                                phoenix.check_and_restart(project_hash, session_id)
                                
    except KeyboardInterrupt:
        if foreground:
            print("\nStopping...")
        logger.info("Daemon stopping (KeyboardInterrupt)", component="daemon")
    except Exception as e:
        logger.fatal("Daemon crashed", component="daemon", error=e)
        raise
    finally:
        observer.stop()
        observer.join()
        metrics.gauge("watcher_active", 0)
        metrics.save()
        logger.info("Daemon stopped", component="daemon")
        
        if not foreground:
            pid_file = state.data_dir / "daemon.pid"
            if pid_file.exists():
                pid_file.unlink()
    
    return 0


def run_consolidation():
    """Run consolidation for all projects with activity."""
    state = StateManager()
    
    api_key = state.get_api_key()
    agent_id = state.get_agent_id()
    
    if not api_key or not agent_id:
        print("Not configured, skipping consolidation", file=sys.stderr)
        return
    
    client = LettaClient(api_key=api_key, base_url=state.get_letta_base_url())
    agent = SubconsciousAgent(client, agent_id=agent_id)
    
    # Find all projects with sessions
    kimi_sessions = state.get_kimi_sessions_dir()
    if not kimi_sessions:
        return
    
    for project_hash_dir in kimi_sessions.iterdir():
        if not project_hash_dir.is_dir():
            continue
        
        project_hash = project_hash_dir.name
        
        # Check for unsent insights
        unsent = state.get_unsent_insights(project_hash)
        
        if not unsent:
            continue
        
        print(f"Consolidating {project_hash[:16]}... ({len(unsent)} insights)", file=sys.stderr)
        
        try:
            # Get or create consolidation conversation
            consolidation_session = "consolidation"
            conversation_id = state.get_conversation_id(project_hash, consolidation_session)
            
            if not conversation_id:
                conversation_id = client.create_conversation(agent.agent_id)
                state.set_conversation_id(project_hash, consolidation_session, conversation_id, agent.agent_id)
            
            # Send consolidation message
            message = f"""<kimi_consolidation>
<timestamp>{datetime.now().isoformat()}</timestamp>

<unsent_insights count="{len(unsent)}">
{chr(10).join(f"  - [{i['type']}] {i['description']}" for i in unsent[:20])}
</unsent_insights>

<instructions>
This is your daily memory consolidation. Review the unsent insights above,
update your memory blocks as needed, and prepare guidance for the next session.
Focus on patterns, preferences, and any pending items that need attention.
</instructions>
</kimi_consolidation>"""
            
            success = client.send_message(conversation_id, message)
            
            if success:
                state.mark_insights_sent(project_hash, [i["id"] for i in unsent])
                
                # Check for guidance
                time.sleep(3)
                last_seen = state.get_last_seen_message(project_hash, consolidation_session)
                guidance_messages, newest_id = agent.get_new_guidance(conversation_id, last_seen)
                
                if guidance_messages:
                    project_path = state.find_project_path(project_hash)
                    
                    # Update SUBCONSCIOUS.md
                    from .injector import SubconsciousInjector
                    
                    try:
                        blocks = agent.get_memory_blocks()
                    except Exception:
                        blocks = []
                    
                    injector = SubconsciousInjector()
                    content = injector.generate(
                        memory_blocks=blocks,
                        guidance_messages=guidance_messages,
                        agent_id=agent.agent_id,
                        is_hosted="localhost" not in client.base_url,
                    )
                    
                    state.write_subconscious(project_hash, content, project_path)
                    state.set_last_seen_message(project_hash, consolidation_session, newest_id)
        
        except Exception as e:
            print(f"Error consolidating {project_hash}: {e}", file=sys.stderr)


if __name__ == "__main__":
    start_daemon(foreground=True)
