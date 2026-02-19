"""Integration tests for the core pipeline.

Covers:
- TraceLogger: dev vs prod mode, redaction
- ContextManager: JSONL I/O, snapshot, prune
- run_python tool: execution, stdout, errors, instruction protection, helpers
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest


# ---------------------------------------------------------------------------
# TraceLogger
# ---------------------------------------------------------------------------

class TestTraceLogger:
    def test_dev_mode_writes_event_to_file(self, tmp_path):
        from research_manager.tools.trace_logger import TraceLogger

        trace_path = tmp_path / "trace.jsonl"
        logger = TraceLogger(session_id="sess-test", path=trace_path, env="dev")
        logger.emit(turn_id=1, event_type="test_event", message="hello", data={"key": "val"})

        assert trace_path.exists()
        event = json.loads(trace_path.read_text().strip())
        assert event["event_type"] == "test_event"
        assert event["message"] == "hello"
        assert event["data"]["key"] == "val"
        assert event["session_id"] == "sess-test"
        assert event["turn_id"] == 1
        assert "ts" in event

    def test_prod_mode_emits_nothing(self, tmp_path):
        from research_manager.tools.trace_logger import TraceLogger

        trace_path = tmp_path / "trace.jsonl"
        logger = TraceLogger(session_id="sess-test", path=trace_path, env="prod")
        logger.emit(turn_id=1, event_type="should_not_appear", message="silent")

        assert not trace_path.exists()

    def test_multiple_events_appended(self, tmp_path):
        from research_manager.tools.trace_logger import TraceLogger

        trace_path = tmp_path / "trace.jsonl"
        logger = TraceLogger(session_id="sess-multi", path=trace_path, env="dev")
        logger.emit(turn_id=1, event_type="ev_a", message="first")
        logger.emit(turn_id=2, event_type="ev_b", message="second")

        lines = [l for l in trace_path.read_text().splitlines() if l.strip()]
        assert len(lines) == 2
        assert json.loads(lines[0])["event_type"] == "ev_a"
        assert json.loads(lines[1])["event_type"] == "ev_b"

    def test_digest_payload_redacts_api_key(self, monkeypatch):
        monkeypatch.setenv("OPENAI_API_KEY", "sk-supersecret999")
        from research_manager.tools.trace_logger import digest_payload

        result = digest_payload("Request with sk-supersecret999 in body")
        assert "sk-supersecret999" not in result["preview"]
        assert "[REDACTED]" in result["preview"]
        assert "len" in result
        assert "sha256" in result

    def test_get_trace_logger_uses_rm_env(self, monkeypatch):
        monkeypatch.setenv("RM_ENV", "prod")
        # Force re-evaluation of get_rm_env by importing fresh
        from research_manager.tools.trace_logger import get_trace_logger
        logger = get_trace_logger(session_id="env-test")
        assert logger.env == "prod"

    def test_get_trace_logger_defaults_to_dev(self, monkeypatch):
        monkeypatch.delenv("RM_ENV", raising=False)
        from research_manager.tools.trace_logger import get_trace_logger
        logger = get_trace_logger(session_id="default-test")
        assert logger.env == "dev"


# ---------------------------------------------------------------------------
# ContextManager
# ---------------------------------------------------------------------------

class TestContextManager:
    def test_write_and_read_jsonl_roundtrip(self, tmp_path, monkeypatch):
        monkeypatch.setenv("RM_ENV", "prod")  # suppress trace output
        from research_manager.tools.context_manager import read_jsonl, write_jsonl

        index = tmp_path / "index.jsonl"
        items = [
            {"role": "user", "content": "hello"},
            {"role": "assistant", "content": "hi"},
        ]
        write_jsonl(index, items)
        result = read_jsonl(index)
        assert result == items

    def test_read_jsonl_missing_file_returns_empty(self, tmp_path, monkeypatch):
        monkeypatch.setenv("RM_ENV", "prod")
        from research_manager.tools.context_manager import read_jsonl

        result = read_jsonl(tmp_path / "nonexistent.jsonl")
        assert result == []

    def test_read_jsonl_skips_malformed_lines(self, tmp_path, monkeypatch):
        monkeypatch.setenv("RM_ENV", "prod")
        from research_manager.tools.context_manager import read_jsonl

        index = tmp_path / "index.jsonl"
        index.write_text('{"role":"user","content":"ok"}\nNOT_JSON\n{"role":"assistant","content":"fine"}\n')
        result = read_jsonl(index)
        assert len(result) == 2

    def test_snapshot_creates_timestamped_file(self, tmp_path, monkeypatch):
        monkeypatch.setenv("RM_ENV", "prod")
        from research_manager.tools.context_manager import ContextPaths, snapshot_index, write_jsonl

        index = tmp_path / "index.jsonl"
        memory_dir = tmp_path / "snapshots"
        write_jsonl(index, [{"role": "user", "content": "test"}])

        paths = ContextPaths(index_path=index, memory_dir=memory_dir)
        result = snapshot_index(paths, label="mysnap")

        assert result["ok"] is True
        assert result["count"] == 1
        snap = Path(result["snapshot"])
        assert snap.exists()
        assert "mysnap" in snap.name
        # Snapshot file should contain the original data
        data = json.loads(snap.read_text().strip())
        assert data["role"] == "user"

    def test_prune_keeps_last_n_messages(self, tmp_path, monkeypatch):
        monkeypatch.setenv("RM_ENV", "prod")
        from research_manager.tools.context_manager import (
            ContextPaths, prune_index_keep_last_messages, read_jsonl, write_jsonl,
        )

        index = tmp_path / "index.jsonl"
        items = [
            {"role": "user" if i % 2 == 0 else "assistant", "content": f"msg {i}"}
            for i in range(10)
        ]
        write_jsonl(index, items)

        paths = ContextPaths(index_path=index, memory_dir=tmp_path)
        result = prune_index_keep_last_messages(paths, keep_last=4)

        assert result["ok"] is True
        assert result["original"] == 10
        remaining = read_jsonl(index)
        assert len(remaining) == 4
        assert remaining[-1]["content"] == "msg 9"

    def test_prune_dialog_turns_drops_tool_entries(self, tmp_path, monkeypatch):
        monkeypatch.setenv("RM_ENV", "prod")
        from research_manager.tools.context_manager import (
            ContextPaths, prune_index_keep_last_dialog_turns, read_jsonl, write_jsonl,
        )

        index = tmp_path / "index.jsonl"
        # Mix of chat messages and a tool call entry
        items = [
            {"role": "user", "content": f"q{i}"} for i in range(6)
        ] + [
            {"type": "function_call", "name": "python", "call_id": "c1", "arguments": "{}"}
        ]
        write_jsonl(index, items)

        paths = ContextPaths(index_path=index, memory_dir=tmp_path)
        result = prune_index_keep_last_dialog_turns(paths, keep_last_turns=3)

        assert result["ok"] is True
        remaining = read_jsonl(index)
        # Only last 3 chat messages; tool call entry is dropped
        assert len(remaining) == 3
        assert all(it.get("role") is not None for it in remaining)
        assert remaining[-1]["content"] == "q5"

    def test_format_for_summary_truncates(self, monkeypatch):
        monkeypatch.setenv("RM_ENV", "prod")
        from research_manager.tools.context_manager import format_for_summary

        items = [{"role": "user", "content": "A" * 200}, {"role": "assistant", "content": "B" * 200}]
        result = format_for_summary(items, max_chars=50)
        assert len(result) <= 50


# ---------------------------------------------------------------------------
# run_python tool (via minimal_memory_chat)
# ---------------------------------------------------------------------------

class TestRunPython:
    @pytest.fixture(autouse=True)
    def patched_paths(self, tmp_path, monkeypatch):
        """Patch minimal_memory_chat globals so tests use isolated tmp files."""
        import minimal_memory_chat as mmc

        index = tmp_path / "index.jsonl"
        index.write_text("")
        instructions = tmp_path / "instructions.md"
        instructions.write_text("You are a helpful assistant.")
        env_file = tmp_path / ".env"
        env_file.write_text("")

        monkeypatch.setattr(mmc, "INDEX_PATH", str(index))
        monkeypatch.setattr(mmc, "INSTRUCTIONS_PATH", str(instructions))
        monkeypatch.setattr(mmc, "ENV_PATH", str(env_file))
        monkeypatch.setenv("RM_ENV", "prod")  # suppress trace output
        mmc.PYTHON_GLOBAL_SCOPE.clear()

        self._paths = {"index": index, "instructions": instructions}

    def test_expression_result_is_captured(self):
        import minimal_memory_chat as mmc
        result = mmc.run_python("1 + 1")
        assert result["ok"] is True
        assert result["result"] == 2

    def test_string_expression_result(self):
        import minimal_memory_chat as mmc
        result = mmc.run_python("'hello' + ' world'")
        assert result["ok"] is True
        assert result["result"] == "hello world"

    def test_stdout_is_captured(self):
        import minimal_memory_chat as mmc
        result = mmc.run_python("print('captured output')")
        assert result["ok"] is True
        assert "captured output" in result["stdout"]

    def test_stdout_used_as_result_when_no_expression(self):
        import minimal_memory_chat as mmc
        result = mmc.run_python("print('only stdout')")
        assert result["ok"] is True
        # stdout becomes result when no expression result is set
        assert result["result"] == "only stdout"

    def test_syntax_error_returns_ok_false(self):
        import minimal_memory_chat as mmc
        result = mmc.run_python("def broken(")
        assert result["ok"] is False
        assert "error" in result

    def test_runtime_error_returns_ok_false(self):
        import minimal_memory_chat as mmc
        result = mmc.run_python("1 / 0")
        assert result["ok"] is False
        assert "division by zero" in result["error"]

    def test_unknown_name_error(self):
        import minimal_memory_chat as mmc
        result = mmc.run_python("this_does_not_exist")
        assert result["ok"] is False
        assert "not defined" in result["error"]

    def test_builtin_helpers_are_callable(self):
        import minimal_memory_chat as mmc
        result = mmc.run_python(
            "all(callable(f) for f in [append_message, append_item, read_index_entries, recent_entries, s2_search_papers, http_get])"
        )
        assert result["ok"] is True
        assert result["result"] is True

    def test_index_path_and_env_path_accessible(self):
        import minimal_memory_chat as mmc
        result = mmc.run_python("isinstance(INDEX_PATH, str) and isinstance(ENV_PATH, str)")
        assert result["ok"] is True
        assert result["result"] is True

    def test_append_message_writes_to_index(self):
        import minimal_memory_chat as mmc
        result = mmc.run_python("append_message('user', 'integration test')")
        assert result["ok"] is True
        index = self._paths["index"]
        lines = [l for l in index.read_text().splitlines() if l.strip()]
        assert len(lines) == 1
        obj = json.loads(lines[0])
        assert obj["role"] == "user"
        assert obj["content"] == "integration test"

    def test_recent_entries_returns_written_messages(self):
        import minimal_memory_chat as mmc
        mmc.run_python("append_message('user', 'first message')")
        mmc.run_python("append_message('assistant', 'second message')")
        result = mmc.run_python("recent_entries(limit=5)")
        assert result["ok"] is True
        entries = result["result"]
        assert isinstance(entries, list)
        assert len(entries) == 2
        assert entries[0]["content"] == "first message"
        assert entries[1]["content"] == "second message"

    def test_instructions_md_protected_from_overwrite(self):
        import minimal_memory_chat as mmc
        instructions = self._paths["instructions"]
        original_text = instructions.read_text()

        # Inject the path so the executed code can reference it
        mmc.PYTHON_GLOBAL_SCOPE["_ipath"] = str(instructions)
        result = mmc.run_python('open(_ipath, "w").write("HACKED")')

        assert result["ok"] is False
        assert "instructions.md" in result["error"]
        # File must be restored to original content
        assert instructions.read_text() == original_text

    def test_instructions_md_protected_from_deletion(self):
        import minimal_memory_chat as mmc
        instructions = self._paths["instructions"]
        original_text = instructions.read_text()

        mmc.PYTHON_GLOBAL_SCOPE["_ipath"] = str(instructions)
        result = mmc.run_python("os.remove(_ipath)")

        assert result["ok"] is False
        assert "instructions.md" in result["error"]
        # File must be recreated
        assert instructions.exists()
        assert instructions.read_text() == original_text

    def test_state_persists_across_calls(self):
        """Variables set in one run_python call are visible in the next."""
        import minimal_memory_chat as mmc
        mmc.run_python("my_counter = 42")
        result = mmc.run_python("my_counter + 1")
        assert result["ok"] is True
        assert result["result"] == 43

    def test_context_manager_tools_available_when_installed(self):
        import minimal_memory_chat as mmc
        # These are imported with a try/except in run_python; they should be
        # available (even if None when the package isn't importable).
        result = mmc.run_python("'ContextPaths' in dir()")
        # ContextPaths is injected into scope even if it's None
        result2 = mmc.run_python("'ContextPaths' in globals()")
        assert result2["ok"] is True
        assert result2["result"] is True
