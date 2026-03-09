# Kimi Subconscious — Universal Memory Architecture

> **Goal:** Every `kimi` session started from terminal, regardless of location, must have full bidirectional subconscious integration.

---

## 1. Core Principles

| Principle | Enforcement |
|-----------|-------------|
| **Universal** | Every session gets subconscious. No exceptions. |
| **Bidirectional** | Out: session → Letta. In: Letta → session. |
| **Location-Agnostic** | Works from any directory, nested subdirs, outside projects. |
| **Eager** | Create `SUBCONSCIOUS.md` on first sync, not just when guidance arrives. |
| **Resilient** | Degrades gracefully (offline, API failures, orphan sessions). |

---

## 2. Current Architecture Gaps

```
┌─────────────────────────────────────────────────────────────────┐
│  CURRENT FLOW (BROKEN)                                          │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  Terminal: ~/Projects/foo/subdir$ kimi                          │
│       │                                                         │
│       ▼                                                         │
│  ┌─────────────┐    ┌─────────────┐    ┌─────────────┐         │
│  │ wire.jsonl  │───▶│   Daemon    │───▶│    Letta    │         │
│  │  created    │    │   watches   │    │   (guidance)│         │
│  └─────────────┘    └─────────────┘    └──────┬──────┘         │
│       │                              NO GUIDANCE │              │
│       ▼                              = NO FILE   ▼              │
│  Session starts                           ┌─────────────┐       │
│  WITHOUT subconscious.md                  │ SUBCONSCIOUS│       │
│  (or with stale one)                      │  NOT CREATED│       │
│                                           └─────────────┘       │
└─────────────────────────────────────────────────────────────────┘
```

**Problems:**
1. `SUBCONSCIOUS.md` only created if Letta returns guidance
2. No file = no injection into Kimi system prompt
3. Project resolution uses exact CWD (breaks in subdirs like `k-search/`)
4. Orphan sessions (started outside any project) get no context
5. Resume doesn't trigger re-injection of updated memories

---

## 3. Target Architecture

```
┌─────────────────────────────────────────────────────────────────────────┐
│  UNIVERSAL SUBCONSCIOUS FLOW                                            │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │  LIFECYCLE HOOKS (New)                                          │   │
│  │  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐          │   │
│  │  │ SessionStart │  │   TurnEnd    │  │ SessionEnd   │          │   │
│  │  │   (eager)    │  │  (incremental)│  │  (checkpoint) │          │   │
│  │  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘          │   │
│  └─────────┼────────────────┼────────────────┼──────────────────┘   │
│            │                │                │                        │
│            ▼                ▼                ▼                        │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │                     UNIVERSAL DAEMON                             │   │
│  │  ┌─────────────┐    ┌─────────────┐    ┌─────────────────────┐  │   │
│  │  │  Project    │    │   Session   │    │   SUBCONSCIOUS.md   │  │   │
│  │  │  Resolver   │───▶│   Syncer    │───▶│   Generator         │  │   │
│  │  │ (walk tree) │    │ (wire.jsonl)│    │   (ALWAYS write)    │  │   │
│  │  └─────────────┘    └──────┬──────┘    └─────────────────────┘  │   │
│  │                            │                                     │   │
│  │                            ▼                                     │   │
│  │                     ┌─────────────┐                              │   │
│  │                     │    Letta    │                              │   │
│  │                     │   (memory)  │                              │   │
│  │                     └──────┬──────┘                              │   │
│  │                            │                                     │   │
│  │              ┌─────────────┴─────────────┐                       │   │
│  │              ▼                           ▼                       │   │
│  │    ┌─────────────────┐      ┌─────────────────┐                 │   │
│  │    │  Guidance Back  │      │  Memory Blocks  │                 │   │
│  │    │  (if any)       │      │  (always read)  │                 │   │
│  │    └─────────────────┘      └─────────────────┘                 │   │
│  └─────────────────────────────────────────────────────────────────┘   │
│                              │                                         │
│                              ▼                                         │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │                     KIMI SESSION                                 │   │
│  │  ┌───────────────────────────────────────────────────────────┐  │   │
│  │  │  SYSTEM PROMPT INJECTION (via AGENTS.md mechanism)        │  │   │
│  │  │                                                           │  │   │
│  │  │  ${KIMI_AGENTS_MD}  ──▶  "## Subconscious Context"       │  │   │
│  │  │                              - Memory blocks              │  │   │
│  │  │                              - Active guidance            │  │   │
│  │  │                              - Session patterns           │  │   │
│  │  └───────────────────────────────────────────────────────────┘  │   │
│  └─────────────────────────────────────────────────────────────────┘   │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## 4. Component Specifications

### 4.1 Universal Project Resolver

**Problem:** Current code uses exact CWD. Breaks in subdirectories.

**Solution:** Walk up directory tree to find project root.

```python
class ProjectResolver:
    """Resolve project root from any working directory."""
    
    ROOT_MARKERS = [
        ".git",           # Git repository
        "pyproject.toml", # Python project
        "package.json",   # Node project
        "Cargo.toml",     # Rust project
        "go.mod",         # Go project
        "SUBCONSCIOUS.md", # Explicit marker
        ".subconscious",  # Hidden marker file
    ]
    
    def resolve(self, cwd: Path) -> tuple[str, Path]:
        """
        Returns (project_hash, project_root).
        
        Strategy:
        1. Walk up from CWD looking for ROOT_MARKERS
        2. If found, use that directory as project root
        3. If not found, use CWD itself (orphan project)
        4. Hash the resolved project root path
        """
        current = cwd.resolve()
        
        # Walk up looking for markers
        for path in [current] + list(current.parents):
            if any((path / marker).exists() for marker in self.ROOT_MARKERS):
                return self._hash_path(path), path
        
        # No marker found - use CWD as orphan project
        return self._hash_path(current), current
    
    def _hash_path(self, path: Path) -> str:
        """Consistent hash for project path."""
        return hashlib.md5(str(path).encode()).hexdigest()
