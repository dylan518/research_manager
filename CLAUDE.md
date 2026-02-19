# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Local AI research workspace: a tool-enabled chat runtime where an LLM (OpenAI) can execute Python, search academic papers (Semantic Scholar), manage a persistent JSONL-based chat history, and invoke Claude Code CLI as a sub-tool.

## Environment Setup

```bash
pip install -e .
pip install -r requirements.txt
cp .env.example .env  # fill in OPENAI_API_KEY, ANTHROPIC_API_KEY, S2_KEY
```

## Commands

```bash
# Run the chat application
python minimal_memory_chat.py

# Run all tests
pytest tests/

# Run a single test file
pytest tests/test_fs_utils.py

# Run a single test
pytest tests/test_semantic_scholar_client.py::test_search_papers

# Analyze dev trace logs
python scripts/summarize_trace.py state/dev/traces/<session>.jsonl
```

## Architecture

### Entry Point
`minimal_memory_chat.py` — monolithic chat loop that wires everything together. It owns the JSONL index (`index.jsonl`), constructs the system prompt (including `instructions.md` + memory context), and exposes a `python` tool to the LLM for all side effects.

### Key Design Patterns

**JSONL persistence**: Chat history, snapshots, and trace logs are all line-delimited JSON. `state/index_store.py` and `tools/context_manager.py` share this pattern.

**Path safety**: All file access by the LLM goes through `tools/fs_utils.py`, which enforces that paths stay within allowed roots (default: `memory/`). Directory traversal via `../` is blocked.

**LLM-caching for briefs**: `tools/briefs.py` uses SHA256 of file contents to avoid re-summarizing unchanged project memos. Cache stored in `memory/_project_briefs.json` / `memory/_project_briefs_meta.json`.

**Dev-only telemetry**: `tools/trace_logger.py` emits structured events only when `ENV=dev`. Events include tool calls, memory reads/writes, and summaries. API keys are redacted from all trace payloads.

**Claude Code as sub-tool**: `tools/claude_code.py` spawns the `claude` CLI via subprocess. `which_claude()` searches PATH and `~/.local/bin/`. The LLM calls `run_claude(prompt, cwd=...)` to delegate coding tasks.

### Source Layout

```
src/research_manager/
  clients/semantic_scholar.py   # Semantic Scholar Graph + Recommendations API
  tools/
    briefs.py                   # LLM-cached project brief generation
    claude_code.py              # Claude CLI subprocess integration
    context_manager.py          # JSONL snapshot/prune/summarize
    fs_utils.py                 # Safe sandboxed file I/O
    project_index.py            # Markdown index of memory/*.md projects
    repo_map.py                 # File tree discovery
    trace_logger.py             # Dev telemetry (JSONL event log)
  state/
    index_store.py              # JSONL read/write primitives
    paths.py                    # Centralized path config (StatePaths)
```

### Memory Directory

`memory/` is the LLM's writable workspace:
- `_pinned.md` — human-edited defaults loaded into every session
- `self_learning.md` and other `*.md` files — project memos
- `generated/` — auto-generated artifacts (briefs, snapshots, summaries) — git-ignored

### Protected Files

`instructions.md` is loaded as a system prompt component and the runtime prevents the LLM from overwriting it. Edit it directly to change LLM behavioral defaults.
