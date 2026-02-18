from tools.claude_code import which_claude


def test_which_claude_returns_dict():
    d = which_claude()
    assert isinstance(d, dict)
    assert 'claude' in d
