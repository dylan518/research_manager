"""Project briefs: summarize project docs into structured JSON."""

from __future__ import annotations

import json
import re
import time
import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional


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


def _heuristic_brief(fp: Path, base_dir: Path) -> Dict[str, Any]:
    """Fallback: extract one_liner from file without LLM."""
    rel = str(fp.relative_to(base_dir))
    try:
        text = fp.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        text = ""
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    # Prefer "One-liner:" header if present
    one_liner = ""
    for ln in lines:
        m = re.match(r"(?i)one.?liner\s*[:\-]\s*(.+)", ln)
        if m:
            one_liner = m.group(1).strip()
            break
    if not one_liner:
        # Fall back to second non-empty line (skip heading)
        raw = lines[1] if len(lines) > 1 else (lines[0] if lines else "")
        one_liner = re.sub(r"^#+\s*", "", raw)[:220]
    return {
        "project_name": fp.stem,
        "one_liner": one_liner,
        "goal": "",
        "current_state": "",
        "key_ideas": [],
        "open_questions": [],
        "next_actions": [],
        "keywords": [],
        "_heuristic": True,
    }


def refresh_briefs(
    *,
    source_files: List[Path],
    base_dir: Path,
    paths: BriefPaths,
    llm_summarize_fn: Optional[Callable[[str], str]] = None,
    force: bool = False,
) -> Dict[str, Any]:
    """Refresh briefs for source_files.

    llm_summarize_fn(prompt: str) -> str should return JSON text.
    If None or if it raises, falls back to heuristic brief so result is never empty.
    """
    meta: Dict[str, Any] = load_json(paths.meta_path, {})
    briefs: Dict[str, Any] = load_json(paths.briefs_path, {})

    updated, skipped, errors = [], [], []

    for fp in source_files:
        rel = str(fp.relative_to(base_dir))
        try:
            text = fp.read_text(encoding="utf-8")
        except Exception as exc:
            briefs[rel] = _heuristic_brief(fp, base_dir)
            briefs[rel]["_read_error"] = str(exc)
            updated.append(rel)
            continue

        sha = sha256_text(text)
        if not force and meta.get(rel, {}).get("sha256") == sha:
            skipped.append(rel)
            continue

        obj: Dict[str, Any] = {}
        if llm_summarize_fn is not None:
            try:
                prompt = make_prompt(rel, text)
                raw = llm_summarize_fn(prompt)
                try:
                    obj = json.loads(raw)
                except Exception:
                    obj = {"parse_error": True, "raw": raw[:4000]}
            except Exception as exc:
                errors.append({"rel": rel, "error": str(exc)})
                obj = {}

        if not obj or obj.get("parse_error"):
            obj = _heuristic_brief(fp, base_dir)
            if not obj:
                obj = _heuristic_brief(fp, base_dir)

        briefs[rel] = obj
        meta[rel] = {"sha256": sha, "updated_at": time.time()}
        updated.append(rel)

    write_json(paths.briefs_path, briefs)
    write_json(paths.meta_path, meta)

    return {"ok": True, "updated": updated, "skipped": skipped, "errors": errors}
