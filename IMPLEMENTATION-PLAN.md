# Universal Subconscious — Implementation Plan

> "If you have to ask 'should I use a library?' the answer is yes." — Stroustrup (probably)

## Philosophy

1. **Reuse ruthlessly** — If it exists and works, use it
2. **Local-first** — Network is a luxury, not a requirement
3. **Files are the API** — Unix philosophy
4. **User in the loop** — "Curious" mode asks, learns, improves
5. **Boring technology** — SQLite, files, TOML. Nothing fancy.

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────────────┐
│  KIMI SESSION (Anywhere in ~/...)                                           │
│  ─────────────────────────────                                              │
│  User Input ──▶ Subconscious Query ──▶ Context Injection ──▶ Response       │
│       │                                                                        │
│       ▼                                                                        │
│  ┌─────────────────────────────────────────────────────────────────────────┐│
│  │  SUBCONSCIOUS DAEMON (File Watcher)                                    ││
│  │  ─────────────────────────────────                                     ││
│  │  wire.jsonl ──▶ Parse ──▶ Extract ──▶ Ask User? ──▶ Store              ││
│  │                              │                                           ││
│  │                              ▼ (if Curious tier)                        ││
│  │                        [y/n/always/never]                              ││
│  │                              │                                           ││
│  │                              ▼                                           ││
│  │  ┌─────────────────────────────────────────────────────────────────┐    ││
│  │  │  STORAGE LAYERS                                                │    ││
│  │  │  ──────────────                                                │    ││
│  │  │  • hnswlib (vectors for similarity)                           │    ││
│  │  │  • SQLite FTS5 (text search)                                  │    ││
│  │  │  • SQLite tables (metadata, feedback, config)                 │    ││
│  │  │  • Files (export, debug)                                      │    ││
│  │  └─────────────────────────────────────────────────────────────────┘    ││
│  └─────────────────────────────────────────────────────────────────────────┘│
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Component Breakdown

### 1. Storage Layer (Reuse Everything)

| Component | Library | Rationale |
|-----------|---------|-----------|
| **Vector similarity** | `hnswlib` | Spotify-proven, fast, supports updates, C++ core, minimal deps |
| **Text search** | SQLite FTS5 | Built-in since SQLite 3.9.0, zero deps, BM25 ranking |
| **Metadata/feedback** | SQLite tables | One DB to rule them all, ACID, portable |
| **Config** | `pydantic-settings` | Type-safe, TOML/YAML/ENV, validation |
| **Embeddings** | `sentence-transformers` (local) or API | All-MiniLM-L6-v2 for local, OpenAI for quality |

**Why not Chroma/Milvus/etc?** They bundle too much. We want composable parts.

**Database Schema (SQLite):**

```sql
-- memories: Core fact storage
CREATE TABLE memories (
    id TEXT PRIMARY KEY,
    content TEXT NOT NULL,
    embedding BLOB,  -- Serialized vector, hnswlib has separate index
    category TEXT,   -- 'preference', 'bug', 'pattern', 'correction'
    lifetime TEXT,   -- 'permanent', 'archivable', 'ephemeral'
    importance REAL, -- 0.0-1.0
    project_path TEXT, -- Where it was learned
    created_at TIMESTAMP,
    last_accessed TIMESTAMP,
    access_count INTEGER DEFAULT 0
);

-- memory_access_log: For usage analytics, auto-archive decisions
CREATE TABLE memory_access_log (
    memory_id TEXT,
    query TEXT,
    retrieved_at TIMESTAMP,
    was_useful BOOLEAN  -- User feedback
);

-- feedback: Active learning feedback
CREATE TABLE feedback (
    id INTEGER PRIMARY KEY,
    query TEXT,
    memory_id TEXT,
    user_marked_relevant BOOLEAN,
    timestamp TIMESTAMP,
    tier_at_time TEXT  -- 'curious', 'conservative', etc.
);

-- extraction_log: What we considered extracting
CREATE TABLE extraction_log (
    id INTEGER PRIMARY KEY,
    turn_summary TEXT,
    suggested_facts TEXT,  -- JSON array
    user_response TEXT,    -- 'y', 'n', 'always', 'never'
    timestamp TIMESTAMP
);

-- FTS5 virtual table for text search
CREATE VIRTUAL TABLE memories_fts USING FTS5(content, tokenize='porter ascii');
```

