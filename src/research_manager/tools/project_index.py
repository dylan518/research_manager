from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple


@dataclass
class ProjectIndexConfig:
    repo_root: Path
    memory_dir: Path
    briefs_path: Path
    output_path: Path


def _load_briefs(briefs_path: Path) -> Dict[str, dict]:
    if not briefs_path.exists():
        return {}
    return json.loads(briefs_path.read_text(encoding='utf-8'))


def _is_project_memo(p: Path) -> bool:
    name = p.name
    if name.startswith('_'):
        return False
    if name.startswith('conversation_'):
        return False
    if 'compact_summary' in name:
        return False
    if name.startswith('index_snapshot_'):
        return False
    return True


def _extract_one_liner(p: Path, briefs: Dict[str, dict]) -> str:
    """Return one_liner from briefs (prefer 'One-liner:' header) or heuristic fallback."""
    # Try briefs keyed by relative path (may use str(p) or relative key)
    for key in (str(p), p.name):
        brief = briefs.get(key) or {}
        ol = (brief.get('one_liner') or '').strip()
        if ol:
            return ol

    # Heuristic: look for "One-liner: ..." header in file
    try:
        txt = p.read_text(encoding='utf-8', errors='ignore')
    except Exception:
        return ''
    for ln in txt.splitlines():
        ln = ln.strip()
        m = re.match(r'(?i)one.?liner\s*[:\-]\s*(.+)', ln)
        if m:
            return m.group(1).strip()

    # Fallback: second non-empty non-heading line
    lines = [l.strip() for l in txt.splitlines() if l.strip()]
    raw = lines[1] if len(lines) > 1 else (lines[0] if lines else '')
    return re.sub(r'^#+\s*', '', raw)[:220]


def generate_project_index(cfg: ProjectIndexConfig) -> str:
    briefs = _load_briefs(cfg.briefs_path)

    projects: List[Tuple[str, str, str]] = []
    for p in sorted(cfg.memory_dir.glob('*.md')):
        if not _is_project_memo(p):
            continue
        one_liner = _extract_one_liner(p, briefs)
        projects.append((p.stem, f"memory/{p.name}", one_liner))

    out: List[str] = ["# Project Index (auto-generated)", "", "## memory/ (project memos)"]
    for key, rel, ol in projects:
        out.append(f"- **{key}** ({rel}): {ol}")

    out += [
        "",
        "## tools/ (capabilities)",
        "- src/research_manager/tools/context_manager.py: snapshot/summarize/prune index.jsonl context",
        "- src/research_manager/tools/claude_code.py: run Claude Code CLI",
        "- src/research_manager/tools/briefs.py: refresh project briefs (cached)",
        "- src/research_manager/tools/fs_utils.py: safe file read/write/list",
        "",
        "## How to use",
        "- Startup context is intentionally hyper-brief.",
        "- To work on a project: open its file with python (read_text) and quote relevant sections.",
    ]

    return "\n".join(out) + "\n"


def write_project_index(cfg: ProjectIndexConfig) -> Path:
    text = generate_project_index(cfg)
    cfg.output_path.parent.mkdir(parents=True, exist_ok=True)
    cfg.output_path.write_text(text, encoding='utf-8')
    return cfg.output_path
