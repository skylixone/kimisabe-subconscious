# Napkin — Kimi-Subconscious Project

> **Session Start:** 2026-03-08T17:18+02:00  
> **Current Focus:** P1 — Phoenix Restart Loop Test  
> **User Priority:** subconscious+vision integration MVP before stress tests

---

## Current State (As of Session Start)

### Daemon Health — ✅ OPERATIONAL
- **PID:** 58050 (running since ~13:19, uptime ~4h)
- **Heartbeat:** Active (every 30s)
- **Metrics:** Flushing every 5s
- **Log Rotation:** Working (daily files auto-created)
- **Session Logs:** 8,794 events captured (1.1MB + 97KB)

### Insight Pipeline — ⚠️ DETECTING BUT NOT SYNTHESIZING
- **241 insights** synced to Letta (100% sync rate)
- **Types detected:** 170 breakthrough, 40 correction, 28 repeated_error, 3 explicit_memory_request
- **CRITICAL GAP:** Memory blocks in Subconscious.af are EMPTY (templates only)

### Memory Block Status (Subconscious.af)
| Block | Content | Status |
|-------|---------|--------|
| block-0 | Role Definition | ✅ Populated (3,098 chars) |
| block-1 | Guidance | ❌ EMPTY (94 chars — template only) |
| block-2 | Pending Items | ❌ EMPTY (85 chars — template only) |
| block-3 | Project Context | ❌ EMPTY (72 chars — template only) |
| block-4 | Self-Improvement | ✅ Populated (1,677 chars) |
| block-5 | Session Patterns | ❌ EMPTY (62 chars — template only) |
| block-6 | Tool Guidelines | ✅ Populated (1,946 chars) |
| block-7 | User Preferences | ❌ EMPTY (114 chars — template only) |

**Problem:** Insights go to Letta, but Letta/Subconscious agent isn't writing back to blocks.

---

## Stress Tests Status

| Test | Status | Priority |
|------|--------|----------|
| resurrection | ✅ Implemented | Done |
| restart_loop | ⏳ TODO — **CURRENT FOCUS (P1)** | NOW |
| fsevents | TODO | Later |
| api_blackout | TODO | Later |
| disk_full | TODO | Later |
| corruption | TODO | Later |
| rapid_changes | TODO | Later |
| concurrent | TODO | Later |

---

## Phoenix System Architecture

**Files:**
- `/Users/ikornii/Documents/_ai-warehouse/kimi-subconscious/kimi_subconscious/phoenix.py` — Core logic

**Key Classes/Functions:**
- `PhoenixController` — Manages auto-restart
- `request_restart(project_hash, session_id, reason)` — Entry point
- `should_auto_restart()` — Check if phoenix_mode enabled in config
- `enable_phoenix_mode(enable)` — Toggle phoenix_mode

**Rate Limiting Config:**
```python
MAX_RESTARTS_PER_MINUTE = 3
RESTART_WINDOW_SECONDS = 60
```

**Idle Detection:**
- Reads `wire.jsonl` from Kimi sessions dir
- Looks for `TurnEnd` (safe to restart if < 5s old)
- Avoids `TurnBegin` / `StepBegin` (in progress)

**Restart Flow:**
1. Check rate limiting (max 3/min)
2. Check if Kimi idle (via wire.jsonl)
3. If idle: execute immediately
4. If busy: queue, retry on next check
5. Execute: spawn `kimi --continue`, kill old process

**Environment Variables Set on Restart:**
- `KIMI_PHOENIX_RESTART=1`
- `KIMI_PHOENIX_REASON=<reason>`

---

## What Needs Testing (P1: Restart Loop)

### Goals
1. Verify rate limiter caps at exactly 3 restarts/minute
2. Verify 4th+ restart is rejected with rate limit message
3. Verify no infinite loop possible
4. Verify idle detection works in practice

### Test Plan (restart_loop test)
1. Enable Phoenix mode (`phoenix_mode: true` in config)
2. Mock/fabricate conditions where guidance would trigger restart
3. Trigger 4+ restart requests rapidly
4. Verify exactly 3 execute, 4th gets rate limited
5. Verify state remains consistent

### Open Questions
- How to simulate "guidance triggers restart" without waiting for real guidance?
- Should we mock the insight→guidance flow or use real data?
- How to verify wire.jsonl parsing works on this system?

---

## Key Paths & Commands

**Daemon Control:**
```bash
cd /Users/ikornii/Documents/_ai-warehouse/kimi-subconscious
source .venv/bin/activate
python -m kimi_subconscious.cli daemon start
python -m kimi_subconscious.cli daemon stop
python -m kimi_subconscious.cli health
python -m kimi_subconscious.cli health --json
```

**Phoenix Control:**
```python
from kimi_subconscious.phoenix import enable_phoenix_mode, should_auto_restart
enable_phoenix_mode(True)  # Enable
should_auto_restart()       # Check status
```

**State Locations:**
- Config: `~/Library/Application Support/kimi-subconscious/config.json`
- PID: `~/Library/Application Support/kimi-subconscious/daemon.pid`
- Logs: `~/Library/Logs/kimi-subconscious/`
- Insights DB: `~/Library/Application Support/kimi-subconscious/projects/{hash}/insights.db`
- Kimi sessions: `~/.kimi/sessions/` (for wire.jsonl)

**Check Process:**
```bash
ps aux | grep "kimi_subconscious" | grep -v grep
```

---

## Blockers & Known Issues

### Critical Path Blocker (P0)
**Problem:** Memory blocks not hydrating despite insights being sent to Letta.

**Hypotheses:**
1. Letta agent not processing insights into block updates
2. Daemon not reading updated Subconscious.af after Letta writes
3. Race condition / timing issue
4. Letta conversation routing issue

**Not in scope for P1** — we're testing Phoenix mechanics independently.

---

## Session Continuity Notes

**If interrupted, resume with:**
1. Check daemon health: `python -m kimi_subconscious.cli health`
2. Read this napkin.md
3. Current task: Implement `test_restart_loop()` in `stress_tests.py`
4. Run with: `python stress_tests.py restart_loop`

**User Priority Reminder:**
- P0: subconscious+vision integration (guidance→blocks working)
- P1: Phoenix restart loop (current)
- P2: Remaining stress tests (after MVP functional)

---

## Git State
```
2df8eab Fix: Convert datetime to timestamp for JSON serialization in health check
8883f0a Add stress test suite (5 tests)
194ad04 Add auto-commit system for state persistence
11464bb Initial commit: Kimi Subconscious with observability & reliability fixes
```

Working tree clean (no uncommitted changes at session start).

---

## User Preferences (From VISION.md / napkin-shared.md)
- Laconic, information-dense communication
- Hybrid Product Designer / Design Engineer mindset
- Localhost feedback loops > text feedback for UI
- Present critique alongside proposals
- When user says "think bigger" — zoom out, demo-worthy > functional
- Review before declaring done (check for scrolls, alignment, responsive)

---

*Last updated: 2026-03-08T17:22+02:00*
*Next expected update: After restart_loop test implementation or interruption*