**hnswlib Integration:**

```python
# vector_store.py - Thin wrapper around hnswlib
import hnswlib
import numpy as np
import pickle
from pathlib import Path

class VectorStore:
    """Lightning-fast local vector search."""
    
    def __init__(self, dim: int = 384, path: Path = None):
        self.dim = dim
        self.path = path or Path.home() / ".kimi/subconscious/vectors.idx"
        self.index = None
        self.id_map = {}  # int -> memory_id
        
    def init(self, max_elements: int = 100000):
        """Create new index."""
        self.index = hnswlib.Index(space='cosine', dim=self.dim)
        self.index.init_index(
            max_elements=max_elements,
            ef_construction=200,
            M=16
        )
        self.index.set_ef(50)
        
    def add(self, memory_id: str, vector: np.ndarray):
        """Add vector with string ID."""
        idx = len(self.id_map)
        self.id_map[idx] = memory_id
        self.index.add_items(vector.reshape(1, -1), np.array([idx]))
        
    def search(self, query: np.ndarray, k: int = 10) -> list[tuple[str, float]]:
        """Returns [(memory_id, distance), ...]"""
        labels, distances = self.index.knn_query(query.reshape(1, -1), k=k)
        return [
            (self.id_map[int(idx)], float(dist))
            for idx, dist in zip(labels[0], distances[0])
        ]
        
    def save(self):
        """Persist to disk."""
        self.index.save_index(str(self.path))
        with open(self.path.with_suffix('.map'), 'wb') as f:
            pickle.dump(self.id_map, f)
            
    def load(self):
        """Load from disk."""
        self.index = hnswlib.Index(space='cosine', dim=self.dim)
        self.index.load_index(str(self.path))
        with open(self.path.with_suffix('.map'), 'rb') as f:
            self.id_map = pickle.load(f)
```

---

### 2. Extraction Engine ("Curious" Tier)

**The "Curious" Philosophy:**
- Not too quiet (miss important things)
- Not too noisy (spam user)
- Ask when uncertain, learn from answers

**Tier Configuration:**

```toml
# ~/.config/subconscious/extraction.toml
[tier]
name = "curious"  # conservative, curious, aggressive

[curious.triggers]
explicit_memory = true      # "remember", "note that"
corrections = true          # "wrong", "actually"
breakthroughs = true        # "finally", "works!"
errors = true               # Tool failures
file_creations = "ask"      # "ask", "always", "never"
file_modifications = "ask"  # Same
thoughts = "ask"            # Kimi's internal monologue

[curious.thresholds]
confidence = 0.6            # Ask if 0.4-0.7 confidence
max_suggestions_per_turn = 3
min_content_length = 20     # Ignore "ok", "yes", etc.

[curious.learning]
auto_promote_after = 3      # "y" 3 times → auto-extract this pattern
auto_suppress_after = 3     # "n" 3 times → never ask for this pattern
```

**Extraction Logic:**

