# Universal Subconscious — Refined Vision

## The Core Insight

You want **human-like subconscious memory** for kimi:
- Walks into any room (directory) and knows the context
- Remembers what happened in similar situations
- Extrapolates from past to present
- No friction — just works

This is fundamentally different from the current project-based, sync-at-boundaries architecture.

---

## What Exists (Open Source)

| System | Key Pattern | We Can Use |
|--------|-------------|------------|
| **Mem0** | Layered memory (conversation → session → user) | ✅ User-level memory layer |
| **Zep/Graphiti** | Temporal knowledge graph + hybrid retrieval | ✅ Hierarchical project inheritance |
| **LangChain** | Pluggable memory types | ✅ Vector + buffer + summary combo |
| **AutoGen** | Multi-agent memory sharing | ✅ Session-to-session memory transfer |

**Key insight:** These systems do **continuous extraction**, not just boundary sync.

---

## The Architecture Shift

### Current (Project-Based, Sync-at-Boundaries)
```
Session Start ──▶ Sync ──▶ [Session Active] ──▶ Session End ──▶ Sync
```

### Target (Universal, Continuous)
```
Session Start ──▶ Load User Memory + Relevant Context
       │
       ▼
User Input ──▶ Search Similar Past Inputs ──▶ Inject Context ──▶ Kimi Responds
       │                                                                         │
       ▼                                                                         ▼
Extract Facts ◀── Kimi Thoughts (internal monologue) ◀── Tool Results/Errors
       │
       ▼
Update Memory (immediate, not batched)
```

---

## Key Design Decisions

### 1. Memory Hierarchy (Like Human Memory)

```
┌─────────────────────────────────────────────────────────────┐
│  WORKING MEMORY (Session)                                   │
│  ────────────────────────                                   │
│  • Current conversation buffer (last N turns)               │
│  • Active files being edited                                │
│  • In-flight errors/context                                 │
│  Lifetime: Current session only                             │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│  SHORT-TERM MEMORY (Recent Sessions)                        │
│  ───────────────────────────────────                        │
│  • Last 7 days of sessions                                  │
│  • Recently learned patterns                                │
│  • Active project context                                   │
│  Lifetime: 7 days, then compressed or promoted              │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│  LONG-TERM MEMORY (Facts & Patterns)                        │
│  ───────────────────────────────────                        │
│  • User preferences (aerospace-ui, patterns)                │
│  • Domain knowledge (design principles, coding styles)      │
│  • Relationship facts (project structures, dependencies)    │
│  Lifetime: Permanent, updated/refined                       │
└─────────────────────────────────────────────────────────────┘
```

### 2. Continuous Extraction (Not Just Boundaries)

**Current:** Only extract insights at session end (batch)  
**Target:** Extract facts continuously (streaming)

```python
# After EVERY turn:
facts = extract_facts(
    user_input=turn.user_input,
    assistant_thinking=turn.thinking,
    tool_calls=turn.tool_calls,
    tool_results=turn.tool_results,
)

# Immediately store:
for fact in facts:
    memory.store(
        fact=fact,
        timestamp=now(),
        session_id=session_id,
        importance=score_importance(fact),
        category=classify(fact),
    )
```

### 3. Hierarchical Context (Parent/Child Projects)

**Problem:** `the-job/k-search/` should inherit `the-job/` context  
**Solution:** Path-based inheritance with shadowing

```
/Users/me/Projects/the-job/k-search/  ← Current directory
          │
          ├── inherits from: /Users/me/Projects/the-job/
          │           └── inherits from: /Users/me/Projects/
          │                       └── inherits from: /Users/me/
          │                                   └── inherits from: global
          │
          └── Memory merge (parent first, child overrides):
              • "Use aerospace-ui" (from the-job)
              • "This is a search component" (from k-search, overrides parent)
```

### 4. Similarity-Based Retrieval (Human-Like Recall)

**Current:** Retrieve by exact project hash  
**Target:** Retrieve by semantic similarity

```python
# User starts session in: ~/Projects/new-client/
# User asks: "Create a dashboard"

# Retrieve similar past work:
similar = memory.search(
    query="dashboard creation UI design",
    filter={"user_id": current_user},  # Not project-specific!
    limit=5,
    recency_weight=0.3,  # 30% recency, 70% relevance
)

# Results might include:
# • Dashboard from ~/Projects/old-client/ (different project!)
# • Dashboard from ~/Projects/internal-tools/ (different project!)
# • UI patterns from ~/Projects/the-job/ (different project!)
```

