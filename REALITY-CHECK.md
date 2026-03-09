# Reality Check — Universal Subconscious

## Machine Specs Analysis

**Hardware:**
- 2016 MacBook Pro 13,3
- Intel Core i7 (4 cores / 8 threads @ 2.7 GHz)
- 16 GB RAM
- AMD Radeon Pro 455 (2GB VRAM)
- No NVIDIA GPU
- Intel HD Graphics 530 (integrated)

**Verdict:** 
- ✅ Can run local embedding models (CPU)
- ❌ Cannot run LLMs locally (no CUDA, not enough VRAM)
- ✅ 16GB RAM is sufficient for our stack
- ✅ SSD is fast enough for SQLite + hnswlib

---

## Embedding Options (Deep Dive)

### Option 1: FastEmbed (⭐ RECOMMENDED)

```python
from fastembed import TextEmbedding
model = TextEmbedding()  # BAAI/bge-small-en-v1.5, 67MB
```

**Pros:**
- ✅ 67MB model (tiny)
- ✅ ~50-100ms per text on your CPU
- ✅ No PyTorch/TensorFlow (ONNX only)
- ✅ ~150MB RAM usage
- ✅ Optimized for CPU inference
- ✅ First load: ~1s

**Cons:**
- ⚠️ Less well-known than sentence-transformers
- ⚠️ Fewer model options (but covers our needs)

**Realistic Performance on Your Mac:**
- Embedding 1 short fact: ~50-100ms
- Embedding 5 facts: ~250-500ms total
- This is acceptable for "Curious" tier (not blocking user)

---

### Option 2: sentence-transformers (all-MiniLM-L6-v2)

```python
from sentence_transformers import SentenceTransformer
model = SentenceTransformer("all-MiniLM-L6-v2")
```

**Pros:**
- ✅ Industry standard
- ✅ 90MB model (still small)
- ✅ Battle-tested

**Cons:**
- ⚠️ Requires PyTorch (~400MB RAM)
- ⚠️ ~100-200ms per text (2x slower)
- ⚠️ First load: ~2-3s

**Verdict:** Heavier than needed. FastEmbed is better for our use case.

---

### Option 3: Ollama (all-minilm)

```bash
ollama pull all-minilm
ollama embed -m all-minilm "your text"
```

**Pros:**
- ✅ HTTP API (easy to integrate)
- ✅ Unified with LLM if you use Ollama

**Cons:**
- ❌ Server overhead (~500MB RAM)
- ❌ Adds latency (HTTP round-trip)
- ❌ Requires separate Ollama install

**Verdict:** Overkill for just embeddings. Use only if you already run Ollama.

---

### Option 4: Kimi CLI / Moonshot API

```python
from openai import OpenAI
client = OpenAI(api_key=..., base_url="https://api.moonshot.cn/v1")
client.embeddings.create(model="embedding-2", input="text")
```

**Pros:**
- ✅ Best quality embeddings
- ✅ No local compute

**Cons:**
- ❌ Requires internet
- ❌ API latency (~200-500ms)
- ❌ Costs money (though embeddings are cheap)
- ❌ Offline = broken

**Verdict:** Not suitable for our offline-first goal.

---

## Our Decision: FastEmbed

**Why:**
1. **Fast enough:** 50-100ms per fact is acceptable for background extraction
2. **Small enough:** 67MB model, 150MB RAM
3. **Simple enough:** `pip install fastembed`, no external services
4. **Good enough:** BAAI/bge-small-en-v1.5 is SOTA for small models

**Fallback:** If FastEmbed fails, we can add sentence-transformers as backup.

---

## Naming Clarification

**You asked:** "Are you using kimisub as a substitute for kemosabe?"

**Answer:** Yes, I defaulted to `kimisub` as the CLI command. But **kemosabe** is the much better name.

**Proposal:**
```
Command: kemosabe (or km for short)
Package: kimi_subconscious (Python module)
Daemon: kemosabe-daemon
Config: ~/.config/kemosabe/
Data: ~/.kimi/kemosabe/
```

