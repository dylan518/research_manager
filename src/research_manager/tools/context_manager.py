"""Context history management utilities.

Manages index.jsonl by creating snapshots/summaries and optional pruning.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List


@dataclass
class ContextPaths:
    index_path: Path
    memory_dir: Path


def read_jsonl(path: Path) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    if not path.exists():
        return out
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
            if isinstance(obj, dict):
                out.append(obj)
        except json.JSONDecodeError:
            continue
    return out


def write_jsonl(path: Path, items: List[Dict[str, Any]]) -> None:
    path.write_text("\n".join(json.dumps(it, ensure_ascii=True) for it in items) + "\n", encoding="utf-8")


def append_jsonl(path: Path, item: Dict[str, Any]) -> None:
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(item, ensure_ascii=True) + "\n")


def snapshot_index(paths: ContextPaths, label: str = "snapshot") -> Dict[str, Any]:
    ts = int(time.time())
    items = read_jsonl(paths.index_path)
    paths.memory_dir.mkdir(parents=True, exist_ok=True)
    snap_path = paths.memory_dir / f"index_snapshot_{ts}_{label}.jsonl"
    write_jsonl(snap_path, items)
    return {"ok": True, "snapshot": str(snap_path), "count": len(items)}


def extract_chat_messages(items: List[Dict[str, Any]]) -> List[Dict[str, str]]:
    msgs: List[Dict[str, str]] = []
    for it in items:
        role = it.get("role")
        content = it.get("content")
        if isinstance(role, str) and isinstance(content, str) and role in {"user", "assistant", "system"}:
            msgs.append({"role": role, "content": content})
    return msgs


def format_for_summary(items: List[Dict[str, Any]], max_chars: int = 120_000) -> str:
    msgs = extract_chat_messages(items)
    text = "\n\n".join([f"{m['role'].upper()}: {m['content']}" for m in msgs])
    if len(text) > max_chars:
        text = text[-max_chars:]
    return text


def write_summary_markdown(paths: ContextPaths, summary_md: str, label: str = "summary") -> str:
    ts = int(time.time())
    paths.memory_dir.mkdir(parents=True, exist_ok=True)
    out_path = paths.memory_dir / f"conversation_{ts}_{label}.md"
    out_path.write_text(summary_md, encoding="utf-8")
    return str(out_path)


def prune_index_keep_last_messages(paths: ContextPaths, keep_last: int = 50) -> Dict[str, Any]:
    """Keep only last N user/assistant/system messages.

Conservative: keeps items after the earliest kept message index.
Prefer snapshot before pruning.
"""
    items = read_jsonl(paths.index_path)
    msg_idxs = [i for i, it in enumerate(items) if it.get("role") in {"user", "assistant", "system"} and isinstance(it.get("content"), str)]
    if not msg_idxs:
        return {"ok": True, "kept": 0, "original": len(items)}
    keep_last = max(1, keep_last)
    start_idx = msg_idxs[-keep_last] if len(msg_idxs) >= keep_last else msg_idxs[0]
    pruned = items[start_idx:]
    write_jsonl(paths.index_path, pruned)
    return {"ok": True, "original": len(items), "kept": len(pruned), "start_index": start_idx}


def prune_index_keep_last_dialog_turns(paths: ContextPaths, keep_last_turns: int = 80) -> Dict[str, Any]:
    """Aggressively prune index.jsonl by keeping only the last N dialog messages (user/assistant/system).

    Drops older tool call artifacts entirely. This WILL break tool-call threading, but keeps future context small.
    Prefer snapshot before pruning.
    """
    items = read_jsonl(paths.index_path)
    msgs = [it for it in items if it.get("role") in {"user", "assistant", "system"} and isinstance(it.get("content"), str)]
    keep_last_turns = max(1, keep_last_turns)
    kept_msgs = msgs[-keep_last_turns:] if len(msgs) > keep_last_turns else msgs
    write_jsonl(paths.index_path, kept_msgs)
    return {"ok": True, "original": len(items), "original_messages": len(msgs), "kept": len(kept_msgs)}
