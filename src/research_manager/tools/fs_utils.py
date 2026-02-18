"""Filesystem utilities with conservative safety defaults."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Iterable, List, Optional


def repo_base() -> Path:
    # src/research_manager/tools/fs_utils.py -> repo root is 3 levels up
    return Path(__file__).resolve().parents[3]


def safe_resolve(rel_path: str, allow_roots: Optional[Iterable[str]] = None) -> Path:
    """Resolve a repo-relative path and enforce it stays within allowed roots.

    allow_roots: iterable of repo-relative directory prefixes, e.g. ["memory", "projects"].
    If None, defaults to ["memory"].
    """
    base = repo_base()
    p = (base / rel_path).resolve()
    if allow_roots is None:
        allow_roots = ["memory"]

    allowed = []
    for root in allow_roots:
        allowed.append((base / root).resolve())

    if not any(str(p).startswith(str(a) + os.sep) or p == a for a in allowed):
        raise ValueError(f"Path not allowed: {rel_path}")
    return p


def read_text(rel_path: str, allow_roots: Optional[Iterable[str]] = None, max_chars: int = 200_000) -> str:
    p = safe_resolve(rel_path, allow_roots=allow_roots)
    text = p.read_text(encoding="utf-8")
    if len(text) > max_chars:
        return text[:max_chars] + "\n\n...[TRUNCATED]"
    return text


def write_text(rel_path: str, content: str, allow_roots: Optional[Iterable[str]] = None) -> None:
    p = safe_resolve(rel_path, allow_roots=allow_roots)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")


def list_files(rel_dir: str, pattern: str = "*", allow_roots: Optional[Iterable[str]] = None, max_results: int = 2000) -> List[str]:
    d = safe_resolve(rel_dir, allow_roots=allow_roots)
    out = []
    for fp in d.glob(pattern):
        if fp.is_file():
            out.append(str(fp.relative_to(repo_base())))
        if len(out) >= max_results:
            break
    return sorted(out)
