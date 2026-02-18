"""Project briefs: summarize project docs into structured JSON."""

from __future__ import annotations

import json
import time
import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def load_json(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def write_json(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")


@dataclass
class BriefPaths:
    briefs_path: Path
    meta_path: Path


BRIEF_SCHEMA = {
    "project_name": "string",
    "one_liner": "string",
    "goal": "string",
    "current_state": "string",
    "key_ideas": ["string"],
    "open_questions": ["string"],
    "next_actions": ["string"],
    "keywords": ["string"],
}


def make_prompt(rel: str, text: str) -> str:
    return f"""You are summarizing a project research memo for later reuse.
Return STRICT JSON only. No markdown.

Schema (keys required):
{json.dumps(BRIEF_SCHEMA, indent=2)}

FILE: {rel}

CONTENT:
{text}
"""


def refresh_briefs(
    *,
    source_files: List[Path],
    base_dir: Path,
    paths: BriefPaths,
    llm_summarize_fn,
    force: bool = False,
) -> Dict[str, Any]:
    """Refresh briefs for source_files.

    llm_summarize_fn(prompt: str) -> str should return JSON text.
    """
    meta: Dict[str, Any] = load_json(paths.meta_path, {})
    briefs: Dict[str, Any] = load_json(paths.briefs_path, {})

    updated, skipped = [], []

    for fp in source_files:
        rel = str(fp.relative_to(base_dir))
        text = fp.read_text(encoding="utf-8")
        sha = sha256_text(text)
        if not force and meta.get(rel, {}).get("sha256") == sha:
            skipped.append(rel)
            continue

        prompt = make_prompt(rel, text)
        raw = llm_summarize_fn(prompt)
        try:
            obj = json.loads(raw)
        except Exception:
            obj = {"parse_error": True, "raw": raw[:4000]}

        briefs[rel] = obj
        meta[rel] = {"sha256": sha, "updated_at": time.time()}
        updated.append(rel)

    write_json(paths.briefs_path, briefs)
    write_json(paths.meta_path, meta)

    return {"ok": True, "updated": updated, "skipped": skipped}
