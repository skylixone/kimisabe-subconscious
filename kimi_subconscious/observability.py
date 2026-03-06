"""Observability and monitoring for Kimi Subconscious.

Provides structured logging, health checks, metrics, and liveness monitoring.
"""

from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from pathlib import Path
from typing import Any

from platformdirs import user_log_dir


class LogLevel(Enum):
    DEBUG = "debug"
    INFO = "info"
    WARN = "warn"
    ERROR = "error"
    FATAL = "fatal"


@dataclass
class Metric:
    """A single metric data point."""
    name: str
    value: float
    timestamp: float = field(default_factory=time.time)
    labels: dict[str, str] = field(default_factory=dict)
    
    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "value": self.value,
            "timestamp": self.timestamp,
            "labels": self.labels,
        }


@dataclass
class HealthStatus:
    """Complete health status of the subconscious system."""
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    overall: str = "unknown"  # healthy, degraded, unhealthy
    
    # Component health
    daemon_running: bool = False
    daemon_pid: int | None = None
    daemon_uptime_seconds: float | None = None
    
    # Watchdog health
    watcher_alive: bool = False
    last_watchdog_ping: float | None = None
    watchdog_ping_age_seconds: float | None = None
    
    # API health
    api_reachable: bool = False
    api_latency_ms: float | None = None
    api_last_error: str | None = None
    
    # Storage health
    storage_writable: bool = False
    storage_free_bytes: int | None = None
    storage_free_percent: float | None = None
    
    # Queue health
    unsent_insights_count: int = 0
    oldest_unsent_age_hours: float | None = None
    
    # Recent errors
    recent_errors: list[dict] = field(default_factory=list)
    
    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
    
    def to_json(self, indent: bool = False) -> str:
        return json.dumps(self.to_dict(), indent=2 if indent else None)


class StructuredLogger:
    """Structured JSON logger for the subconscious system."""
    
    def __init__(self, name: str = "kimi-subconscious"):
        self.name = name
        self.log_dir = Path(user_log_dir(name, name))
        self.log_dir.mkdir(parents=True, exist_ok=True)
        
        # Rotating log files by day
        self.current_log_file: Path | None = None
        self.current_log_date: str | None = None
        
        # Error buffer for health checks
        self.recent_errors: list[dict] = []
        self.max_errors = 10
    
    def _get_log_file(self) -> Path:
        """Get today's log file path."""
        today = datetime.now().strftime("%Y-%m-%d")
        if today != self.current_log_date:
            self.current_log_date = today
            self.current_log_file = self.log_dir / f"subconscious-{today}.jsonl"
        return self.current_log_file or self.log_dir / f"subconscious-{today}.jsonl"
    
    def log(
        self,
        level: LogLevel,
        message: str,
        component: str | None = None,
        extra: dict[str, Any] | None = None,
        error: Exception | None = None,
    ) -> None:
        """Write a structured log entry."""
        entry = {
            "timestamp": datetime.now().isoformat(),
            "level": level.value,
            "logger": self.name,
            "message": message,
            "component": component or "daemon",
        }
        
        if extra:
            entry["extra"] = extra
        
        if error:
            entry["error"] = {
                "type": type(error).__name__,
                "message": str(error),
            }
        
        # Write to log file
        log_file = self._get_log_file()
        with open(log_file, "a") as f:
            f.write(json.dumps(entry) + "\n")
        
        # Buffer errors for health checks
        if level in (LogLevel.ERROR, LogLevel.FATAL):
            self.recent_errors.append({
                "timestamp": entry["timestamp"],
                "message": message,
                "component": component,
            })
            # Keep only recent errors
            self.recent_errors = self.recent_errors[-self.max_errors:]
    
    def debug(self, message: str, component: str | None = None, **extra) -> None:
        self.log(LogLevel.DEBUG, message, component, extra or None)
    
    def info(self, message: str, component: str | None = None, **extra) -> None:
        self.log(LogLevel.INFO, message, component, extra or None)
    
    def warn(self, message: str, component: str | None = None, **extra) -> None:
        self.log(LogLevel.WARN, message, component, extra or None)
    
    def error(self, message: str, component: str | None = None, error: Exception | None = None, **extra) -> None:
        self.log(LogLevel.ERROR, message, component, extra or None, error)
    
    def fatal(self, message: str, component: str | None = None, error: Exception | None = None, **extra) -> None:
        self.log(LogLevel.FATAL, message, component, extra or None, error)
    
    def get_recent_errors(self, since_seconds: int = 3600) -> list[dict]:
        """Get errors within the last N seconds."""
        cutoff = time.time() - since_seconds
        return [
            e for e in self.recent_errors
            if datetime.fromisoformat(e["timestamp"]).timestamp() > cutoff
        ]