**Why "kemosabe":**
- ✅ Kimi + Kemosabe (trusted friend/partner from Lone Ranger)
- ✅ Memorable
- ✅ Short command (`km`)
- ✅ Fun

**Updated CLI:**
```bash
$ km status              # Was: kimisub status
$ km memories --search   # Was: kimisub memories
$ km daemon start        # Was: kimisub daemon start
$ km curious             # Was: kimisub curious
```

---

## UI/UX Decisions

### Verbosity: Level 2 (Normal Header) by Default

```bash
$ kimi
┌─────────────────────────────────────────────────────────────┐
│ 🧠 kemosabe  42 memories  3 from ~/the-job  [press ? toggle] │
└─────────────────────────────────────────────────────────────┘
> 
```

**Hotkey to Toggle:** `?` or `Ctrl+S`

**Cycle:**
- Level 2 (normal) → Level 1 (compact) → Level 3 (verbose) → Level 0 (silent) → Level 2

**Implementation:**
```python
# In daemon, listen for keypress
# When '?' detected, cycle verbosity and redraw
```

### Shell Integration: Built-in

```bash
# Auto-install on first run
$ km shell-integration --install
✓ Added to ~/.zshrc
✓ Run `source ~/.zshrc` to activate

# Or manual
$ km shell-integration >> ~/.zshrc
```

**Right-prompt (zsh):**
```
user@host ~/Projects/the-job/k-search $          🧠42
```

**PS1 suffix (bash):**
```
user@host:~/Projects/the-job/k-search 🧠42$ 
```

---

## Letta Sync: Roadmap Only

**Decision:** Keep in roadmap, implement after core is stable.

**Why:**
1. Local-first is the priority
2. Letta adds complexity (async, conflicts, API)
3. Not needed for MVP value
4. Can add later without breaking changes

**When to add:**
- Core system stable for 2+ weeks
- User (you) explicitly asks for cross-device sync
- Or when you switch machines regularly

---

## Sanity Check: Goals vs Plan

### Original Goals

| Goal | Our Plan | Status |
|------|----------|--------|
| Universal (anywhere in ~/) | Hierarchical path-based memory | ✅ |
| Continuous learning | Curious tier with user feedback | ✅ |
| Extrapolate from past | Vector similarity across all sessions | ✅ |
| Low friction | FastEmbed (no API keys), sensible defaults | ✅ |
| Human-like recall | Merge: similarity + recency + hierarchy | ✅ |

### Machine Reality

| Concern | Reality | Mitigation |
|---------|---------|------------|
| 2016 Mac too slow? | FastEmbed: 50-100ms per fact | Background async extraction |
| 16GB RAM enough? | FastEmbed: 150MB, SQLite: negligible | Yes, plenty of headroom |
| No GPU? | FastEmbed optimized for CPU | Not a problem |
| Intel Mac obsolete? | ONNX Runtime supports x86_64 | Supported |

### Technical Reality

| Concern | Reality | Mitigation |
|---------|---------|------------|
| File watcher too slow? | inotify/fsevents is kernel-level, ~10ms | Not a problem |
| SQLite at scale? | Handles 100K+ rows fine | Archive old memories |
| hnswlib corruption? | Atomic saves, backups | Backup on compaction |
| User annoyed by prompts? | Auto-promote after 3 "y", suppress after 3 "n" | Self-learning |

---

## Revised Component Stack

| Component | Library | Confidence |
|-----------|---------|------------|
| **Embeddings** | FastEmbed (BAAI/bge-small-en-v1.5) | 95% |
| **Vector search** | hnswlib | 95% |
| **Text search** | SQLite FTS5 | 95% |
| **Metadata** | SQLite tables | 95% |
| **Config** | pydantic-settings + TOML | 95% |
| **CLI** | click + rich | 95% |
| **File watching** | watchdog | 95% |
| **UI** | rich (terminal) | 95% |