```python
# extraction.py
from dataclasses import dataclass
from typing import List, Optional
import re

@dataclass
class ExtractionCandidate:
    content: str
    category: str
    confidence: float
    source: str  # 'user', 'assistant_thought', 'tool_result'
    why: str     # Explanation for user

class CuriousExtractor:
    """Ask user about potentially memory-worthy content."""
    
    def __init__(self, config: ExtractionConfig, feedback_store: FeedbackStore):
        self.config = config
        self.feedback = feedback_store
        self.learned_patterns = self._load_learned_patterns()
        
    def extract(self, turn: Turn) -> List[ExtractionCandidate]:
        """Find candidates from a turn."""
        candidates = []
        
        # Pattern 1: Explicit memory requests
        if self.config.triggers.explicit_memory:
            for match in self._find_explicit_requests(turn.user_input):
                candidates.append(ExtractionCandidate(
                    content=match.content,
                    category="preference",
                    confidence=0.95,
                    source="user",
                    why=f"You said '{match.keyword}'"
                ))
        
        # Pattern 2: Corrections
        if self.config.triggers.corrections:
            if self._is_correction(turn):
                candidates.append(ExtractionCandidate(
                    content=f"Correction: {turn.user_input}",
                    category="correction",
                    confidence=0.85,
                    source="user",
                    why="You corrected the assistant"
                ))
        
        # Pattern 3: File operations
        if self.config.triggers.file_creations != "never":
            for file_op in turn.file_operations:
                if file_op.type == "create":
                    candidates.append(ExtractionCandidate(
                        content=f"Created {file_op.path}",
                        category="file_creation",
                        confidence=0.7,
                        source="tool",
                        why=f"New file: {file_op.path.name}"
                    ))
        
        # Pattern 4: Thoughts (if enabled)
        if self.config.triggers.thoughts != "never":
            for thought in turn.assistant_thinking:
                if self._is_insightful_thought(thought):
                    candidates.append(ExtractionCandidate(
                        content=thought[:500],  # Truncate
                        category="insight",
                        confidence=0.6,
                        source="assistant_thought",
                        why="Key insight from reasoning"
                    ))
        
        # Sort by confidence, filter
        candidates.sort(key=lambda x: x.confidence, reverse=True)
        return candidates[:self.config.thresholds.max_suggestions_per_turn]
    
    def should_ask_user(self, candidate: ExtractionCandidate) -> bool:
        """Determine if we should prompt user for this candidate."""
        # Check learned patterns
        if self._is_auto_promoted(candidate):
            return False  # Auto-extract
        if self._is_auto_suppressed(candidate):
            return False  # Skip silently
            
        # Check confidence
        conf = candidate.confidence
        if conf >= 0.85:
            return False  # Auto-extract high confidence
        if conf < 0.4:
            return False  # Skip low confidence
            
        return True  # Ask user
    
    def ask_user(self, candidate: ExtractionCandidate) -> str:
        """Prompt user, return 'y', 'n', 'always', 'never'."""
        # Format compact prompt
        print(f"\n[🧠 Subconscious] Remember this?")
        print(f"  {candidate.why}")
        print(f"  \"{candidate.content[:100]}{'...' if len(candidate.content) > 100 else ''}\"")
        print(f"  [y/n/always/never] ", end="", flush=True)
        
        response = input().strip().lower()
        
        # Learn from response
        if response == "always":
            self._promote_pattern(candidate)
        elif response == "never":
            self._suppress_pattern(candidate)
            
        return response[0] if response else "n"  # 'y', 'n', or ''
```

**Learning from Feedback:**

```python
def _promote_pattern(self, candidate: ExtractionCandidate):
    """Mark this pattern as auto-extract in future."""
    pattern = self._extract_pattern_signature(candidate)
    self.learned_patterns[pattern] = {"action": "auto_extract", "count": 0}
    
def _suppress_pattern(self, candidate: ExtractionCandidate):
    """Mark this pattern as auto-skip in future."""
    pattern = self._extract_pattern_signature(candidate)
    self.learned_patterns[pattern] = {"action": "auto_skip", "count": 0}
```

---

### 3. Retrieval Engine (Human-Like Recall)

**The Query Flow:**