class LivenessMonitor:
    """Monitors daemon liveness via heartbeat file."""
    
    HEARTBEAT_FILE = "watchdog.alive"
    HEARTBEAT_INTERVAL_SECONDS = 30
    STALE_THRESHOLD_SECONDS = 120
    
    def __init__(self, data_dir: Path):
        self.data_dir = data_dir
        self.heartbeat_file = data_dir / self.HEARTBEAT_FILE
    
    def touch(self) -> None:
        """Update heartbeat timestamp."""
        self.heartbeat_file.touch()
    
    def is_alive(self) -> tuple[bool, float | None]:
        """Check if heartbeat is fresh.
        
        Returns (is_alive, age_seconds).
        """
        if not self.heartbeat_file.exists():
            return False, None
        
        mtime = self.heartbeat_file.stat().st_mtime
        age = time.time() - mtime
        is_alive = age < self.STALE_THRESHOLD_SECONDS
        return is_alive, age
    
    def get_last_ping(self) -> datetime | None:
        """Get last heartbeat timestamp."""
        if not self.heartbeat_file.exists():
            return None
        return datetime.fromtimestamp(self.heartbeat_file.stat().st_mtime)


class MetricsCollector:
    """Collects and stores metrics for the subconscious system."""
    
    def __init__(self, data_dir: Path):
        self.data_dir = data_dir
        self.metrics_file = data_dir / "metrics.json"
        self._metrics: list[Metric] = []
        self._gauges: dict[str, float] = {}
    
    def record(self, name: str, value: float, **labels) -> None:
        """Record a metric data point."""
        metric = Metric(name=name, value=value, labels=labels)
        self._metrics.append(metric)
        
        # Keep only last 1000 metrics
        if len(self._metrics) > 1000:
            self._metrics = self._metrics[-1000:]
    
    def gauge(self, name: str, value: float) -> None:
        """Set a gauge value (current state)."""
        self._gauges[name] = value
    
    def get_gauge(self, name: str) -> float | None:
        """Get current gauge value."""
        return self._gauges.get(name)
    
    def save(self) -> None:
        """Save current metrics to disk."""
        data = {
            "timestamp": datetime.now().isoformat(),
            "gauges": self._gauges,
            "recent_metrics": [m.to_dict() for m in self._metrics[-100:]],
        }
        with open(self.metrics_file, "w") as f:
            json.dump(data, f, indent=2)
    
    def load(self) -> dict[str, Any]:
        """Load metrics from disk."""
        if not self.metrics_file.exists():
            return {"gauges": {}, "recent_metrics": []}
        with open(self.metrics_file, "r") as f:
            return json.load(f)