```

**Example:**
```
CWD: /Users/me/Projects/the-job/k-search/
Markers found: /Users/me/Projects/the-job/.git
Resolved: project_hash("/Users/me/Projects/the-job")
```

---

### 4.2 Eager SUBCONSCIOUS.md Generator

**Problem:** File only created when guidance arrives.

**Solution:** Always create on first sync, with or without guidance.

```python
class SubconsciousGenerator:
    """Generate SUBCONSCIOUS.md content."""
    
    def generate(self, project_root: Path, force: bool = False) -> str:
        """
        Generate SUBCONSCIOUS.md content.
        
        ALWAYS includes:
        - Agent context (Letta agent URL/ID)
        - Memory blocks (from Letta, or empty markers)
        - Project metadata
        
        OPTIONALLY includes:
        - Active guidance (if Letta responded)
        - Recent insights (from local DB)
        """
        lines = [
            "# Subconscious",
            "",
            "> Auto-generated memory layer for Kimi sessions.",
            "> This file is read on session start and updated after each turn.",
            "",
            "---",
            "",
            "## Active Context",
            "",
            f"**Project:** `{project_root.name}`  ",
            f"**Path:** `{project_root}`  ",
            f"**Session:** `{self.session_id[:8]}...`  ",
            "",
        ]
        
        # Always fetch memory blocks (even if empty)
        blocks = self._fetch_memory_blocks() or []
        lines.extend(self._format_memory_blocks(blocks))
        
        # Fetch guidance if available
        guidance = self._fetch_guidance()
        if guidance:
            lines.extend(self._format_guidance(guidance))
        
        # Always include recent patterns from local DB
        patterns = self._fetch_local_patterns()
        lines.extend(self._format_patterns(patterns))
        
        return "\n".join(lines)
