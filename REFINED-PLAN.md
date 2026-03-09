# Universal Subconscious — Refined Implementation Plan

## TL;DR

**Yes,** any kimi instance from (almost) anywhere will use subconscious — with smart exclusions for safety/privacy.

| Scenario | Coverage | How |
|----------|----------|-----|
| `~/Projects/foo/` with `.git` | ✅ Full | Tree-walk finds root, AGENTS.md injected |
| `~/Projects/foo/bar/` subdir | ✅ Full | Tree-walk up to `foo/`, context injected |
| `~/random-folder/` no git | ✅ Full | Orphan project, context in daemon data |
| `/tmp/test-123/` | ✅ Full | Orphan, cleaned up after 30 days |
| `~/.ssh/`, `~/.aws/` | ❌ Excluded | Privacy protection |
| `/usr/share/docs/` | ❌ Excluded | Read-only, safety |

---

## The Critical Discovery

**AGENTS.md only loads from CWD — not parent directories.**

```python
# kimi_cli/soul/agent.py (verified)
paths = [
    work_dir / "AGENTS.md",  # ← ONLY CWD
    work_dir / "agents.md",
]
```

**Implication:** We must write `AGENTS.md` to wherever kimi starts, not just project root.

**Solution:** Two-file strategy
- `CWD/AGENTS.md` — Injection (ephemeral, rewritten per session)
- `Project/SUBCONSCIOUS.md` — Persistence (canonical, long-term)

---

## Architecture (Realistic)

```
User types: $ kimi (from ~/Projects/the-job/k-search/)
                    │
                    ▼
    ┌───────────────────────────────┐
    │ 1. Classify Location          │
    │    Safe? → Proceed            │
    │    Sensitive? → Skip          │
    └───────────────────────────────┘
                    │
                    ▼
    ┌───────────────────────────────┐
    │ 2. Resolve Project            │
    │    Walk: k-search → the-job   │
    │    Found: .git at the-job/    │
    └───────────────────────────────┘
                    │
                    ▼
    ┌───────────────────────────────┐
    │ 3. Fetch Context              │
    │    Letta API → Memory blocks  │
    │    Fallback → Local cache     │
    └───────────────────────────────┘
                    │
                    ▼
    ┌───────────────────────────────┐
    │ 4. Write Files                │
    │    k-search/AGENTS.md         │
    │    the-job/SUBCONSCIOUS.md    │
    └───────────────────────────────┘
                    │
                    ▼
    ┌───────────────────────────────┐
    │ 5. Kimi Starts                │
    │    AGENTS.md → System Prompt  │
    │    Subconscious Active ✓      │
    └───────────────────────────────┘
```

---

## Implementation Phases

### Phase 1: Foundation (This Week) — 95% Confidence

**Deliverable:** Works for 95% of real use cases

```
P1.1 Project Tree Resolver (1 day)
├── Walk up from CWD
├── Find .git, pyproject.toml, etc.
├── Return (hash, project_root)
└── Handle orphan (no markers)

P1.2 Eager File Generator (2 days)
├── ALWAYS write SUBCONSCIOUS.md
├── Write CWD/AGENTS.md (injection)
├── Write project/SUBCONSCIOUS.md (canonical)
└── Handle existing AGENTS.md (merge)

P1.3 Offline Mode (1 day)
├── Detect Letta unreachable
├── Fallback to local cache
├── Queue insights for later
└── Mark context as "stale"

P1.4 Resume Detection (1 day)
├── Check session exists + age
├── Force fresh injection
└── Silent operation
```

**Acceptance Criteria:**
- [ ] `kimi` from `~/Projects/foo/` gets subconscious
- [ ] `kimi` from `~/Projects/foo/bar/` gets same subconscious (tree walk)
- [ ] `kimi` from `~/random/` gets orphan subconscious
- [ ] `kimi --continue` gets fresh subconscious
- [ ] Works offline (degraded)

---

### Phase 2: Edge Cases (Next Week) — 70% Confidence

**Deliverable:** Robust handling of corner cases

```
P2.1 Read-Only Directories
├── Detect os.access(W_OK)
├── Skip file write
├── Use memory-only mode
└── Log gracefully

P2.2 Sensitive Directory Exclusion
├── Patterns: .ssh, .aws, .kube, etc.
├── Skip subconscious
└── Log: "Privacy protection active"

P2.3 AGENTS.md Merge Logic
├── Parse existing AGENTS.md
├── Find "Subconscious" section
├── Replace or append
├── Preserve user content
└── Backup before write

P2.4 Orphan Cleanup
├── Daily cron job
├── 30-day TTL
├── Archive insights
└── Delete files
```

**Acceptance Criteria:**
- [ ] `kimi` from `/tmp` works (orphan)
- [ ] `kimi` from `~/.ssh` excluded
- [ ] Existing AGENTS.md preserved
- [ ] Old orphans cleaned up

---

### Phase 3: Advanced (Future) — 50% Confidence

**Deliverable:** Complex scenarios (may defer)

```
P3.1 Mid-Session CD (complex)
├── Poll CWD periodically
├── Detect project change
├── Checkpoint old project
└── Inject new context

P3.2 Concurrent Sessions
├── File locking
├── Per-session guidance
└── Race condition handling

P3.3 Performance Optimization
├── Async resolution
├── Cached tree walks
└── Batch API calls
```

---

## Confidence Summary

### What I'm Confident About (90%+)

| Item | Confidence | Why |
|------|------------|-----|
| Tree-walking resolver | 95% | Simple pattern, proven |
| Always-write SUBCONSCIOUS.md | 95% | One-line fix |
| AGENTS.md injection | 90% | Verified in kimi source |
| Orphan projects | 90% | Standard fallback |
| Phase 1 completion | 90% | Clear scope, proven patterns |

### What I'm Not Confident About (60-80%)

| Item | Confidence | Risk |
|------|------------|------|
| AGENTS.md merge | 70% | Parsing edge cases |
| Concurrent sessions | 70% | Race conditions |
| Read-only fallback UX | 70% | Degraded experience |
| Orphan cleanup | 65% | May delete wanted data |
| Mid-session CD | 60% | Complex detection |
| Performance at scale | 65% | Unmeasured |

### What I Know Won't Work (By Design)

| Item | Reason |
|------|--------|
| System dirs (/usr, etc) | Read-only, safety exclusion |
| Sensitive dirs (.ssh) | Privacy protection |
| CI/automation | Out of scope |

---

## Risk Matrix

| Risk | Prob | Impact | Mitigation |
|------|------|--------|------------|
| Merge corrupts AGENTS.md | Med | High | Backup, defensive parsing |
| Cleanup deletes wanted orphans | Med | Med | 30d TTL, archive first |
| Performance too slow | Low | Med | Async, caching |
| Kimi CLI changes | Low | High | Version detection |

---

## Recommendation

**Start Phase 1 immediately.**

- High confidence (90%+)
- Delivers 95% of value
- Architecture supports Phase 2/3 expansion
- Edge cases can be addressed incrementally

**The "universal" vision is achievable** — with smart exclusions for safety and privacy.

---

## Files Delivered

| File | Purpose |
|------|---------|
| `UNIVERSAL-VISION.md` | Complete analysis, edge cases, confidence assessment |
| `REFINED-PLAN.md` | This file — implementation roadmap |
| `ARCHITECTURE.md` | Technical specification (30KB) |
| `ARCHITECTURE-SUMMARY.md` | Quick reference |
| `docs/architecture-visual.html` | Visual diagram |

---

*Ready to implement Phase 1?*
