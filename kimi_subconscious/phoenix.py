"""Auto-restart functionality for seamless memory integration."""

from __future__ import annotations

import os
import psutil
import signal
import subprocess
import sys
import time
from pathlib import Path
from typing import Optional

from .state import StateManager


class PhoenixController:
    """Controls auto-restart of Kimi sessions for memory refresh."""
    
    # Rate limiting config
    MAX_RESTARTS_PER_MINUTE = 3
    RESTART_WINDOW_SECONDS = 60
    
    def __init__(self, state: StateManager):
        self.state = state
        self._pending_restart: dict[str, bool] = {}  # session_id -> needs_restart
        self._restart_history: dict[str, list[float]] = {}  # session_id -> list of restart timestamps
        self._last_restart_attempt: dict[str, float] = {}  # session_id -> timestamp
        
    def find_kimi_process(self, session_id: str | None = None) -> Optional[psutil.Process]:
        """Find the Kimi process for the current terminal/session."""
        current_tty = os.ttyname(sys.stdin.fileno()) if sys.stdin.isatty() else None
        current_pgrp = os.getpgrp()
        
        for proc in psutil.process_iter(['pid', 'name', 'cmdline', 'terminal']):
            try:
                # Look for kimi processes
                if proc.info['name'] not in ('kimi', 'python', 'python3'):
                    continue
                    
                cmdline = proc.info.get('cmdline', [])
                if not cmdline:
                    continue
                    
                # Check if it's a kimi command
                if 'kimi' not in cmdline[0] and 'kimi' not in ' '.join(cmdline):
                    continue
                
                # If session_id provided, check if this process is in that session
                if session_id:
                    # Check environment or working directory for session hint
                    try:
                        environ = proc.environ()
                        if environ.get('KIMI_SESSION_ID') == session_id:
                            return proc
                    except (psutil.NoSuchProcess, psutil.AccessDenied):
                        pass
                    
                    # Check working directory matches project
                    try:
                        cwd = proc.cwd()
                        expected_hash = self.state.get_project_hash(cwd)
                        if self._is_session_for_project(session_id, expected_hash):
                            return proc
                    except (psutil.NoSuchProcess, psutil.AccessDenied):
                        pass
                
                # Match by terminal/TTY
                if current_tty:
                    try:
                        proc_tty = proc.terminal()
                        if proc_tty == current_tty:
                            return proc
                    except (psutil.NoSuchProcess, psutil.AccessDenied):
                        pass
                        
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                continue
                
        return None
    
    def _is_session_for_project(self, session_id: str, project_hash: str) -> bool:
        """Check if a session ID belongs to a project."""
        kimi_sessions = self.state.get_kimi_sessions_dir()
        if not kimi_sessions:
            return False
            
        project_dir = kimi_sessions / project_hash
        if not project_dir.exists():
            return False
            
        # Check if session exists in this project
        return (project_dir / session_id).exists()
    
    def request_restart(self, project_hash: str, session_id: str, reason: str) -> bool:
        """Request an auto-restart for a session.
        
        Returns True if restart was triggered, False if queued for later.
        """
        key = f"{project_hash}:{session_id}"
        
        # Check rate limiting
        if self._is_rate_limited(session_id):
            self._notify_user(f"Restart rate limit exceeded for {session_id[:8]}...", error=True)
            return False
        
        # Check if Kimi is currently idle
        if self._is_kimi_idle(project_hash, session_id):
            return self._execute_restart(project_hash, session_id, reason)
        else:
            # Queue for restart when idle
            self._pending_restart[key] = True
            self._notify_user(reason, queued=True)
            return False
    
    def _is_rate_limited(self, session_id: str) -> bool:
        """Check if restart is rate limited for this session."""
        now = time.time()
        window_start = now - self.RESTART_WINDOW_SECONDS
        
        # Get restart history for this session
        history = self._restart_history.get(session_id, [])
        
        # Filter to recent restarts
        recent_restarts = [t for t in history if t > window_start]
        
        # Update history
        self._restart_history[session_id] = recent_restarts
        
        # Check limit
        return len(recent_restarts) >= self.MAX_RESTARTS_PER_MINUTE
    
    def _is_kimi_idle(self, project_hash: str, session_id: str) -> bool:
        """Check if Kimi is in a safe state to restart (just completed a turn)."""
        # Check wire.jsonl for recent activity
        kimi_sessions = self.state.get_kimi_sessions_dir()
        if not kimi_sessions:
            return False
            
        wire_path = kimi_sessions / project_hash / session_id / "wire.jsonl"
        if not wire_path.exists():
            return False
        
        # Read last few lines
        try:
            with open(wire_path, 'r') as f:
                # Seek to near end
                f.seek(0, 2)  # End
                size = f.tell()
                f.seek(max(0, size - 4096))  # Last 4KB
                
                lines = f.readlines()
                
                # Look for TurnEnd (completed) vs TurnBegin/StepBegin (in progress)
                for line in reversed(lines):
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        import json
                        data = json.loads(line)
                        msg_type = data.get('message', {}).get('type')
                        
                        if msg_type == 'TurnEnd':
                            # Completed a turn - safe to restart
                            # Check if it was recent (< 5 seconds ago)
                            timestamp = data.get('timestamp', 0)
                            return (time.time() - timestamp) < 5
                        elif msg_type in ('TurnBegin', 'StepBegin'):
                            # In the middle of something
                            return False
                    except json.JSONDecodeError:
                        continue
                        
        except Exception:
            pass
            
        return False
    
    def check_and_restart(self, project_hash: str, session_id: str) -> bool:
        """Check if a queued restart can now execute.
        
        Call this periodically from the daemon.
        """
        key = f"{project_hash}:{session_id}"
        
        if not self._pending_restart.get(key):
            return False
            
        if self._is_kimi_idle(project_hash, session_id):
            return self._execute_restart(project_hash, session_id, "memory integration complete")
            
        return False
    
    def _execute_restart(self, project_hash: str, session_id: str, reason: str) -> bool:
        """Execute the actual restart."""
        key = f"{project_hash}:{session_id}"
        
        # Check rate limit one more time before executing
        if self._is_rate_limited(session_id):
            self._notify_user("Restart aborted: rate limit would be exceeded", error=True)
            self._pending_restart.pop(key, None)
            return False
        
        # Record restart attempt
        now = time.time()
        self._last_restart_attempt[session_id] = now
        if session_id not in self._restart_history:
            self._restart_history[session_id] = []
        self._restart_history[session_id].append(now)
        
        # Find Kimi process
        proc = self.find_kimi_process(session_id)
        if not proc:
            self._notify_user("Could not find Kimi process to restart", error=True)
            return False
        
        # Get project path for the restart
        project_path = self.state.find_project_path(project_hash)
        work_dir = project_path or Path.cwd()
        
        # Clear pending flag
        self._pending_restart.pop(key, None)
        
        # Notify before restart
        restart_count = len(self._restart_history.get(session_id, []))
        self._notify_user(f"[{restart_count}/3 per min] Restarting Kimi: {reason[:50]}...")
        time.sleep(1)  # Give user a moment to see
        
        try:
            # Get terminal info for the new process
            env = os.environ.copy()
            env['KIMI_PHOENIX_RESTART'] = '1'
            env['KIMI_PHOENIX_REASON'] = reason
            
            # Spawn continuation process
            subprocess.Popen(
                ['kimi', '--continue'],
                cwd=work_dir,
                env=env,
                # Detach properly
                start_new_session=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            
            # Give new process time to start
            time.sleep(0.5)
            
            # Kill old process
            proc.terminate()
            try:
                proc.wait(timeout=3)
            except psutil.TimeoutExpired:
                proc.kill()
                
            return True
            
        except Exception as e:
            self._notify_user(f"Restart failed: {e}", error=True)
            return False
    
    def _notify_user(self, message: str, queued: bool = False, error: bool = False) -> None:
        """Notify the user about restart status."""
        prefix = ""
        if error:
            prefix = "\033[91m[Kimisub ERROR]\033[0m"
        elif queued:
            prefix = "\033[93m[Kimisub QUEUED]\033[0m"
        else:
            prefix = "\033[92m[Kimisub]\033[0m"
            
        # Print to stderr with escape codes for visibility
        print(f"\n{prefix} {message}\033[0m", file=sys.stderr)
        
        if queued:
            print("\033[90m        Will restart when Kimi finishes current task...\033[0m", file=sys.stderr)


def should_auto_restart() -> bool:
    """Check if auto-restart is enabled in config."""
    state = StateManager()
    config = state.get_config()
    return config.get('phoenix_mode', False)


def enable_phoenix_mode(enable: bool = True) -> None:
    """Enable or disable auto-restart (Phoenix mode)."""
    state = StateManager()
    config = state.get_config()
    config['phoenix_mode'] = enable
    state.save_config()
    
    status = "enabled" if enable else "disabled"
    print(f"Phoenix mode {status}. Kimi will auto-restart when new guidance arrives.")