```python
# retrieval.py
class MemoryRetriever:
    """Retrieve relevant memories like a human would."""
    
    def __init__(self, vector_store: VectorStore, db: sqlite3.Connection):
        self.vector_store = vector_store
        self.db = db
        
    def recall(self, query: str, current_path: Path, 
               verbosity: int = 1) -> RetrievedContext:
        """
        Main entry point. Returns context for injection.
        """
        # 1. Get query embedding
        query_vec = self._embed(query)
        
        # 2. Vector similarity search (what's similar)
        vector_results = self.vector_store.search(query_vec, k=20)
        
        # 3. FTS5 text search (keyword matches)
        fts_results = self._fts_search(query, k=10)
        
        # 4. Recent context (what's fresh)
        recent_results = self._get_recent(k=5, hours=24)
        
        # 5. Hierarchical context (where we are)
        hierarchy_results = self._get_hierarchical(current_path, k=10)
        
        # 6. Merge and rank
        merged = self._merge_results(
            vector=vector_results,
            fts=fts_results,
            recent=recent_results,
            hierarchy=hierarchy_results
        )
        
        # 7. Format for LLM
        context = self._format_for_llm(merged[:10])  # Top 10
        
        # 8. Build status info
        status = RetrievalStatus(
            memories_consulted=len(merged),
            memories_included=len(context.memories),
            categories=self._count_categories(merged),
            projects=self._count_projects(merged)
        )
        
        return RetrievedContext(
            formatted=context,
            status=status,
            raw_memories=merged
        )
    
    def _merge_results(self, **result_sets) -> List[ScoredMemory]:
        """
        Merge different result types with weighted scoring.
        
        Weight philosophy:
        - Vector: 0.40 (semantic similarity)
        - FTS: 0.25 (keyword match)
        - Recent: 0.20 (recency bias)
        - Hierarchy: 0.15 (location context)
        """
        scores = defaultdict(float)
        memories = {}
        
        for name, results in result_sets.items():
            weight = {"vector": 0.4, "fts": 0.25, "recent": 0.2, "hierarchy": 0.15}[name]
            for mem_id, score in results:
                scores[mem_id] += score * weight
                if mem_id not in memories:
                    memories[mem_id] = self._load_memory(mem_id)
        
        # Sort by combined score
        ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        return [
            ScoredMemory(memory=memories[mid], score=score)
            for mid, score in ranked if mid in memories
        ]
```

**Hierarchical Context:**

```python
def _get_hierarchical(self, current_path: Path, k: int) -> List[tuple]:
    """
    Get memories from parent directories.
    
    ~/Projects/the-job/k-search/ should see:
    1. the-job/k-search/ memories (specific)
    2. the-job/ memories (project context)
    3. Projects/ memories (domain context)
    4. ~/ memories (global preferences)
    """
    results = []
    
    # Walk up the tree
    path = current_path
    while path != path.parent:  # Stop at root
        # Get memories tagged with this exact path
        cursor = self.db.execute("""
            SELECT id, importance FROM memories
            WHERE project_path = ?
            ORDER BY importance DESC, last_accessed DESC
            LIMIT ?
        """, (str(path), k // 4))
        
        for row in cursor:
            # Weight by depth (closer = higher weight)
            depth_weight = 1.0 if path == current_path else 0.7
            results.append((row[0], row[1] * depth_weight))
        
        path = path.parent
    
    return results
```

---

### 4. UI/UX Design

**Verbosity Levels:**

```toml
[ui]
verbosity = 2  # 0=silent, 1=compact, 2=normal, 3=verbose
position = "header"  # header, footer, right-prompt, none
```

**Level 0: Silent (Magic Mode)**
```
# Nothing shown. Memories injected silently.
```

**Level 1: Compact (Icon + Count)**
```
$ kimi
🧠 42 | ~/Projects/the-job/k-search

# Or in right prompt (zsh):
user@host ~/Projects/the-job/k-search 🧠42 $ 
```

**Level 2: Normal (Status Header)**
```
$ kimi
┌─────────────────────────────────────────────────────────────┐
│ 🧠 Subconscious  42 memories  3 from ~/the-job  1 similar   │
└─────────────────────────────────────────────────────────────┘

> 
```

**Level 3: Verbose (Full Context)**
```
$ kimi
🧠 Subconscious Context
────────────────────────
Loaded: 42 total memories
  • 5 from ~/Projects/the-job (current project)
  • 3 from ~/Projects (parent context)
  • 34 global patterns/preferences

Similar to "dashboard":
  → "Created analytics dashboard for client-a" (~/Projects/client-a)
  → "Use recharts for charts, not D3" (preference)

> 
```

**Commands:**

