Got it. v0 should feel like **Cursor**, but for *research context*, with a **deep research chat** in the middle. Less “agent pipeline that runs” and more “interactive workspace that remembers and retrieves.”

Here’s an implementation plan that matches that.

---

## Core concept for v0

A **chat-first research workspace** where a strong model (GPT-5) can:

* pull in papers and notes on demand
* keep a persistent research context for each “thread/idea”
* let you *curate* what gets saved (nothing auto-saves unless you choose)
* retrieve relevant snippets from your library (semantic + keyword)
* help you write and refine a thesis doc, but only when you ask

Think: **Cursor’s side panel + chat**, except the files are *papers, notes, and excerpts*.

---

## v0 goals

### What v0 must do

1. **Chat-first “Research Thread”**

   * Each thread has a *pinned context* (your thesis-in-progress, key claims, definitions, constraints).
   * The model can reference that pinned context every time.

2. **Paper library that’s easy to use**

   * Save paper → parse → chunk → embed → store.
   * Search by semantic similarity and keyword.
   * Show “related papers” for a given paper or excerpt.

3. **Bring-your-own control**

   * Model suggests what to save, what to read next, and what to pin.
   * You approve with one click/command.

4. **Fast referencing**

   * When the model uses paper content, it cites *paper + section/snippet id*.
   * You can open the cited snippet immediately.

### What v0 explicitly should NOT do

* Auto-running research workflows in the background
* Auto-updating thesis docs without you asking
* Experiment execution or W&B integration (we’ll design a “results” object later)

---

## v0 UX: what it feels like

### Main layout (Cursor-inspired)

**Left sidebar**

* Research Threads
* Paper Library
* Saved Notes / Excerpts

**Center**

* Chat with “Deep Research GPT-5”

**Right panel**

* Pinned context for the current thread
* “Saved items” for this thread (papers, excerpts, notes)
* “Relevant snippets retrieved for this message”

### Typical flow

You: “I’m exploring verifiability reward for question generators. Pull 10 key papers and show a map of approaches.”

Assistant:

* returns list of candidates with short reasons
* offers buttons / commands:

  * `save paper #3 #5 #7`
  * `open #5`
  * `find similar to #7`
  * `pin this definition`
  * `add to thread summary`

You: “save 3,5,7. open 5. summarize eval setups.”

Assistant:

* reads the paper you saved
* produces summary + extracted eval details
* proposes what to pin

You choose what gets pinned.

---

## Data model (minimal, flexible)

You only need 4 objects for v0:

### `Thread`

* `thread_id`
* `title`
* `pinned_context_md` (manually curated, model can suggest edits)
* `saved_papers[]`
* `saved_excerpts[]`
* `chat_log_ref` (optional)

### `Paper`

* `paper_id` (arxiv/doi/custom)
* `metadata` (title/authors/year/links)
* `pdf_path`
* `text_chunks[]` (with chunk ids)
* `embeddings_ref`

### `Excerpt`

A slice of a paper (or web snippet) you decided matters.

* `excerpt_id`
* `source` (paper_id + chunk_id range)
* `quote` (small)
* `note` (your annotation)
* `tags[]`
* `linked_thread_id`

### `Note`

* `note_id`
* `content_md`
* `linked_thread_id`
* `links[]` (papers/excerpts)

Key design rule: **Nothing is “true context” unless it’s pinned or saved.**

---

## Retrieval (the engine that makes it work)

You want 3 retrieval modes:

1. **Thread-aware retrieval**

   * Search only within papers/excerpts saved to the thread.

2. **Global library retrieval**

   * Search across all saved papers.

3. **“Similar to X” retrieval**

   * Given a paper or excerpt, return nearest neighbors + why.

Implementation:

* Keyword search: SQLite FTS5
* Semantic search: FAISS (local) or Chroma
* Hybrid scoring: keep simple

---

## Chat orchestration (how GPT-5 uses context)

Each chat turn should have:

1. **Pinned context** (short, curated)
2. **Conversation recent messages** (normal)
3. **Retrieved snippets** (top K chunks from library/thread)
4. **Tool access**

   * search papers (arXiv / Semantic Scholar / web)
   * ingest/save paper
   * open/cite chunk
   * find similar chunks/papers
   * update pinned context (suggest diff)

Important: GPT-5 should **never** hallucinate paper content.
If it says “the paper claims X,” it must have retrieved the chunk and cite it.

---

## Tool surface (v0 “commands”)

Make it feel like Cursor slash-commands.

### Core

* `/new-thread "title"`
* `/pin` (pin selected text into thread context)
* `/unpin`
* `/save-paper <arxiv|url|pdf>`
* `/open-paper <id>`
* `/save-excerpt <paper_id:chunk_id>`
* `/search "query" [thread|global]`
* `/similar <paper_id|excerpt_id>`
* `/summarize <paper_id> [focus=method|eval|claims]`
* `/map` (cluster saved papers into themes)

### Optional nice-to-have

* `/export-thread` → markdown bundle (thread summary + bibliography + excerpts)

---

## Implementation plan (build order)

### Milestone 1 — Library + parsing (foundation)

* Paper ingest:

  * arXiv id → metadata + PDF
  * PDF → text extraction
  * chunking (section-aware if possible, else fixed tokens)
* Store:

  * SQLite tables for metadata + chunks
  * embeddings in FAISS/Chroma

Deliverable: you can save a paper and search it.

---

### Milestone 2 — Thread context + saved items

* Threads stored in SQLite + filesystem markdown
* Ability to link papers/excerpts to threads
* Pinned context is a markdown doc per thread

Deliverable: threads + pinned context + saved items.

---

### Milestone 3 — Chat interface + retrieval augmentation

* Simple web UI (or TUI) with:

  * chat
  * left sidebar threads
  * right panel pinned context
* Implement retrieval injection:

  * thread retrieval first
  * fall back to global if needed
* Inline citations point to paper chunk ids

Deliverable: Cursor-like chat that “knows” your saved library.

---

### Milestone 4 — Web paper discovery (interactive, not automated)

* Search tool:

  * “find papers” returns candidates with metadata
* One-click save/ingest

Deliverable: “find → shortlist → save” loop in-chat.

---

### Milestone 5 — Similarity + mapping

* `similar(paper)` and `similar(excerpt)`
* `map(thread)` clusters saved papers + names clusters

Deliverable: “show me adjacent literature” instantly.

---

## Tech stack suggestion (light, fast)

* Backend: Python (FastAPI)
* DB: SQLite (FTS5)
* Vector: FAISS (fast, local)
* PDF parse: PyMuPDF
* UI: simple web app (Next.js or minimal React) OR even a local Electron/Tauri app later
* Model: GPT-5 via API, with tool calls for retrieval + ingest

---

## What “done” means for v0

You can:

1. Start a thread
2. Ask GPT-5 to find papers
3. Save a subset
4. Open and quote chunks
5. Ask for “similar papers”
6. Pin context you care about
7. Continue chatting with persistent context and grounded citations

That’s the product.

---

If you want to start building immediately, next I can output:

* the exact SQLite schema (threads, papers, chunks, excerpts)
* the API endpoints (`/search`, `/ingest`, `/similar`, `/threads/...`)
* the chat prompt template (how pinned context + retrieved chunks are injected)
* and a minimal UI wireframe (Cursor-like panels)