```

**Key Change:** File is written on `SessionStart` AND `TurnEnd`, not just when guidance arrives.

---

### 4.3 Kimi Injection Mechanism

**Problem:** Kimi doesn't know to read SUBCONSCIOUS.md.

**Solution:** Leverage existing `AGENTS.md` injection + write to Kimi's session directory.

```python
class KimiInjector:
    """Inject subconscious into Kimi system prompt."""
    
    def inject(self, session_id: str, project_root: Path):
        """
        Make subconscious context available to Kimi.
        
        Two-pronged approach:
        1. Write AGENTS.md in project root (Kimi auto-loads this)
        2. Write to Kimi's session directory (backup mechanism)
        """
        content = self._build_injection_content()
        
        # Method 1: AGENTS.md in project root
        agents_md = project_root / "AGENTS.md"
        if not agents_md.exists():
            # Create fresh AGENTS.md with subconscious section
            self._write_agents_md(agents_md, content)
        else:
            # Update existing AGENTS.md, preserving user content
            self._update_agents_md(agents_md, content)
        
        # Method 2: Session-local injection (guarantee)
        # Write to Kimi's session directory
        session_dir = self._get_kimi_session_dir(session_id)
        if session_dir:
            subconscious_link = session_dir / "subconscious_context.md"
            subconscious_link.write_text(content)
    
    def _build_injection_content(self) -> str:
        """Build the content to inject into Kimi's prompt."""
        return f"""## Subconscious Context

You have access to persistent memory through the Subconscious system.

### Memory Blocks
{self._format_memory_blocks()}

### Active Guidance
{self._format_guidance()}

### Usage Instructions
- Check memory before making assumptions about preferences
- Update memory when you learn something important
- Reference memory explicitly: "Per your subconscious..."
"""
```

**Why AGENTS.md:**
- Kimi already loads and injects `AGENTS.md` into system prompt
- No CLI modifications needed
- Works with `--continue` (resume)

---

### 4.4 Universal Session Tracker

**Problem:** Sessions outside projects are ignored.

**Solution:** Create "orphan" projects for unmatched sessions.

```python
class UniversalSessionTracker:
    """Track ALL kimi sessions, regardless of location."""
    
    ORPHAN_PREFIX = "orphan_"
    
    def track_session(self, session_id: str, cwd: Path) -> str:
        """
        Track a session, creating orphan project if needed.
        
        Returns: project_hash
        """
        project_hash, project_root = self.resolver.resolve(cwd)
        
        # Check if this is an orphan (no recognizable project)
        is_orphan = self._is_orphan(project_root)
        
        if is_orphan:
            # Create orphan project entry
            orphan_hash = f"{self.ORPHAN_PREFIX}{project_hash}"
            self._create_orphan_project(orphan_hash, cwd)
            return orphan_hash
        
        return project_hash
    
    def _create_orphan_project(self, orphan_hash: str, cwd: Path):
        """
        Create a virtual project for orphan sessions.
        
        Orphan projects:
        - Get their own Letta conversation
        - Store memories in daemon data dir (not CWD)
        - Are named by path hash (stable across sessions)
        """
        project_dir = self.state.get_project_dir(orphan_hash)
        
        # Create SUBCONSCIOUS.md in daemon data dir
        sub_path = project_dir / "SUBCONSCIOUS.md"
        
        # Store metadata about original location
        metadata = {
            "original_cwd": str(cwd),
            "created_at": datetime.now().isoformat(),
            "type": "orphan",
        }
        self.state.save_orphan_metadata(orphan_hash, metadata)
```

---

### 4.5 Resume Detection & Re-injection

**Problem:** Resumed sessions don't get updated memories.

**Solution:** Detect resume, force re-injection.

```python
class ResumeHandler:
    """Handle session resume (kimi --continue)."""
    
    def handle_resume(self, session_id: str, wire_path: Path):
        """
        Detect if this is a resumed session and ensure fresh injection.
        """
        # Check if session already exists
        state = self.state.load_session_state(session_id)
        
        if state and state.get("last_activity"):
            # This is a resume
            time_since_last = time.time() - state["last_activity"]
            
            if time_since_last > 60:  # More than 1 minute = resume
                # Force fresh subconscious generation
                self.generator.generate(force=True)
                
                # Re-inject into Kimi's context
                self.injector.inject(session_id, self.project_root)
                
                # Log resume
                self.logger.info("Session resumed, re-injected subconscious")
```

---

## 5. Event Flow

### 5.1 New Session Flow

```
Terminal$ kimi
    │
    ▼
┌───────────────┐
│ SessionStart  │
│ Event Fired   │
└───────┬───────┘
        │
        ▼
┌───────────────────────────┐
│ 1. Resolve Project        │
│    - Walk up tree         │
│    - Find root markers    │
│    - Hash project path    │
└───────┬───────────────────┘
        │
        ▼
┌───────────────────────────┐
│ 2. Ensure SUBCONSCIOUS.md │
│    - Fetch memory blocks  │
│    - Fetch guidance       │
│    - ALWAYS write file    │
└───────┬───────────────────┘
        │
        ▼
┌───────────────────────────┐
│ 3. Inject into Kimi       │
│    - Write AGENTS.md      │
│    - Update system prompt │
└───────┬───────────────────┘
        │
        ▼