```bash
# View status
$ kimisub status
🧠 Subconscious Daemon
──────────────────────
Status:     active (PID 12345)
Uptime:     3 days, 2 hours
Memories:   42 total
  Permanent:    12
  Long-term:    25
  Ephemeral:    5
Last sync:  2 minutes ago

# View memories (with search)
$ kimisub memories --search "dashboard"
ID       Content                                      Project
────────────────────────────────────────────────────────────
mem_12   Created analytics dashboard for client-a    ~/Projects/client-a
mem_23   Use recharts for charts, not D3             global
mem_34   Dashboard should have dark mode toggle      ~/Projects/the-job

# Interactive inspection
$ kimisub inspect mem_12
ID:          mem_12
Content:     Created analytics dashboard for client-a
Category:    file_creation
Lifetime:    archivable
Importance:  0.7
Project:     ~/Projects/client-a
Created:     2024-03-01
Accessed:    3 times (last: 2 days ago)

[Actions: (p)in (a)rchive (d)elete (q)uit]

# Pin to permanent
$ kimisub pin "always use aerospace-ui"
✓ Created permanent memory: mem_45

# Forget
$ kimisub forget mem_12
✓ Archived memory mem_12 (can be restored)

# Feedback on retrieval
$ kimisub feedback --query "dashboard" --result mem_12 --relevant
✓ Recorded: mem_12 is relevant for "dashboard"

# Show what's being considered for extraction (Curious tier)
$ kimisub curious --preview
Next turn will suggest:
  • "Created file dashboard.tsx" (file creation)
  • "Use TypeScript interfaces, not types" (preference signal)
  
[y/Enter to accept, n to skip, v for verbose]
```

**Shell Integration (Optional but Nice):**

```bash
# Add to .bashrc/.zshrc
source <(kimisub shell-integration --format=compact)

# Result: Shows 🧠42 in RPROMPT (zsh) or PS1 suffix (bash)
```

---

### 5. Configuration (pydantic-settings)

```python
# config.py
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field
from typing import Literal

class ExtractionConfig(BaseModel):
    tier: Literal["conservative", "curious", "aggressive"] = "curious"
    
    # Curious tier settings
    ask_on_file_creation: bool = True
    ask_on_file_modification: bool = False
    ask_on_thoughts: bool = True
    max_suggestions_per_turn: int = 3
    
    # Learning
    auto_promote_threshold: int = 3  # "y" 3 times
    auto_suppress_threshold: int = 3  # "n" 3 times

class UIConfig(BaseModel):
    verbosity: Literal[0, 1, 2, 3] = 2
    position: Literal["header", "footer", "right-prompt", "none"] = "header"
    colors: bool = True
    icons: bool = True

class StorageConfig(BaseModel):
    db_path: str = "~/.kimi/subconscious/memory.db"
    vector_path: str = "~/.kimi/subconscious/vectors.idx"
    max_memories: int = 100000
    archive_after_days: int = 90

class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        toml_file="~/.config/subconscious/config.toml",
        env_prefix="SUBCONSCIOUS_",
    )
    
    extraction: ExtractionConfig = ExtractionConfig()
    ui: UIConfig = UIConfig()
    storage: StorageConfig = StorageConfig()
    
    # Letta (optional cloud sync)
    letta_api_key: str | None = None
    letta_agent_id: str | None = None
    sync_to_letta: bool = False

# TOML file example:
"""
[extraction]
tier = "curious"
ask_on_file_creation = true
max_suggestions_per_turn = 3

[ui]
verbosity = 2
position = "header"

[storage]
db_path = "~/.kimi/subconscious/memory.db"
archive_after_days = 90

# Uncomment to enable cloud sync:
# [letta]
# api_key = "..."
# agent_id = "..."
# sync_to_letta = true
"""
```

---

## Implementation Phases

### Phase 1: Core Infrastructure (Week 1)

**Goal:** Basic extraction, storage, retrieval working

```
Day 1-2: Storage Layer
├── SQLite schema
├── hnswlib integration
└── FTS5 setup

Day 3-4: Extraction (Curious tier)
├── Parse wire.jsonl
├── Pattern detection
└── User prompt logic

Day 5: Retrieval
├── Vector similarity
├── Hierarchical context
└── Result merging

Day 6-7: CLI & Integration
├── kimisub CLI commands
├── Shell status display
└── Config management
```

**Acceptance Criteria:**
- [ ] `kimisub daemon start` watches wire.jsonl
- [ ] Curious tier asks user about file creations
- [ ] Memories stored in SQLite + hnswlib
- [ ] `kimisub status` shows daemon status
- [ ] Compact status shown on kimi start

