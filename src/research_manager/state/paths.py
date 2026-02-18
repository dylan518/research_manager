from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


def repo_root() -> Path:
    # src/research_manager/state/paths.py -> repo root is 4 levels up
    return Path(__file__).resolve().parents[4]


@dataclass(frozen=True)
class StatePaths:
    root: Path
    state_dir: Path
    generated_dir: Path
    index_jsonl: Path
    instructions_md: Path
    env_file: Path


def default_state_paths() -> StatePaths:
    root = repo_root()
    state_dir = root / "state"
    generated_dir = state_dir / "generated"
    return StatePaths(
        root=root,
        state_dir=state_dir,
        generated_dir=generated_dir,
        index_jsonl=state_dir / "index.jsonl",
        instructions_md=root / "instructions.md",
        env_file=root / ".env",
    )
