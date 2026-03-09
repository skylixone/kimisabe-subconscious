# Universal Subconscious — Final Vision

## The Core Question

> "Will ANY kimi instance started from ANYWHERE on this machine make use of subconscious in and out?"

**Short answer:** Yes, with qualifications. The architecture supports universal coverage, but "anywhere" has edge cases that require explicit handling.

---

## What "Universal" Actually Means

### The Universe of Locations

```
Machine Root
├── /Users/ikornii/              ← Home (primary workspace)
│   ├── Projects/                ← Git repos (25 found)
│   ├── Documents/               ← Documents
│   ├── .ssh/, .aws/, .kube/     ← SENSITIVE (special handling)
│   └── Downloads/, Desktop/     ← Transient
├── /tmp/, /var/tmp/             ← TEMP (volatile)
├── /usr/, /etc/, /bin/          ← SYSTEM (read-only)
├── /Volumes/External/           ← EXTERNAL
└── /Volumes/NetworkShare/       ← NETWORK
```

### Confidence Matrix

| Location Type | Coverage | Confidence | Notes |
|--------------|----------|------------|-------|
| Home git repos | ✅ Full | **95%** | Primary use case, well-tested |
| Home non-git dirs | ✅ Full | **90%** | Orphan projects work |
| /tmp, /var/tmp | ⚠️ Partial | **70%** | Volatile, may be cleared |
| External drives | ✅ Full | **85%** | Works, but path changes when unmounted |
| Network mounts | ✅ Full | **75%** | Latency issues, may be slow |
| System dirs (/usr, etc) | ❌ Excluded | **95%** | Read-only, safety exclusion |
| Sensitive dirs (.ssh) | ❌ Excluded | **95%** | Privacy protection |
| CI/automation | ⚠️ Depends | **60%** | Needs special session detection |

---

## Critical Technical Reality

### AGENTS.md Only Loads from CWD

**What I verified:**
```python
# From kimi_cli/soul/agent.py (line 56-66)
async def load_agents_md(work_dir: KaosPath) -> str | None:
    paths = [
        work_dir / "AGENTS.md",      # ← Only CWD
        work_dir / "agents.md",
    ]
    # No parent directory walking!
```

**Implication:**
- To inject subconscious, we MUST write `AGENTS.md` to the CWD
- Writing only to project root doesn't work if CWD is a subdir

**Solution — Two-File Strategy:**
```
Starting session in: ~/Projects/foo/src/components/
                              │
        ┌─────────────────────┼─────────────────────┐
        ▼                     ▼                     ▼
┌──────────────┐     ┌──────────────┐     ┌──────────────┐
│  CWD         │     │  Project     │     │  Daemon      │
│  Injection   │     │  Persistence │     │  Data        │
├──────────────┤     ├──────────────┤     ├──────────────┤
│ AGENTS.md    │     │ SUBCONSCIOUS │     │ insights.db  │
│ (ephemeral)  │     │ .md          │     │ conversations│
│              │     │ (canonical)  │     │ .json        │
└──────────────┘     └──────────────┘     └──────────────┘
       │                    │                    │
       ▼                    ▼                    ▼
  Kimi loads            Long-term           Backend
  immediately           storage             storage
```

---

## Refined Universal Architecture

### The Real Flow (Honest Version)