┌───────────────────────────┐
│ Session Active            │
│ (subconscious in context) │
└───────────────────────────┘
```

### 5.2 Turn End Flow (Incremental)

```
User Input → Kimi Processing → Tool Calls
                                     │
                                     ▼
                              ┌─────────────┐
                              │  TurnEnd    │
                              │  (wire.jsonl│
                              │   updated)  │
                              └──────┬──────┘
                                     │
    ┌────────────────────────────────┼────────────────────────────────┐
    │                                ▼                                │
    │                    ┌─────────────────────┐                      │
    │                    │   Daemon Watcher    │                      │
    │                    │   (file change)     │                      │
    │                    └──────────┬──────────┘                      │
    │                               │                                 │
    │         ┌─────────────────────┼─────────────────────┐           │
    │         ▼                     ▼                     ▼           │
    │  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐      │
    │  │ Sync to Letta│    │ Detect       │    │ Update       │      │
    │  │ (insights)   │    │ Insights     │    │ SUBCONSCIOUS │      │
    │  └──────────────┘    └──────────────┘    └──────────────┘      │
    │         │                     │                     │          │
    └─────────┴─────────────────────┴─────────────────────┘          │
                                     │                               │
                                     ▼                               │
                              ┌─────────────┐                        │
                              │ Check for   │                        │
                              │ Guidance    │                        │
                              └──────┬──────┘                        │
                                     │                               │
                    ┌────────────────┼────────────────┐              │
                    ▼                ▼                ▼              │
             ┌──────────┐    ┌──────────┐    ┌──────────┐          │
             │ Guidance │    │ No       │    │ Timeout  │          │
             │ Received │    │ Guidance │    │ / Error  │          │
             └────┬─────┘    └────┬─────┘    └────┬─────┘          │
                  │               │               │                │
                  ▼               ▼               ▼                │
             ┌──────────┐    ┌──────────┐    ┌──────────┐          │
             │ Append   │    │ Memory   │    │ Degraded │          │
             │ to file  │    │ blocks   │    │ mode     │          │
             │ + notify │    │ only     │    │ (local)  │          │
             └──────────┘    └──────────┘    └──────────┘          │
                                                                     │
    ┌────────────────────────────────────────────────────────────────┘
    │
    ▼
┌───────────────────────────┐
│ Next Turn Starts          │
│ (fresh subconscious in    │
│  context)                 │
└───────────────────────────┘
```

### 5.3 Session End Flow

```
User exits kimi (Ctrl+D, "exit", etc.)
    │
    ▼
┌───────────────────────────┐
│ SessionEnd Event          │
└───────┬───────────────────┘
        │
        ▼
┌───────────────────────────┐
│ 1. Final Sync             │
│    - Send pending insights│
│    - Get final guidance   │
└───────┬───────────────────┘
        │
        ▼
┌───────────────────────────┐
│ 2. Consolidation Check    │
│    - If significant,      │
│      trigger memory merge │
└───────┬───────────────────┘
        │
        ▼
┌───────────────────────────┐
│ 3. Checkpoint             │
│    - Save session state   │
│    - Mark session closed  │
└───────────────────────────┘
```

---

## 6. Edge Cases & Handling

### 6.1 Nested Projects

**Scenario:** `~/Projects/monorepo/frontend/` where both have `.git`

**Resolution:** Use nearest marker (most specific wins).

```python
def resolve_nested(current: Path) -> Path:
    """
    For: ~/Projects/monorepo/frontend/
    
    Check in order:
    1. ~/Projects/monorepo/frontend/.git  ← Use this (nearest)
    2. ~/Projects/monorepo/.git
    
    Result: frontend/ is its own project
    """
    for path in [current] + list(current.parents):
        if any((path / m).exists() for m in self.ROOT_MARKERS):
            return path
```

### 6.2 Mid-Session Directory Change

**Scenario:** User `cd`s to different project mid-session.

**Resolution:** Treat as project boundary crossing.

```python
def detect_project_switch(self, new_cwd: Path) -> bool:
    """Detect if user changed projects mid-session."""
    new_hash = self.resolver.resolve(new_cwd)
    
    if new_hash != self.current_project_hash:
        # Project switch detected
        self.logger.info(f"Project switch: {self.current_project_hash[:8]}... -> {new_hash[:8]}...")
        
        # Save current context
        self._checkpoint_current_project()
        
        # Load/inject new project context
        self._activate_project(new_hash)
        
        return True
    
    return False
