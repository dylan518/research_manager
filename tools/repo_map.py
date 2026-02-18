"""Repo mapping and discovery."""

from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Dict, Any, Set


def build_repo_map(base_dir: Path, max_files: int = 5000, skip_dirs: Set[str] | None = None) -> Dict[str, Any]:
    if skip_dirs is None:
        skip_dirs = {".git", "__pycache__", ".venv", "venv", ".pytest_cache"}
    repo_map: Dict[str, Any] = {"generated_at": time.time(), "files": [], "truncated": False}
    count = 0
    for root, dirs, files in os.walk(base_dir):
        dirs[:] = [d for d in dirs if d not in skip_dirs]
        for name in files:
            if name.startswith('.'):
                continue
            rel = os.path.relpath(os.path.join(root, name), base_dir)
            repo_map["files"].append(rel)
            count += 1
            if count >= max_files:
                repo_map["truncated"] = True
                return repo_map
    return repo_map
