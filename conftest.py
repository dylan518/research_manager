"""Ensure the repo root is on sys.path so minimal_memory_chat is importable."""
import sys
from pathlib import Path

ROOT = Path(__file__).parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
