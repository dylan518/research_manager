from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from research_manager.config import get_rm_env


def repo_root() -> Path:
    # src/research_manager/state/paths.py -> repo root is 3 levels up
    return Path(__file__).resolve().parents[3]


@dataclass(frozen=True)
class StatePaths:
    env_name: str
    root: Path
    state_dir: Path
    generated_dir: Path
    index_jsonl: Path
    instructions_md: Path
    env_file: Path


def default_state_paths() -> StatePaths:
    root = repo_root()
    env_name = get_rm_env()
    state_dir = root / "state" / env_name
    generated_dir = state_dir / "generated"
    return StatePaths(
        env_name=env_name,
        root=root,
        state_dir=state_dir,
        generated_dir=generated_dir,
        index_jsonl=state_dir / "index.jsonl",
        instructions_md=root / "instructions.md",
        env_file=root / ".env",
    )
