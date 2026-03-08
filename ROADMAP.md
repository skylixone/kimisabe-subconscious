# Roadmap to Kimisabe 1.0

> Kimisabe = Kimi-Subconscious + VISION.md integration  
> Goal: Persistent, cross-session memory that improves every interaction

---

## Current State (Alpha)

✅ **Daemon operational** — watches Kimi sessions, detects insights  
✅ **Letta integration** — sends insights, receives guidance  
✅ **Memory blocks** — 8 blocks from Subconscious.af active  
✅ **Phoenix mode** — auto-restart when guidance arrives  
✅ **Stress tests** — resurrection, restart_loop passing  
✅ **Integration tests** — agent, blocks, formatting verified  

**Last verified:** 2026-03-08 — guidance block wrote first content (500 chars)

---

## 1.0 Definition of Done

Kimisabe 1.0 is achieved when:

1. **Every Kimi session** on this machine starts with subconscious context
2. **Every session contributes** insights that improve future sessions  
3. **Guidance is actionable** — not generic, but specific to current work
4. **Zero manual intervention** — setup once, runs forever
5. **Destructive tests pass** — survives crashes, API outages, disk issues

---

## Phase 1: Hardening (Current → 1-2 weeks)

**Goal:** Make it unbreakable

### P1.1 Remaining Stress Tests
- [ ] `fsevents` — Exhaust FSEvents watcher limit
- [ ] `api_blackout` — Block API, verify queue behavior  
- [ ] `disk_full` — Simulate disk full condition
- [ ] `corruption` — Corrupt state files, verify recovery
- [ ] `rapid_changes` — 1000 file changes/second
- [ ] `concurrent` — Multiple sessions simultaneously

### P1.2 Error Recovery
- [ ] Auto-retry with exponential backoff for Letta API
- [ ] Queue insights locally when API unavailable
- [ ] Graceful degradation when blocks are full
- [ ] Detect and recover from partial writes

### P1.3 Monitoring
- [ ] Health dashboard (simple HTML)
- [ ] Metrics export (Prometheus format)
- [ ] Alert on insight backlog > 100
- [ ] Alert on daemon crash

**Exit Criteria:** All stress tests passing, 7 days uptime without restart

---

## Phase 2: Intelligence (2-4 weeks)

**Goal:** Make it actually useful

### P2.1 Insight Quality
- [ ] Tune detection thresholds (current: too many false positives?)
- [ ] Add insight deduplication (same correction 3x = preference)
- [ ] Cross-session pattern detection
- [ ] Time-based insights ("You always work on X at 9am")

### P2.2 Block Population
- [ ] guidance: Write when genuinely useful
- [ ] user_preferences: Extract from corrections
- [ ] session_patterns: Detect recurring behaviors  
- [ ] pending_items: Track TODOs across sessions
- [ ] project_context: Auto-populate from codebase

### P2.3 Context Injection
- [ ] Format blocks for optimal Kimi consumption
- [ ] Prioritize by recency and relevance
- [ ] Trim old content intelligently
- [ ] Inject at session start (VISION.md style)

**Exit Criteria:** User reports "it remembered X from last week" unprompted

---

## Phase 3: Distribution (4-6 weeks)

**Goal:** Make it portable

### P3.1 Installation
- [ ] One-command install: `curl ... | bash`
- [ ] Homebrew formula
- [ ] pip install with all deps
- [ ] Auto-detect Kimi installation

### P3.2 Configuration
- [ ] `kimisabe setup` interactive wizard
- [ ] Validate Letta credentials
- [ ] Import Subconscious.af automatically
- [ ] Test connection end-to-end

### P3.3 Documentation
- [ ] Architecture diagram
- [ ] Troubleshooting guide
- [ ] Contributing guide
- [ ] Video walkthrough

**Exit Criteria:** New user goes from "never heard of it" to "working" in < 10 minutes

---

## Phase 4: Ecosystem (6+ weeks)

**Goal:** Make it extensible

### P4.1 Custom Blocks
- [ ] User-defined memory blocks
- [ ] Per-project block templates
- [ ] Block versioning/migration

### P4.2 Integrations
- [ ] VS Code extension (show guidance inline)
- [ ] Slack/Discord bot ("Kimi is working on...")
- [ ] Notion/Obsidian sync

### P4.3 Advanced Features
- [ ] Multi-agent support (different personalities)
- [ ] Plugin system for insight detectors
- [ ] Web UI for memory management

---

## Milestones

| Milestone | Date Target | Success Criteria |
|-----------|-------------|------------------|
| Alpha → Beta | +2 weeks | All stress tests pass, 7d uptime |
| Beta → RC | +4 weeks | User reports usefulness unprompted |
| RC → 1.0 | +6 weeks | External user installs successfully |

---

## Success Metrics

- **Uptime:** > 99% (measured weekly)
- **Insight detection:** > 80% precision, > 60% recall
- **Block growth:** Guidance written at least once per day
- **User satisfaction:** "Would miss it if gone" = yes

---

*This roadmap is a living document. Update as priorities shift.*
