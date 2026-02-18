from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List


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
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(it, ensure_ascii=True) for it in items) + "\n", encoding="utf-8")


def append_jsonl(path: Path, item: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(item, ensure_ascii=True) + "\n")


def only_chat_messages(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    allowed_roles = {"user", "assistant", "system", "developer"}
    out: List[Dict[str, Any]] = []
    for it in items:
        role = it.get("role")
        content = it.get("content")
        if isinstance(role, str) and role in allowed_roles and content is not None:
            out.append({"role": role, "content": content})
    return out
