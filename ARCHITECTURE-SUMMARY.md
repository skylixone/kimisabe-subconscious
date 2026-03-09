# Universal Subconscious — Executive Summary

## The Core Problem

When you run `kimi` from anywhere (new project, subdir, random folder), the subconscious should:
1. **Know about the session** (outbound: session → Letta)
2. **Inject context** (inbound: Letta → session system prompt)

**Current state:** 2 works only if 1 happened AND Letta responded with guidance. That's fragile.

---

## The Three Fixes You Asked For

### Fix 1: Guaranteed SUBCONSCIOUS.md Creation
**Current:** File created only if Letta returns guidance  
**Target:** File created on EVERY session start, guidance or not

```python
# BEFORE (broken)
if guidance_messages:
    write_subconscious(guidance)  # Often never happens

# AFTER (fixed)
write_subconscious(guidance or [])  # Always happens
```

### Fix 2: Universal Project Resolution
**Current:** Uses exact CWD (`/the-job/k-search/` → separate project)  
**Target:** Walk up to find project root (`/the-job/` with `.git`)

```python
def resolve_project(cwd):
    for path in [cwd, cwd.parent, cwd.parent.parent, ...]:
        if (path / ".git").exists():
            return path  # Found root
    return cwd  # Orphan
```

### Fix 3: Kimi Injection Mechanism
**Current:** No injection — Kimi doesn't know to read SUBCONSCIOUS.md  
**Target:** Use `AGENTS.md` auto-loading

```
Daemon writes: ~/Projects/foo/AGENTS.md
Kimi auto-loads: ${KIMI_AGENTS_MD} injected into system prompt
Result: Subconscious context always present
```

---

## Key Architectural Decisions

### 1. AGENTS.md as Injection Vector
**Why:** Kimi already loads and injects `AGENTS.md` automatically  
**How:** Daemon writes/updates AGENTS.md with subconscious section  
**Benefit:** No Kimi CLI modifications needed

### 2. Two-Pronged Project Resolution
```
┌─────────────────────────────────────────┐
│  /Users/me/Projects/the-job/k-search/   │  ← CWD (session here)
│       │                                 │
│       ▼                                 │
│  /Users/me/Projects/the-job/            │  ← Root (marker: .git)
│       │                                 │
│       ▼                                 │
│  Project Hash: "the-job"                │  ← Stable identity
└─────────────────────────────────────────┘
```

### 3. Orphan Projects for "Anywhere" Sessions
```
CWD: /tmp/random-test/
No markers found → Orphan project
Stored: ~/.kimi/subconscious/orphans/<hash>/
Result: Still gets subconscious, just not in CWD
```

### 4. Resume Detection
```
Session exists + last_activity > 60s ago = RESUME
  ↓
Force subconscious regeneration
  ↓
Re-inject into Kimi context
```

---

## The Complete Flow (Universal)

```
Any Directory$ kimi
       │
       ▼
┌─────────────────────┐
│ 1. Resolve Project  │  ← Walk up, find .git, hash path
└──────────┬──────────┘
           │
           ▼
┌─────────────────────┐
│ 2. Create Context   │  ← Fetch memory blocks (Letta or cache)
└──────────┬──────────┘
           │
           ▼
┌─────────────────────┐
│ 3. Write Files      │  ← SUBCONSCIOUS.md + AGENTS.md
└──────────┬──────────┘
           │
           ▼
┌─────────────────────┐
│ 4. Kimi Loads       │  ← AGENTS.md auto-injected
└──────────┬──────────┘
           │
           ▼
┌─────────────────────┐
│ Session Active      │  ← Subconscious in system prompt
│ (Every Turn)        │
└──────────┬──────────┘
           │
           ▼
┌─────────────────────┐
│ 5. Sync to Letta    │  ← wire.jsonl changes detected
└──────────┬──────────┘
           │
           ▼
┌─────────────────────┐
│ 6. Update Context   │  ← Fresh SUBCONSCIOUS.md
└─────────────────────┘
```

---

## Critical Implementation Details

### AGENTS.md Format
```markdown
# Project Agents Configuration

[user content preserved above]

---

## Subconscious Context (AUTO-GENERATED - DO NOT EDIT)

> Last updated: 2026-03-09 16:30

### Memory Blocks
- **user_preferences**: "Use aerospace-ui for all HTML..."
- **project_context**: "This is a resume tailoring system..."

### Active Guidance
- Remember to verify dates unchanged
- Use `<br>` for logical phrase breaks

### Reference
- Agent: [Subconscious](https://app.letta.com/agents/...)
- Session: `48eef3a4...`
```

### File Location Strategy
```
Project Root/
├── .git/
├── AGENTS.md              ← Injected content (daemon writes)
├── SUBCONSCIOUS.md ──────→ ~/.kimi/subconscious/projects/<hash>/SUBCONSCIOUS.md
└── [other files]
```

### Resume Handling
```python
if session_exists and time_since_last > 60s:
    # This is a resume, not a new session
    force_fresh_subconscious = True
    notify_user = False  # Silent refresh
```

---

## Edge Cases Covered

| Scenario | Handling |
|----------|----------|
| `kimi` in `/tmp` | Orphan project created |
| `cd` mid-session | Detect switch, checkpoint old, load new |
| No network | Degrade to local cache, queue for later |
| Existing AGENTS.md | Merge, preserve user content |
| Concurrent sessions | Per-session guidance, shared memory blocks |
| Nested projects (monorepo) | Nearest marker wins (most specific) |

---

## Implementation Priority

```
P0 (Critical - Week 1)
├── Fix: Always write SUBCONSCIOUS.md
├── Fix: Project tree-walking
└── Fix: AGENTS.md injection

P1 (Important - Week 2)
├── Orphan project handling
├── Resume re-injection
└── Offline mode

P2 (Nice - Week 3+)
├── Mid-session project switch
├── Concurrent session optimization
└── Cross-project memory linking
```

---

## Success Criteria

- [ ] `kimi` from `/tmp` gets subconscious (orphan)
- [ ] `kimi` from `the-job/k-search/` gets `the-job` context (tree walk)
- [ ] Resume loads fresh subconscious (not stale)
- [ ] Every session has SUBCONSCIOUS.md within 1 second of start
- [ ] No manual `kimisub sync` needed for basic operation

---

*Ready for implementation review*