### Phase 2: Polish (Week 2)

**Goal:** Learning, feedback, archive

```
Day 1-2: Learning System
├── Auto-promote patterns
├── Auto-suppress patterns
└── Feedback storage

Day 3-4: Archive & Lifecycle
├── Auto-archive old memories
├── Manual pin/archive/delete
└── Restore from archive

Day 5-6: Search & Discovery
├── FTS5 text search
├── kimisub memories --search
└── Similarity browsing

Day 7: Testing & Hardening
```

**Acceptance Criteria:**
- [ ] "y" 3 times on same pattern → auto-extract
- [ ] Old memories auto-archive
- [ ] Search across all memories
- [ ] Manual memory management

### Phase 3: Optional Cloud Sync (Week 3)

**Goal:** Letta integration for cross-device

```
Day 1-2: Letta Sync
├── Async sync to Letta
├── Conflict resolution
└── Offline queue

Day 3-4: Cross-Device
├── Session transfer
├── Memory consolidation
└── Import/export

Day 5: Performance
├── Benchmarks
├── Optimization
└── Caching
```

**Acceptance Criteria:**
- [ ] Works offline
- [ ] Syncs when online
- [ ] Cross-device memory access

---

## Reused Components Summary

| Component | Library | Lines We Write |
|-----------|---------|----------------|
| Vector search | hnswlib | ~100 (thin wrapper) |
| Text search | SQLite FTS5 | ~50 (SQL only) |
| Config | pydantic-settings | ~30 (schema only) |
| CLI | click | ~200 (commands) |
| File watching | watchdog | ~50 (handler) |
| Embeddings | sentence-transformers | ~20 (call only) |
| Database | sqlite3 (stdlib) | ~100 (queries) |
| **Total** | | **~550 lines** |

**What we DON'T write:**
- ❌ Vector index implementation (hnswlib)
- ❌ Text search engine (FTS5)
- ❌ Config parser (pydantic)
- ❌ CLI framework (click)
- ❌ File watch kernel code (watchdog)

**This is how you stand on the shoulders of giants.**

---

## File Structure

```
kimi_subconscious/
├── __init__.py
├── __main__.py              # Entry point
├── cli.py                   # Click commands
├── config.py                # pydantic-settings
├── daemon.py                # File watcher daemon
├── extraction/
│   ├── __init__.py
│   ├── curious.py           # Curious tier logic
│   ├── patterns.py          # Pattern detection
│   └── learning.py          # Feedback learning
├── storage/
│   ├── __init__.py
│   ├── db.py                # SQLite schema/queries
│   ├── vectors.py           # hnswlib wrapper
│   └── fts.py               # FTS5 wrapper
├── retrieval/
│   ├── __init__.py
│   ├── engine.py            # Main retrieval
│   ├── hierarchy.py         # Path-based context
│   └── merge.py             # Result merging
├── models.py                # Pydantic models
├── watcher.py               # wire.jsonl watcher
└── ui/
    ├── __init__.py
    ├── status.py            # Status display
    └── format.py            # Output formatting
```

---

## The Stroustrup-Linus-Ritchie Test

| Principle | Our Approach | Pass? |
|-----------|--------------|-------|
| **Reuse** | 7 major libraries, ~550 lines | ✅ |
| **Files are API** | wire.jsonl + SQLite | ✅ |
| **Local-first** | Works offline, optional cloud | ✅ |
| **User in loop** | Curious tier asks, learns | ✅ |
| **Boring tech** | SQLite, files, TOML | ✅ |
| **Simple parts** | Each module <200 lines | ✅ |
| **Composable** | Can swap hnswlib, SQLite, etc. | ✅ |

**They nod in approval.** 🎯

---

## Remaining Questions

1. **Embedding model:** Local (All-MiniLM, 80MB) or API (OpenAI, requires key)?
2. **Default verbosity:** 1 (compact) or 2 (normal header)?
3. **Shell integration:** Include in package or separate install?
4. **Letta sync priority:** Phase 3 or defer until needed?

**Ready to build?**
