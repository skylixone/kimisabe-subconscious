"""Auto-commit state changes to git for backup and recovery.

Commits every significant state change so a new machine can clone and resume.
"""

from __future__ import annotations

import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any


class GitCommitter:
    """Auto-commit state changes to git."""
    
    def __init__(self, repo_path: Path | None = None):
        self.repo_path = repo_path or Path(__file__).parent.parent
        self.enabled = self._check_git_repo()
        self.last_commit_time: float | None = None
        self.min_commit_interval = 5  # seconds between commits
    
    def _check_git_repo(self) -> bool:
        """Check if we're in a git repo."""
        try:
            result = subprocess.run(
                ["git", "rev-parse", "--git-dir"],
                cwd=self.repo_path,
                capture_output=True,
                text=True,
                check=True,
            )
            return bool(result.stdout.strip())
        except Exception:
            return False
    
    def should_commit(self) -> bool:
        """Check if we should commit now (rate limiting)."""
        import time
        if self.last_commit_time is None:
            return True
        return (time.time() - self.last_commit_time) >= self.min_commit_interval
    
    def commit_state_change(
        self,
        change_type: str,
        details: str = "",
        files: list[Path] | None = None,
    ) -> bool:
        """Commit a state change.
        
        Args:
            change_type: Type of change (insight, guidance, config, etc.)
            details: Human-readable details
            files: Specific files to commit (if None, commits all changes)
        
        Returns:
            True if commit was made, False otherwise
        """
        if not self.enabled:
            return False
        
        if not self.should_commit():
            return False
        
        try:
            # Add files
            if files:
                for f in files:
                    rel_path = f.relative_to(self.repo_path) if f.is_absolute() else f
                    subprocess.run(
                        ["git", "add", str(rel_path)],
                        cwd=self.repo_path,
                        capture_output=True,
                        check=True,
                    )
            else:
                # Add all changes
                subprocess.run(
                    ["git", "add", "-A"],
                    cwd=self.repo_path,
                    capture_output=True,
                    check=True,
                )
            
            # Check if there are changes to commit
            result = subprocess.run(
                ["git", "diff", "--cached", "--quiet"],
                cwd=self.repo_path,
                capture_output=True,
            )
            if result.returncode == 0:
                # No changes
                return False
            
            # Create commit message
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            message = f"[{change_type}] {details}"[:72]  # Keep first line short
            message += f"\n\nAuto-commit at {timestamp}\nChange: {change_type}"
            
            # Commit
            subprocess.run(
                ["git", "commit", "-m", message],
                cwd=self.repo_path,
                capture_output=True,
                check=True,
            )
            
            # Push (async - don't block)
            subprocess.Popen(
                ["git", "push", "origin", "HEAD"],
                cwd=self.repo_path,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            
            import time
            self.last_commit_time = time.time()
            return True
            
        except Exception:
            return False
    
    def commit_insight(self, insight_type: str, description: str) -> bool:
        """Commit when an insight is recorded."""
        return self.commit_state_change(
            change_type="insight",
            details=f"{insight_type}: {description[:50]}...",
        )
    
    def commit_guidance(self, guidance_summary: str) -> bool:
        """Commit when guidance is received."""
        return self.commit_state_change(
            change_type="guidance",
            details=f"New guidance: {guidance_summary[:50]}...",
        )
    
    def commit_config_change(self, config_key: str) -> bool:
        """Commit when config changes."""
        return self.commit_state_change(
            change_type="config",
            details=f"Config updated: {config_key}",
        )
    
    def commit_memory_update(self, block_label: str) -> bool:
        """Commit when memory blocks are updated."""
        return self.commit_state_change(
            change_type="memory",
            details=f"Memory block updated: {block_label}",
        )


# Global instance
_committer: GitCommitter | None = None


def init_git_committer(repo_path: Path | None = None) -> GitCommitter:
    """Initialize the git committer."""
    global _committer
    _committer = GitCommitter(repo_path)
    return _committer


def get_committer() -> GitCommitter | None:
    """Get the global committer instance."""
    return _committer
