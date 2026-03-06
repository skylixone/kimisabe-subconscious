#!/usr/bin/env python3
"""Stress tests for Kimi Subconscious reliability.

Usage:
    python stress_tests.py <test_name>

Tests:
    resurrection      - Kill daemon mid-operation, verify auto-recovery
    fsevents          - Exhaust FSEvents watcher limit
    api_blackout      - Block API access, verify queue behavior
    disk_full         - Simulate disk full condition
    restart_loop      - Trigger Phoenix restart cascade
    corruption        - Corrupt state files, verify recovery
    rapid_changes     - 1000 file changes per second
    concurrent        - Multiple sessions simultaneously
"""

from __future__ import annotations

import os
import signal
import subprocess
import sys
import tempfile
import time
from pathlib import Path


def get_daemon_pid() -> int | None:
    """Get current daemon PID."""
    pid_file = Path.home() / "Library/Application Support/kimi-subconscious/daemon.pid"
    if not pid_file.exists():
        return None
    try:
        return int(pid_file.read_text().strip())
    except (ValueError, OSError):
        return None


def health_check() -> dict:
    """Run health check and return results."""
    result = subprocess.run(
        ["python", "-m", "kimi_subconscious.cli", "health", "--json"],
        capture_output=True,
        text=True,
        cwd="/Users/ikornii/Documents/_ai-warehouse/kimi-subconscious",
    )
    if result.returncode == 0:
        import json
        try:
            return json.loads(result.stdout)
        except json.JSONDecodeError:
            pass
    return {"overall": "unknown", "error": result.stderr}


def test_resurrection():
    """TEST 1: Kill daemon mid-operation, verify it can be resurrected.
    
    Steps:
        1. Note current daemon PID
        2. kill -9 <pid>
        3. Check health (should show stopped)
        4. Start daemon
        5. Verify health shows healthy
        6. Check logs for any data loss
    
    Expected: Daemon restarts cleanly, no data loss, health shows healthy.
    """
    print("=" * 60)
    print("STRESS TEST 1: Daemon Resurrection")
    print("=" * 60)
    
    # Get current PID
    pid = get_daemon_pid()
    if not pid:
        print("FAIL: No daemon running to test")
        return False
    
    print(f"1. Current daemon PID: {pid}")
    
    # Check pre-kill health
    health = health_check()
    print(f"2. Pre-kill health: {health.get('overall', 'unknown')}")
    
    # Kill with SIGKILL (uncatchable)
    print(f"3. Sending SIGKILL to {pid}...")
    try:
        os.kill(pid, signal.SIGKILL)
        print("   SIGKILL sent")
    except ProcessLookupError:
        print("   Process already dead")
    
    # Wait for death
    time.sleep(2)
    
    # Check post-kill health
    health = health_check()
    print(f"4. Post-kill health: {health.get('overall', 'unknown')}")
    
    if health.get('daemon_running'):
        print("FAIL: Daemon still running after SIGKILL")
        return False
    
    # Resurrect
    print("5. Resurrecting daemon...")
    result = subprocess.run(
        ["python", "-m", "kimi_subconscious.cli", "daemon", "start"],
        capture_output=True,
        text=True,
        cwd="/Users/ikornii/Documents/_ai-warehouse/kimi-subconscious",
    )
    
    if result.returncode != 0:
        print(f"FAIL: Failed to start daemon: {result.stderr}")
        return False
    
    time.sleep(3)
    
    # Check post-resurrection health
    health = health_check()
    print(f"6. Post-resurrection health: {health.get('overall', 'unknown')}")
    
    if health.get('overall') != 'healthy':
        print(f"FAIL: Health not healthy: {health}")
        return False
    
    print("\n✓ PASS: Daemon resurrection successful")
    return True


def test_fsevents_exhaustion():
    """TEST 2: Exhaust FSEvents watcher limit.
    
    Steps:
        1. Create 500+ directories with watchers
        2. Verify daemon doesn't crash
        3. Check if fallback to polling occurs
        4. Clean up
    
    Expected: Daemon survives, either with FSEvents or polling fallback.
    """
    print("=" * 60)
    print("STRESS TEST 2: FSEvents Exhaustion")
    print("=" * 60)
    print("WARNING: This test may temporarily impact system file watching")
    
    # Implementation would create many watchers
    print("TODO: Implement FSEvents exhaustion test")
    return None


def test_api_blackout():
    """TEST 3: Block API access, verify queue behavior.
    
    Steps:
        1. Block api.letta.com in /etc/hosts
        2. Trigger an insight
        3. Verify insight is queued locally
        4. Unblock API
        5. Verify queue flushes
    
    Expected: Insights queue locally, no crashes, flush when API returns.
    """
    print("=" * 60)
    print("STRESS TEST 3: API Blackout")
    print("=" * 60)
    print("WARNING: This test temporarily blocks Letta API access")
    
    print("TODO: Implement API blackout test")
    return None


def test_disk_full():
    """TEST 4: Simulate disk full condition.
    
    Steps:
        1. Create small tmpfs with size limit
        2. Fill it
        3. Try to write insight
        4. Verify graceful degradation
    
    Expected: No corruption, error logged, daemon survives.
    """
    print("=" * 60)
    print("STRESS TEST 4: Disk Full")
    print("=" * 60)
    
    print("TODO: Implement disk full test")
    return None


def test_restart_loop():
    """TEST 5: Trigger Phoenix restart cascade.
    
    Steps:
        1. Enable Phoenix mode
        2. Create condition where guidance triggers repeatedly
        3. Verify rate limiter kicks in at 3 restarts/min
        4. Verify no infinite loop
    
    Expected: Exactly 3 restarts, then rate limit message.
    """
    print("=" * 60)
    print("STRESS TEST 5: Phoenix Restart Loop")
    print("=" * 60)
    print("WARNING: This test will restart Kimi sessions")
    
    print("TODO: Implement restart loop test")
    return None


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        print("\nAvailable tests:")
        print("  resurrection")
        print("  fsevents")
        print("  api_blackout")
        print("  disk_full")
        print("  restart_loop")
        print("  all (runs all tests sequentially)")
        sys.exit(1)
    
    test_name = sys.argv[1]
    
    tests = {
        "resurrection": test_resurrection,
        "fsevents": test_fsevents_exhaustion,
        "api_blackout": test_api_blackout,
        "disk_full": test_disk_full,
        "restart_loop": test_restart_loop,
    }
    
    if test_name == "all":
        results = {}
        for name, func in tests.items():
            results[name] = func()
            print("\n" + "=" * 60 + "\n")
            time.sleep(2)
        
        print("\n" + "=" * 60)
        print("SUMMARY")
        print("=" * 60)
        for name, result in results.items():
            status = "✓ PASS" if result else "✗ FAIL" if result is False else "○ SKIP"
            print(f"{status}: {name}")
    
    elif test_name in tests:
        result = tests[test_name]()
        sys.exit(0 if result else 1)
    
    else:
        print(f"Unknown test: {test_name}")
        sys.exit(1)


if __name__ == "__main__":
    main()