---

## Risk Assessment

| Risk | Probability | Impact | Mitigation |
|------|-------------|--------|------------|
| FastEmbed doesn't install on Intel Mac | Low | High | Fallback to sentence-transformers |
| File watcher misses rapid changes | Low | Medium | Poll every 100ms as backup |
| User overwhelmed by Curious prompts | Medium | Medium | Start conservative, learn preferences |
| SQLite corruption | Low | High | WAL mode, periodic backups |
| hnswlib index corruption | Low | High | Save snapshots, rebuild from SQLite |
| Embeddings too slow | Low | Medium | Async processing, queue if needed |

---

## Final Architecture (Reality-Checked)

```
Kimi Session (anywhere in ~/)
    │
    ├── On Start ──▶ Load memories from:
    │   • Current directory
    │   • Parent directories  
    │   • Global context
    │
    ├── Each Turn ──▶ File watcher detects wire.jsonl change
    │   │
    │   └── Daemon ──▶ Parse turn
    │       │
    │       ├── Extract candidates
    │       │   └── FastEmbed (50-100ms per fact)
    │       │
    │       ├── Curious tier: Ask user?
    │       │   ├── "y" → Store in SQLite + hnswlib
    │       │   ├── "n" → Discard, learn pattern
    │       │   ├── "always" → Auto-extract this pattern
    │       │   └── "never" → Auto-skip this pattern
    │       │
    │       └── High confidence → Auto-store
    │
    └── On Query ──▶ Retrieve:
        • Vector similarity (hnswlib)
        • FTS5 text search
        • Recent context
        • Hierarchical (parent dirs)
        └── Merge & inject into Kimi context

Storage (~250MB total):
    ~/.kimi/kemosabe/
    ├── memory.db (SQLite, ~50MB at scale)
    ├── vectors.idx (hnswlib, ~100MB at scale)
    ├── vectors.map (ID mapping, ~10MB)
    └── config.toml (settings)
```

---

## Command Reference (Final)

```bash
# Daemon
$ km daemon start          # Start background daemon
$ km daemon stop           # Stop daemon
$ km daemon status         # Check if running

# Memories
$ km memories              # List all memories
$ km memories --search "dashboard"
$ km memories --project ~/Projects/the-job
$ km memories --category preference
$ km inspect <id>          # View + edit single memory

# Curious tier
$ km curious --preview     # See what would be extracted
$ km curious --config      # Edit Curious tier settings

# Management
$ km pin "always use aerospace-ui"     # Create permanent memory
$ km forget <id>                       # Archive memory
$ km restore <id>                      # Restore from archive
$ km feedback --query "x" --result <id> --relevant

# Shell integration
$ km shell-integration --install
$ km shell-integration --uninstall

# Status
$ km status                # Full status
$ km status --compact      # One line
```

---

## Go/No-Go Decision

**Can we build this on your 2016 Mac?** 

✅ **YES.** FastEmbed + hnswlib + SQLite will run comfortably.

**Will it achieve the goals?**

✅ **YES.** Universal coverage, continuous learning, similarity-based recall.

**Is the complexity justified?**

✅ **YES.** ~550 lines of code, mostly glue. Heavy lifting done by libraries.

---

## Next Step

**Approve this reality-checked plan → I start Phase 1 implementation.**

Files ready to create:
1. `kimi_subconscious/__init__.py` - Package init
2. `kimi_subconscious/config.py` - pydantic-settings
3. `kimi_subconscious/storage/db.py` - SQLite schema
4. `kimi_subconscious/storage/vectors.py` - hnswlib wrapper
5. `kimi_subconscious/daemon.py` - File watcher
6. `kimi_subconscious/extraction/curious.py` - Curious tier
7. `kimi_subconscious/cli.py` - Click commands
8. `pyproject.toml` - Package metadata

**Estimated Phase 1:** 5-7 days of implementation.