**This is the human-like extrapolation you want.**

---

## Implementation Approaches

### Approach A: Enhance Current (Letta + Local)

**Keep:** Letta as the memory backend  
**Change:** How we interact with it

```python
# Current: Send whole conversation to Letta
# Target: Extract facts locally, send structured updates

class ContinuousMemory:
    def __init__(self):
        self.letta = LettaClient()
        self.local_vector_db = FAISSIndex()  # For fast similarity
        
    def on_turn_end(self, turn: Turn):
        # 1. Extract facts locally (fast)
        facts = self.extract_facts(turn)
        
        # 2. Store in local vector DB (for immediate retrieval)
        self.local_vector_db.add(facts)
        
        # 3. Async send to Letta (for persistence/consolidation)
        asyncio.create_task(self.letta.add_facts(facts))
        
    def get_context(self, query: str) -> str:
        # Fast local similarity search
        return self.local_vector_db.search(query, k=5)
```

**Pros:**
- Leverages existing Letta investment
- Minimal architectural change
- Letta handles consolidation

**Cons:**
- Letta API latency
- Rate limits
- Less control over retrieval

### Approach B: Hybrid Local + Cloud (Recommended)

**Local:** Fast retrieval, immediate storage  
**Cloud (Letta):** Long-term consolidation, cross-device sync

```python
class HybridMemory:
    """Fast local + persistent cloud."""
    
    def __init__(self):
        # Local: SQLite + FAISS for speed
        self.local_db = SQLiteDB("~/.kimi/subconscious/memory.db")
        self.vector_index = FAISSIndex(dim=1536)
        
        # Cloud: Letta for long-term/consolidation
        self.letta = LettaClient()
        
    def add(self, fact: Fact):
        # Immediate local storage
        self.local_db.insert(fact)
        self.vector_index.add(fact.embedding)
        
        # Queue for cloud sync
        self.sync_queue.put(fact)
        
    def search(self, query: str, **filters) -> List[Fact]:
        # Fast local search
        local_results = self.vector_index.search(query, k=10)
        
        # If offline or recent, local only
        if not self.letta.is_available():
            return local_results
            
        # Otherwise, also query Letta for long-term memories
        cloud_results = self.letta.search(query, k=5)
        
        # Merge and deduplicate
        return self.merge_results(local_results, cloud_results)
        
    def sync(self):
        """Background sync to Letta."""
        batch = self.sync_queue.get_batch()
        self.letta.add_facts(batch)
```

**Pros:**
- Fast local retrieval (<100ms)
- Works offline
- Letta for cross-device/cross-session consolidation
- Full control over retrieval logic

**Cons:**
- More complex
- Dual storage

### Approach C: Replace Letta with Open Source

**Replace:** Letta with Mem0/Zep/Graphiti

```python
from mem0 import Memory  # or zep, or graphiti

class OSSMemory:
    def __init__(self):
        self.memory = Memory()  # Mem0 instance
        
    def add(self, messages, **metadata):
        self.memory.add(messages, **metadata)
        
    def search(self, query, **filters):
        return self.memory.search(query, **filters)
```

**Pros:**
- Purpose-built for this
- Better APIs
- Self-hostable

**Cons:**
- Migration from Letta
- Another dependency
- Less mature

---

## Continuous Monitoring Architecture

### How to Capture Kimi's Thoughts?

**Problem:** Current architecture watches `wire.jsonl` (file-based)  
**Issue:** Delayed, batch-oriented

**Solution:** Real-time streaming from kimi-cli

```python
# Option 1: Patch kimi-cli (like ai-config/kimi/patches/)
# Add hook in kimi_cli/soul/agent.py after each turn

async def on_turn_complete(turn: Turn):
    # Send to subconscious daemon via IPC
    subprocess.run([
        "kimisub", "ingest", 
        "--session", session_id,
        "--project", project_hash,
    ], input=turn.to_json())
```

```python
# Option 2: File watcher with zero delay
# Use inotify/fsevents for immediate notification

class RealtimeWatcher:
    def __init__(self):
        self.observer = Observer()  # watchdog
        
    def on_wire_change(self, event):
        # Read only NEW lines since last offset
        new_lines = self.read_new_lines(event.src_path)
        
        # Parse and extract immediately
        for line in new_lines:
            msg = parse(line)
            if msg.type == "TurnEnd":
                self.process_turn(msg)
                
    def process_turn(self, turn):
        facts = extract_facts(turn)
        for fact in facts:
            memory.add(fact)  # Immediate!
```

