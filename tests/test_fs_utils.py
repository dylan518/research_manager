import pytest
from research_manager.tools import fs_utils


def test_safe_resolve_allows_memory():
    p = fs_utils.safe_resolve('memory', allow_roots=['memory'])
    assert p.name == 'memory'


def test_safe_resolve_blocks_repo_escape(tmp_path):
    with pytest.raises(ValueError):
        fs_utils.safe_resolve('../secret.txt', allow_roots=['memory'])