```
Terminal$ kimi (from anywhere)
    │
    ▼
┌─────────────────────────────────────────────────────────────┐
│ 1. LOCATION CLASSIFIER                                       │
│    ─────────────────────                                     │
│    Check: Is this location safe/supported?                   │
│    • Read-only? → Skip file write, use memory only           │
│    • Sensitive? → Skip for privacy                           │
│    • System dir? → Skip (safety)                             │
│    • OK? → Proceed                                           │
└─────────────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────────────┐
│ 2. PROJECT RESOLUTION (Tree Walk)                            │
│    ───────────────────────────────                           │
│    CWD: ~/Projects/the-job/k-search/                         │
│    Walk: k-search/ → the-job/ (found .git)                   │
│    Project Root: ~/Projects/the-job/                         │
│    Hash: 3250a28c20888252d12dd3287b0bc993                    │
└─────────────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────────────┐
│ 3. CONTEXT GENERATION (Always)                               │
│    ────────────────────────────                              │
│    Fetch from Letta:                                         │
│    • Memory blocks (guidance, preferences, etc)              │
│    • Active guidance (if any)                                │
│                                                              │
│    Fallback (if offline):                                    │
│    • Load from local cache                                   │
│    • Mark as "stale"                                         │
└─────────────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────────────┐
│ 4. DUAL FILE WRITE                                           │
│    ─────────────────                                         │
│    A. CWD/AGENTS.md (for Kimi injection)                     │
│       - Write subconscious context                           │
│       - Mark as auto-generated                               │
│       - Preserve existing user content (merge)               │
│                                                              │
│    B. Project/SUBCONSCIOUS.md (for persistence)              │
│       - Write full canonical context                         │
│       - Add to .gitignore                                    │
│       - Symlink from daemon data dir                         │
└─────────────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────────────┐
│ 5. KIMI SESSION (Subconscious Loaded)                        │
│    ───────────────────────────────────                       │
│    System prompt includes:                                   │
│    ${KIMI_AGENTS_MD} → "## Subconscious Context..."          │
│                                                              │
│    [Every turn detected]                                     │
│    wire.jsonl change → Daemon sync → Update context          │
└─────────────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────────────┐
│ 6. CLEANUP (Session End)                                     │
│    ─────────────────────                                     │
│    If CWD AGENTS.md is auto-generated:                       │
│    • Option A: Remove it (clean)                             │
│    • Option B: Keep it with "last session" marker            │
└─────────────────────────────────────────────────────────────┘
```

---

## Edge Cases & Handling (Detailed)

### Case 1: Read-Only Directory

**Scenario:** `kimi` started in `/usr/local/docs` (read-only)

**Handling:**
```python
if not os.access(cwd, os.W_OK):
    # Can't write AGENTS.md
    # Option A: Skip file injection
    # Option B: Write to /tmp and symlink (complex)
    
    # RECOMMENDED: Use memory-only mode
    logger.info(f"Read-only directory: {cwd}")
    logger.info("Using memory-only subconscious (no file persistence)")
    
    # Still sync to Letta, just don't write files
    return MemoryOnlyMode()
```

**Confidence:** 90% — Fallback works, but session loses file-based persistence.

---

### Case 2: Sensitive Directory

**Scenario:** `kimi` started in `~/.ssh` or `~/.aws`

**Handling:**
```python
SENSITIVE_PATTERNS = [
    r"\.ssh",
    r"\.aws",
    r"\.kube",
    r"\.gnupg",
    r"\.password-store",
    r".*secret.*",
    r".*credential.*",
]

if any(re.match(pattern, str(cwd)) for pattern in SENSITIVE_PATTERNS):
    logger.warning(f"Sensitive directory detected: {cwd}")
    logger.warning("Skipping subconscious to protect privacy")
    
    # Still allow session, just without memory
    return DisabledMode(reason="privacy")
```

**Confidence:** 95% — Conservative approach protects user.

---

### Case 3: Nested Git Repos (Monorepo)

**Scenario:** 
```
/monorepo/.git
/monorepo/frontend/.git
/monorepo/backend/.git
```

Started in: `/monorepo/frontend/src/`

**Handling:**
```python
def resolve_project(cwd):
    """Nearest marker wins (most specific)."""
    for path in [cwd] + list(cwd.parents):
        markers = [p for p in self.ROOT_MARKERS if (path / p).exists()]
        if markers:
            return path, markers  # First match = nearest
```

**Result:** `frontend/` treated as separate project from `monorepo/`

**Confidence:** 85% — Correct behavior, but may surprise users.

---

### Case 4: Mid-Session Directory Change

**Scenario:** 
```bash
$ cd ~/project-a
$ kimi
[session active]
$ cd ~/project-b  # Different project!
$ [continue working]
```