**Recommendation:** Option 2 (file watcher) — no kimi-cli modifications needed.

---

## Human-Like Recall Algorithm

```python
def retrieve_context(query: str, current_dir: Path) -> str:
    """
    Retrieve relevant context using human-like principles:
    1. Recency (what happened recently)
    2. Relevance (semantic similarity)
    3. Hierarchical (parent project context)
    4. Importance (flagged facts)
    """
    
    # 1. Semantic similarity (what's similar)
    similar = vector_search(query, k=10)
    
    # 2. Recent context (what's fresh)
    recent = time_range_search(hours=24, k=5)
    
    # 3. Hierarchical (parent projects)
    hierarchy = []
    for parent in walk_up(current_dir):
        hierarchy.extend(get_project_memory(parent))
    
    # 4. Important facts (flagged)
    important = search(importance="high", k=3)
    
    # Merge with weighted scoring
    results = merge(
        similar, weight=0.4,
        recent, weight=0.3,
        hierarchy, weight=0.2,
        important, weight=0.1,
    )
    
    return format_for_prompt(results)
```

---

## What I'm Confident About

| Aspect | Confidence | Reasoning |
|--------|------------|-----------|
| **Continuous extraction** | 90% | File watcher pattern works, proven |
| **Local vector DB** | 95% | FAISS/SQLite are mature |
| **Hierarchical context** | 85% | Path walking is simple |
| **Fact extraction LLM** | 80% | Prompt engineering challenge |
| **Hybrid local/cloud** | 85% | Common pattern, proven |
| **Cross-session recall** | 90% | Vector similarity works |

## What I'm NOT Confident About

| Aspect | Confidence | Risk |
|--------|------------|------|
| **Extraction quality** | 60% | Will extract noise/miss key facts |
| **Retrieval relevance** | 65% | May return irrelevant context |
| **Performance at scale** | 60% | 1000s of sessions = slow? |
| **Privacy boundaries** | 60% | Cross-project leak risk |
| **Kimi CLI integration** | 70% | May need patches |
| **Fact consolidation** | 60% | Duplication, conflicts |

---

## The "Linus Test"

Would Linus Torvalds approve?

| Principle | Our Approach | Linus Says |
|-----------|--------------|------------|
| **Do one thing well** | Memory layer only, not full AI | ✅ Good |
| **Text-based** | SQLite + markdown export | ✅ Good |
| **Composable** | API-based, can swap backends | ✅ Good |
| **No surprises** | Explicit memory vs magic | ⚠️ Need care |
| **Performance matters** | Local first, <100ms retrieval | ✅ Good |
| **Simple over complex** | Hybrid may be too complex | ❌ Risk |

**Risk:** Hybrid local/cloud adds complexity. Maybe start with local-only?

---

## Recommendation

**Phase 1 (MVP): Local-First with Simple Hierarchy**

```
SQLite + FAISS (local only)
├── Fast retrieval (<100ms)
├── Hierarchical project inheritance
├── Continuous extraction
└── Semantic search
```

**Phase 2 (Scale): Add Letta Sync**

```
Local (fast) + Letta (long-term)
├── Local for immediate retrieval
├── Letta for consolidation
└── Cross-device sync
```

**Skip for now:**
- Complex fact consolidation (hard)
- Real-time kimi thought extraction (needs patches)
- Full knowledge graphs (overkill)

---

## Discussion Points for You

Before finalizing implementation, I need your input on:

### 1. **Privacy Boundaries**
   - Should sessions in `~/Projects/client-a/` see memories from `~/Projects/client-b/`?
   - If similar query: "dashboard design" — cross-client ok?
   - Or strict project isolation with explicit cross-project tags?

### 2. **Extraction Granularity**
   - Extract every turn (high volume)?
   - Extract only "important" turns (miss things)?
   - Extract only on explicit keywords ("remember this")?

### 3. **Memory Lifetime**
   - Keep everything forever?
   - Auto-expire old sessions (90 days)?
   - Manual "archive" vs "delete"?

### 4. **Kimi Integration**
   - Patch kimi-cli for better hooks (risky)?
   - Stick with file watching (safer)?
   - Wait for kimi's native plugin system (patient)?

### 5. **Letta Future**
   - Keep Letta as primary backend?
   - Migrate to Mem0/Zep when stable?
   - Build local-only, Letta as optional sync?

### 6. **UI/Visibility**
   - Show "recalled memories" in session (verbose)?
   - Silent injection (magic)?
   - Command `/subconscious show` to inspect?

---

*Awaiting your guidance on these tradeoffs before proceeding.*