class HealthChecker:
    """Performs deep health checks on the subconscious system."""
    
    def __init__(
        self,
        state_manager: Any,  # StateManager
        logger: StructuredLogger,
        liveness: LivenessMonitor,
        metrics: MetricsCollector,
    ):
        self.state = state_manager
        self.logger = logger
        self.liveness = liveness
        self.metrics = metrics
    
    def check(self, deep: bool = False) -> HealthStatus:
        """Perform health check.
        
        Args:
            deep: If True, check API reachability and storage.
        """
        status = HealthStatus()
        
        # Check daemon PID
        pid_file = self.state.data_dir / "daemon.pid"
        if pid_file.exists():
            try:
                with open(pid_file) as f:
                    pid = int(f.read().strip())
                # Check if process exists
                import os
                os.kill(pid, 0)
                status.daemon_running = True
                status.daemon_pid = pid
                
                # Get uptime if possible
                try:
                    import psutil
                    proc = psutil.Process(pid)
                    status.daemon_uptime_seconds = time.time() - proc.create_time()
                except Exception:
                    pass
            except (ValueError, OSError, ProcessLookupError):
                status.daemon_running = False
        
        # Check liveness heartbeat
        alive, age = self.liveness.is_alive()
        status.watcher_alive = alive
        status.last_watchdog_ping = self.liveness.get_last_ping()
        status.watchdog_ping_age_seconds = age
        
        # Deep checks
        if deep:
            status = self._deep_checks(status)
        
        # Determine overall health
        if status.daemon_running and status.watcher_alive:
            if deep and not status.api_reachable:
                status.overall = "degraded"
            else:
                status.overall = "healthy"
        elif status.daemon_running and not status.watcher_alive:
            status.overall = "degraded"  # Zombie daemon
        else:
            status.overall = "unhealthy"
        
        # Add recent errors
        status.recent_errors = self.logger.get_recent_errors(since_seconds=3600)
        
        return status
    
    def _deep_checks(self, status: HealthStatus) -> HealthStatus:
        """Perform deep health checks."""
        # Check API reachability
        try:
            import httpx
            start = time.time()
            response = httpx.get(
                f"{self.state.get_letta_base_url()}/v1/health",
                timeout=10.0,
                headers={"Authorization": f"Bearer {self.state.get_api_key() or ''}"},
            )
            status.api_latency_ms = (time.time() - start) * 1000
            status.api_reachable = response.status_code == 200
        except Exception as e:
            status.api_reachable = False
            status.api_last_error = str(e)
        
        # Check storage
        try:
            test_file = self.state.data_dir / ".write_test"
            test_file.write_text("test")
            test_file.unlink()
            status.storage_writable = True
        except Exception:
            status.storage_writable = False
        
        # Check disk space
        try:
            import shutil
            usage = shutil.disk_usage(self.state.data_dir)
            status.storage_free_bytes = usage.free
            status.storage_free_percent = (usage.free / usage.total) * 100
        except Exception:
            pass
        
        # Check queue depth
        try:
            unsent = self.state.get_unsent_insights(limit=1000)
            status.unsent_insights_count = len(unsent)
            
            if unsent:
                oldest = min(unsent, key=lambda x: x["timestamp"])
                oldest_time = datetime.fromisoformat(oldest["timestamp"])
                status.oldest_unsent_age_hours = (
                    datetime.now() - oldest_time
                ).total_seconds() / 3600
        except Exception:
            pass
        
        return status


# Global instances (initialized by daemon)
_logger: StructuredLogger | None = None
_liveness: LivenessMonitor | None = None
_metrics: MetricsCollector | None = None


def init_observability(data_dir: Path) -> tuple[StructuredLogger, LivenessMonitor, MetricsCollector]:
    """Initialize observability subsystem."""
    global _logger, _liveness, _metrics
    
    _logger = StructuredLogger()
    _liveness = LivenessMonitor(data_dir)
    _metrics = MetricsCollector(data_dir)
    
    return _logger, _liveness, _metrics


def get_logger() -> StructuredLogger:
    """Get the global logger instance."""
    if _logger is None:
        raise RuntimeError("Observability not initialized. Call init_observability first.")
    return _logger


def get_liveness() -> LivenessMonitor:
    """Get the global liveness monitor."""
    if _liveness is None:
        raise RuntimeError("Observability not initialized. Call init_observability first.")
    return _liveness


def get_metrics() -> MetricsCollector:
    """Get the global metrics collector."""
    if _metrics is None:
        raise RuntimeError("Observability not initialized. Call init_observability first.")
    return _metrics