**Handling:**
```python
def detect_project_switch():
    current_cwd = get_current_working_directory()
    current_hash = resolve_project(current_cwd)
    
    if current_hash != session_project_hash:
        logger.info(f"Project switch detected!")
        logger.info(f"Checkpointing {session_project_hash[:8]}...")
        
        # Save current context
        checkpoint_session()
        
        # Load new context
        activate_project(current_hash)
        
        # Update injection
        rewrite_agents_md(current_cwd)
```

**Confidence:** 60% — Technically feasible, but detecting CWD change in running kimi session is tricky (requires polling or hooks). **May defer to Phase 2.**

---

### Case 5: Concurrent Sessions

**Scenario:**
- Terminal 1: `kimi` in `~/project-a`
- Terminal 2: `kimi` in `~/project-a` (same project!)
- Terminal 3: `kimi` in `~/project-b`

**Handling:**
```python
class ConcurrentSessionManager:
    def get_context(self, session_id: str, project_hash: str):
        # Shared: Memory blocks (read-only)
        shared_memory = self.letta.get_memory_blocks(project_hash)
        
        # Private: Session-specific guidance
        private_guidance = self.state.get_session_guidance(session_id)
        
        return SessionContext(
            shared=shared_memory,
            private=private_guidance,
        )
```

**Confidence:** 80% — Works, but race conditions possible if both sessions write AGENTS.md simultaneously.

---

### Case 6: Orphan Accumulation

**Scenario:** User starts many sessions in random temp directories.

**Handling:**
```python
ORPHAN_TTL_DAYS = 30

def cleanup_orphans():
    """Daily cleanup of old orphan projects."""
    for orphan in list_orphan_projects():
        last_activity = get_last_activity(orphan)
        
        if days_since(last_activity) > ORPHAN_TTL_DAYS:
            logger.info(f"Cleaning up orphan: {orphan[:8]}...")
            archive_orphan(orphan)  # Keep insights, remove files
            delete_orphan(orphan)
```

**Confidence:** 85% — Cleanup works, but may delete "forgotten but important" sessions.

---

## What I'm Confident About

| Aspect | Confidence | Rationale |
|--------|------------|-----------|
| Tree-walking project resolution | **95%** | Simple, proven pattern |
| Always-write SUBCONSCIOUS.md | **95%** | One-line fix, low risk |
| AGENTS.md injection mechanism | **90%** | Verified in kimi source |
| Orphan project handling | **90%** | Standard fallback pattern |
| Offline mode | **85%** | Queue + cache pattern |
| Bidirectional sync | **85%** | Current daemon works, needs tuning |

---

## What I'm NOT Confident About

| Aspect | Confidence | Concerns |
|--------|------------|----------|
| Mid-session `cd` detection | **60%** | Requires polling or kimi CLI hooks |
| AGENTS.md merge logic | **65%** | Complex to preserve user content correctly |
| Concurrent session safety | **70%** | File write races, needs locking |
| Read-only directory fallback | **70%** | UX is degraded (no file persistence) |
| CI/automation environments | **50%** | Unknown behavior in non-interactive shells |
| Performance at scale | **65%** | Tree-walking + Letta API on every session start |
| Long-term storage growth | **60%** | Orphans accumulate, need aggressive cleanup |
| Phoenix restart reliability | **70%** | Process detection, timing issues |

---

## Revised Implementation Plan

### Phase 1: Foundation (Week 1) — HIGH CONFIDENCE

**Goal:** Make subconscious work for the 80% case (home directory projects)

```
✅ P1.1: Project Tree Resolver
    - Walk up from CWD looking for .git
    - Return (project_hash, project_root)
    - Handle orphan case

✅ P1.2: Eager File Generator  
    - ALWAYS write SUBCONSCIOUS.md
    - Write to CWD/AGENTS.md (for injection)
    - Write to project_root/SUBCONSCIOUS.md (for persistence)

✅ P1.3: Offline Fallback
    - If Letta unreachable, use local cache
    - Queue insights for later sync
    - Mark context as "stale"
```