```

### 6.3 Offline Mode

**Scenario:** No network, Letta unreachable.

**Resolution:** Degrade to local-only mode.

```python
class OfflineHandler:
    """Handle offline scenarios gracefully."""
    
    def sync(self, insights: list):
        if not self.letta.is_reachable():
            # Queue insights for later
            self.state.queue_insights(insights)
            
            # Generate SUBCONSCIOUS.md from local cache only
            content = self.generator.generate_local_only()
            self.state.write_subconscious(content)
            
            # Notify user (once per session)
            if not self._offline_notified:
                print("[Subconscious] Offline mode - using cached memories")
                self._offline_notified = True
            
            return
        
        # Online - normal flow
        self._sync_online(insights)
```

### 6.4 Concurrent Sessions

**Scenario:** Multiple kimi sessions active simultaneously.

**Resolution:** Per-session context with shared memory base.

```python
class ConcurrentSessionManager:
    """Manage multiple active sessions."""
    
    def get_session_context(self, session_id: str) -> SessionContext:
        """
        Each session gets:
        - Shared: Memory blocks (read-only sync)
        - Private: Session-specific guidance
        """
        return SessionContext(
            shared_memory=self.letta.get_memory_blocks(),
            private_guidance=self.state.get_session_guidance(session_id),
            session_id=session_id,
        )
```

---

## 7. File Locations

```
~/.kimi/sessions/
├── <project_hash_1>/
│   ├── <session_id_1>/
│   │   ├── wire.jsonl           # Kimi writes
│   │   ├── state.json           # Kimi writes
│   │   └── subconscious_context.md  # Daemon writes (injection)
│   └── <session_id_2>/
│       └── ...
└── <project_hash_2>/
    └── ...

~/.kimi/subconscious/           # Daemon data
├── config.json
├── daemon.pid
├── projects/
│   ├── <project_hash_1>/
│   │   ├── SUBCONSCIOUS.md      # Canonical subconscious file
│   │   ├── conversations.json   # Session -> Letta mapping
│   │   ├── insights.db          # SQLite: detected insights
│   │   └── last_read_<session>.json
│   └── <project_hash_2>/
│       └── ...
└── orphans/
    └── <orphan_hash>/
        ├── SUBCONSCIOUS.md
        └── metadata.json

<project_root>/
├── .git/
├── AGENTS.md                    # Daemon writes (Kimi injection)
├── SUBCONSCIOUS.md -> ~/.kimi/subconscious/projects/<hash>/SUBCONSCIOUS.md  # Symlink
└── ...
```

---

## 8. Implementation Phases

### Phase 1: Foundation (Week 1)
- [ ] Refactor `ProjectResolver` with tree-walking
- [ ] Implement `EagerGenerator` (always write file)
- [ ] Add `AGENTS.md` injection mechanism
- [ ] Fix: Write SUBCONSCIOUS.md on first sync, not just guidance

### Phase 2: Universal Coverage (Week 2)
- [ ] Implement orphan project handling
- [ ] Add resume detection & re-injection
- [ ] Handle nested projects correctly
- [ ] Add offline mode fallback

### Phase 3: Polish (Week 3)
- [ ] Mid-session project switch detection
- [ ] Concurrent session handling
- [ ] Performance optimization (batch sync)
- [ ] Observability (metrics, logs)

### Phase 4: Advanced (Week 4)
- [ ] Memory consolidation (daily/weekly)
- [ ] Cross-project memory linking
- [ ] Explicit memory API (`/remember`, `/recall`)

---

## 9. Success Metrics

| Metric | Current | Target |
|--------|---------|--------|
| Sessions with subconscious.md | ~60% | 100% |
| Resume injection success | ~30% | 100% |
| Orphan session coverage | 0% | 100% |
| Offline degradation | Crash | Graceful |
| Avg. injection latency | N/A | <500ms |

---

## 10. Risks & Mitigations

| Risk | Mitigation |
|------|------------|
| AGENTS.md conflicts with user file | Section-based merging, preserve user content |
| Too many orphan projects | Auto-cleanup after N days of inactivity |
| Letta API latency | Async sync, local caching, background processing |
| Disk bloat | Auto-compact old sessions, compress wire.jsonl |
| Privacy leaks | Respect .gitignore, exclude secrets patterns |

---

*Architecture version: 1.0*
*Last updated: 2026-03-09*
