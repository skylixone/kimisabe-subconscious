"""Atomic file operations for data integrity.

Prevents corruption from:
- Power loss during write
- Concurrent writes
- Partial writes on disk full
"""

from __future__ import annotations

import os
import tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import filelock


class AtomicFileWriter:
    """Write files atomically using temp + rename pattern."""
    
    def __init__(self, target_path: Path, mode: str = "w", encoding: str = "utf-8"):
        self.target_path = Path(target_path)
        self.mode = mode
        self.encoding = encoding
        self.temp_file: tempfile._TemporaryFileWrapper | None = None
        self._written = False
    
    def __enter__(self):
        # Create temp file in same directory for atomic rename
        fd, temp_path = tempfile.mkstemp(
            dir=self.target_path.parent,
            prefix=f".{self.target_path.name}.tmp-",
            suffix=".tmp"
        )
        self.temp_path = Path(temp_path)
        os.close(fd)
        
        # Open for writing
        self.temp_file = open(temp_path, self.mode, encoding=self.encoding)
        return self.temp_file
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.temp_file:
            self.temp_file.close()
        
        if exc_type is None and self.temp_path.exists():
            # Success: atomic rename
            try:
                os.replace(self.temp_path, self.target_path)
                self._written = True
            except OSError:
                # Clean up temp on failure
                self._cleanup()
                raise
        else:
            # Failure: clean up temp
            self._cleanup()
    
    def _cleanup(self):
        """Remove temp file if it exists."""
        try:
            if hasattr(self, 'temp_path') and self.temp_path.exists():
                self.temp_path.unlink()
        except OSError:
            pass


def atomic_write_text(path: Path, content: str, encoding: str = "utf-8") -> None:
    """Write text file atomically."""
    with AtomicFileWriter(path, mode="w", encoding=encoding) as f:
        f.write(content)


def atomic_write_json(path: Path, data: Any, indent: int | None = None) -> None:
    """Write JSON file atomically."""
    import json
    content = json.dumps(data, indent=indent)
    atomic_write_text(path, content)


def atomic_write_bytes(path: Path, content: bytes) -> None:
    """Write binary file atomically."""
    fd, temp_path = tempfile.mkstemp(
        dir=path.parent,
        prefix=f".{path.name}.tmp-",
        suffix=".tmp"
    )
    try:
        os.write(fd, content)
        os.fsync(fd)  # Ensure data hits disk
        os.close(fd)
        os.replace(temp_path, path)
    except:
        os.close(fd)
        try:
            os.unlink(temp_path)
        except OSError:
            pass
        raise


@contextmanager
def file_lock(path: Path, timeout: float = 10.0):
    """Acquire a file lock for exclusive access.
    
    Usage:
        with file_lock(path_to_file):
            # Exclusive access to file
            data = json.loads(path.read_text())
    """
    lock_path = path.parent / f".{path.name}.lock"
    lock = filelock.FileLock(str(lock_path), timeout=timeout)
    try:
        lock.acquire()
        yield
    finally:
        lock.release()
        # Clean up lock file
        try:
            lock_path.unlink(missing_ok=True)
        except OSError:
            pass


class SafeStateManager:
    """Mixin-style class for safe file operations in StateManager.
    
    Use this to wrap existing state operations with atomicity.
    """
    
    def _atomic_save_json(self, path: Path, data: Any, indent: int | None = 2) -> None:
        """Save JSON file atomically with locking."""
        with file_lock(path):
            atomic_write_json(path, data, indent=indent)
    
    def _atomic_load_json(self, path: Path, default: Any = None) -> Any:
        """Load JSON file with locking."""
        import json
        with file_lock(path):
            if not path.exists():
                return default
            return json.loads(path.read_text())
    
    def _safe_sqlite_execute(self, db_path: Path, operation) -> Any:
        """Execute SQLite operation with WAL mode for safety."""
        import sqlite3
        conn = sqlite3.connect(str(db_path), timeout=30.0)
        try:
            # Enable WAL mode for better concurrency and corruption resistance
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA synchronous=NORMAL")
            
            result = operation(conn)
            conn.commit()
            return result
        finally:
            conn.close()
