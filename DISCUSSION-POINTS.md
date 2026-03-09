# Discussion Points — Universal Subconscious

## TL;DR

I understand what you want now: **human-like subconscious that works everywhere, continuously learns, and extrapolates from past to present.**

This is fundamentally different from the current project-based, sync-at-boundaries architecture.

---

## The Research Findings

Existing open-source memory systems show us the way:

| System | What They Do Right |
|--------|-------------------|
| **Mem0** | Layered memory (working → short-term → long-term) + continuous extraction |
| **Zep/Graphiti** | Temporal knowledge graphs + hybrid retrieval (semantic + keyword + graph) |
| **LangChain** | Pluggable memory types (buffer, summary, vector, entity) |

**Key insight:** They do **continuous extraction**, not just boundary sync.

---

## The Architecture Shift Required

### Current (What We Have)
```
Session Start ──▶ Sync to Letta ──▶ [Session Active] ──▶ Session End ──▶ Sync
```
Project-based, batched, file-only injection.

### Target (What You Want)
```
Any Directory ──▶ Load User Memory + Similar Context
       │
       ▼
User Input ──▶ Search Similar Past Inputs ──▶ Inject ──▶ Kimi Responds
       │                                                      │
       ▼                                                      ▼
Extract Facts ◀── Kimi Thoughts ◀── Tool Results
       │
       ▼
Update Memory (immediate, not batched)
```
Universal, continuous, similarity-based.

---

## What "Human-Like" Actually Means

| Human Trait | Technical Implementation |
|-------------|-------------------------|
| Walk into room, know context | Hierarchical project inheritance (child sees parent context) |
| Remember similar situations | Vector similarity search across ALL sessions |
| Extrapolate past → present | Retrieve relevant facts, not just project-specific |
| Continuous learning | Extract facts every turn, not just at end |
| Forget unimportant things | Importance scoring + compression over time |

---

## The Critical Questions

I need your decisions on these before implementing:

---

### 1. Privacy Boundaries ⚠️ CRITICAL

**Scenario:** You're working on `~/Projects/client-a/` and ask "dashboard design." Should kimi recall the dashboard you built for `~/Projects/client-b/` 6 months ago?

**Option A: Universal (Cross-Project)**
- ✅ Most useful — leverages all your work
- ⚠️ Risk of leaking client-specific details across projects

**Option B: Project-Isolated**
- ✅ Privacy-safe
- ❌ Misses relevant past work

**Option C: Hybrid (Tags)**
- Mark memories as `private`, `shared`, `technique`, `pattern`
- `private` = stay in project
- `shared`/`technique` = available everywhere
- ✅ Balanced, but requires classification

**Your call?**

---

### 2. Extraction Granularity

**How aggressively should we extract memories?**

**Option A: Every Turn (Continuous)**
- Extract facts from every user input + kimi response
- ✅ Most comprehensive
- ⚠️ High volume, may extract noise

**Option B: Smart Filter**
- Only extract on:
  - Explicit keywords ("remember", "important")
  - Corrections ("no, that's wrong")
  - Breakthroughs ("finally works!")
  - Tool errors/failures
- ✅ Lower volume, higher signal
- ⚠️ May miss implicit learnings

**Option C: Explicit Only**
- Only extract when you say "subconscious: remember that..."
- ✅ Full control
- ❌ High friction

**Your preference?**

---

### 3. Memory Lifetime

**How long should memories live?**

**Option A: Forever**
- Keep everything
- ✅ Complete history
- ⚠️ Storage bloat, retrieval noise

**Option B: Tiered Expiration**
- Working: session only
- Short-term: 30 days
- Long-term: promoted facts only
- ✅ Natural forgetting
- ⚠️ May lose important context

**Option C: Manual Archive**
- Auto-expire after 90 days
- Manual "pin" to keep important
- ✅ User control
- ❌ Requires maintenance

**Your choice?**

---

### 4. Kimi Integration Method

**How do we capture kimi's thoughts in real-time?**

**Option A: File Watcher (Current, Safe)**
- Watch `wire.jsonl` for changes
- ✅ No kimi-cli modifications
- ⚠️ Small delay (seconds)

**Option B: Patched kimi-cli (Risky)**
- Patch kimi source (like ai-config/kimi/patches/)
- Add hook after each turn
- ✅ Immediate, clean
- ⚠️ Breaks on kimi updates

**Option C: IPC/Plugin (Future)**
- Wait for kimi's official plugin system
- ✅ Clean, supported
- ❌ Unknown timeline

**Risk tolerance?**

---

### 5. Backend Strategy

**What should be the source of truth?**

**Option A: Letta-First (Current Path)**
- Keep using Letta as primary backend
- Enhance how we interact with it
- ✅ Leverages existing work
- ⚠️ API latency, rate limits

**Option B: Local-First + Letta Sync**
- SQLite + FAISS locally for speed
- Async sync to Letta for consolidation
- ✅ Fast (<100ms), works offline
- ⚠️ More complex, dual storage

**Option C: Migrate to OSS (Mem0/Zep)**
- Replace Letta with Mem0 or Zep
- ✅ Purpose-built, better APIs
- ⚠️ Migration effort, new dependencies

**Preference?**

---

### 6. Visibility/Debugging

**How much should you see the subconscious working?**

**Option A: Silent (Magic)**
- Memories injected silently
- ✅ No noise
- ⚠️ Opaque, hard to debug

**Option B: Verbose (Transparent)**
- Show "Recalled 3 memories" on each turn
- Display what was recalled
- ✅ Understandable
- ⚠️ Chatty, may annoy

**Option C: On-Demand**
- Silent by default
- `/subconscious show` to inspect
- `/subconscious recall <query>` to search
- ✅ Best of both
- ❌ Requires learning commands

**UX preference?**

---

## My Recommendations (If You Want Them)

| Decision | My Rec | Reasoning |
|----------|--------|-----------|
| Privacy | **Hybrid (Tags)** | Balance utility vs safety |
| Extraction | **Smart Filter** | 80% of value, 20% of noise |
| Lifetime | **Tiered** | Natural, like human memory |
| Integration | **File Watcher** | Safe, proven, no deps |
| Backend | **Local-First + Letta** | Speed + consolidation |
| Visibility | **On-Demand** | Power when needed, silence otherwise |

---

## The "Linus" Perspective

What would Linus Torvalds say?

**Good:**
- ✅ Text-based storage (SQLite + markdown)
- ✅ Composable (can swap backends)
- ✅ Performance-first (local caching)
- ✅ Do one thing well (memory layer only)

**Risky:**
- ⚠️ Hybrid local/cloud adds complexity
- ⚠️ Continuous extraction = high volume
- ⚠️ Privacy boundaries are fuzzy

**Suggestion:** Start simple (local-only), add complexity only when needed.

---

## Next Steps

1. **You answer the 6 questions above** (can be brief)
2. **I create final implementation plan** aligned with your choices
3. **We build Phase 1** (MVP with core functionality)
4. **Iterate based on usage**

**Ready when you are.**
