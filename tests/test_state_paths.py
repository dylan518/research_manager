from research_manager.state.paths import default_state_paths


def test_default_state_paths_uses_dev_by_default(monkeypatch):
    monkeypatch.delenv("RM_ENV", raising=False)
    paths = default_state_paths()
    assert paths.env_name == "dev"
    assert str(paths.index_jsonl).endswith("state/dev/index.jsonl")
    assert str(paths.generated_dir).endswith("state/dev/generated")


def test_default_state_paths_uses_prod(monkeypatch):
    monkeypatch.setenv("RM_ENV", "prod")
    paths = default_state_paths()
    assert paths.env_name == "prod"
    assert str(paths.index_jsonl).endswith("state/prod/index.jsonl")
    assert str(paths.generated_dir).endswith("state/prod/generated")