**Deliverable:** Subconscious works from any home directory location.

---

### Phase 2: Polish (Week 2) — MEDIUM CONFIDENCE

**Goal:** Handle edge cases, improve reliability

```
⚠️ P2.1: AGENTS.md Merge Logic
    - Parse existing AGENTS.md
    - Preserve user content
    - Inject subconscious section
    - Handle malformed files gracefully

⚠️ P2.2: Read-Only & Sensitive Directory Handling
    - Detect read-only dirs
    - Detect sensitive patterns
    - Graceful degradation

⚠️ P2.3: Resume Detection
    - Detect resumed sessions
    - Force fresh context injection
    - Silent (no user notification)

⚠️ P2.4: Orphan Cleanup
    - Daily cleanup job
    - Configurable TTL (default 30 days)
    - Archive before delete
```

**Deliverable:** Robust handling of edge cases.

---

### Phase 3: Advanced (Week 3+) — LOW CONFIDENCE

**Goal:** Handle complex scenarios (may defer based on Phase 2 results)

```
❓ P3.1: Mid-Session Project Switch
    - Poll CWD during session
    - Detect directory changes
    - Checkpoint + switch context
    [MAY DEFER: Complex, edge case]

❓ P3.2: Concurrent Session Safety
    - File locking for AGENTS.md
    - Per-session private guidance
    [MAY DEFER: Rare case]

❓ P3.3: Performance Optimization
    - Async project resolution
    - Cached tree walking
    - Batch Letta API calls
    [MAY DEFER: Only if slow]
```

---

## Success Metrics (Realistic)

| Metric | Baseline | Target (Phase 1) | Target (Phase 2) |
|--------|----------|------------------|------------------|
| Home dir coverage | ~60% | 95% | 98% |
| Resume injection | ~30% | 80% | 95% |
| File write success | ~70% | 90% | 95% |
| Orphan handling | 0% | 90% | 95% |
| Offline degradation | Crash | Graceful | Graceful |

---

## Risk Mitigation

| Risk | Probability | Impact | Mitigation |
|------|-------------|--------|------------|
| AGENTS.md merge corrupts user file | Medium | High | Backup before merge, parse defensively |
| Orphan cleanup deletes wanted data | Medium | Medium | 30-day TTL, archive before delete |
| Performance too slow | Low | Medium | Async processing, caching |
| Privacy leak in sensitive dir | Low | High | Explicit exclusion list |
| Kimi CLI changes injection mechanism | Low | High | Version detection, fallback modes |

---

## Final Vision Summary

### What WILL Work (High Confidence)

✅ **Any kimi session from home directory** — Full subconscious in/out  
✅ **Git repositories anywhere** — Tree-walking finds project root  
✅ **Resume/continue** — Fresh context injected  
✅ **Offline mode** — Graceful fallback to cache  
✅ **Orphan directories** — Still get subconscious (stored in daemon data)  

### What MIGHT Work (Medium Confidence)

⚠️ **Mid-session directory changes** — Needs complex detection  
⚠️ **Read-only directories** — Works but without file persistence  
⚠️ **Concurrent sessions** — Works but may have race conditions  
⚠️ **External/network drives** — Works but path may change  

### What WON'T Work (By Design)

❌ **Sensitive directories (.ssh, .aws)** — Excluded for privacy  
❌ **System directories (/usr, /etc)** — Excluded for safety  
❌ **CI/automation** — May work but not explicitly supported  

---

## Recommendation

**Proceed with Phase 1** — The 80% case (home directory projects) is high-confidence and delivers immediate value. The architecture supports expansion to edge cases in Phase 2/3.

**The vision is achievable:** Universal subconscious coverage for practical use cases, with graceful degradation for edge cases.

---

*Document version: 1.0*  
*Confidence assessment based on: source code analysis, architectural patterns, prototype feasibility*  
*Last updated: 2026-03-09*
