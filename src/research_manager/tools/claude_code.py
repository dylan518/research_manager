from __future__ import annotations

import os
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from research_manager.tools.fs_utils import repo_base
from research_manager.tools.trace_logger import get_trace_logger, digest_payload


def _candidate_paths() -> List[str]:
    home = os.path.expanduser('~')
    return [
        os.path.join(home, '.local', 'bin', 'claude'),
        os.path.join(home, '.claude', 'bin', 'claude'),
    ]


def which_claude() -> Dict[str, Optional[str]]:
    """Return discovered CLI paths for common Claude Code binary names."""
    names = ["claude", "claude-code", "anthropic"]
    found: Dict[str, Optional[str]] = {name: shutil.which(name) for name in names}

    # Also check common install locations if not on PATH.
    for p in _candidate_paths():
        if os.path.exists(p):
            found.setdefault("claude_local", p)
            found["claude_local"] = p
            break
    else:
        found.setdefault("claude_local", None)

    return found


def default_claude_bin() -> str:
    found = which_claude()
    return found.get('claude') or found.get('claude-code') or found.get('anthropic') or found.get('claude_local') or 'claude'


def run_claude(
    prompt: str,
    *,
    cwd: Optional[str] = None,
    bin_name: Optional[str] = None,
    extra_args: Optional[List[str]] = None,
    add_dirs: Optional[List[str]] = None,
    print_mode: bool = True,
    pass_prompt_as_arg: bool = False,
    dangerously_skip_permissions: bool = False,
    continue_session: bool = False,
    resume_session: Optional[str] = None,
    timeout_s: int = 1800,
) -> Dict[str, Any]:
    """Run Claude Code CLI non-interactively.

    By default, uses -p/--print and passes the prompt via stdin for reliability.
    Set dangerously_skip_permissions=True to let Claude write/edit files without
    approval prompts — required for Claude to actually execute tasks rather than
    just describe them.

    Session continuity:
      continue_session=True  — resumes the most recent session in cwd (-c flag).
                               Use this to give Claude memory of previous calls.
      resume_session="<id>"  — resumes a specific session by ID (-r flag).
                               The session ID is returned in result["session_id"]
                               when output_format="json" is passed via extra_args.

    Use add_dirs to grant Claude tool access to directories.
    """
    if cwd is None:
        cwd = str(repo_base())
    if bin_name is None:
        bin_name = default_claude_bin()

    cmd: List[str] = [bin_name]

    if print_mode:
        cmd.append('-p')

    if dangerously_skip_permissions:
        cmd.append('--dangerously-skip-permissions')

    if continue_session:
        cmd.append('--continue')

    if resume_session:
        cmd += ['--resume', resume_session]

    if add_dirs:
        for d in add_dirs:
            cmd += ['--add-dir', d]

    if extra_args:
        cmd += list(extra_args)

    if pass_prompt_as_arg:
        cmd.append(prompt)

    trace = get_trace_logger()
    turn_id = int(os.getenv("RM_TURN_ID", "0"))
    call_id = f"claude_code:{int(time.time()*1000)}"
    args_d = digest_payload(prompt)

    trace.emit(
        turn_id=turn_id,
        event_type="tool_call_started",
        message="claude_code.run_claude started",
        data={
            "tool_name": "claude_code",
            "call_id": call_id,
            "timeout_s": timeout_s,
            "cmd": cmd,
            "cwd": cwd,
            "args_len": args_d["len"],
            "args_sha256": args_d["sha256"],
            "args_preview": args_d["preview"],
        },
    )

    # Always write to the real terminal, bypassing any stdout redirect active
    # in the calling context (e.g. run_python uses contextlib.redirect_stdout).
    _tty = sys.__stdout__

    t0 = time.time()
    stdout_chunks: List[str] = []
    stderr_chunks: List[str] = []

    print(f"\n{'─' * 60}", file=_tty, flush=True)
    print(f"[claude-code] starting  call_id={call_id}", file=_tty, flush=True)
    print(f"{'─' * 60}", file=_tty, flush=True)

    try:
        p = subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            cwd=cwd,
        )

        def _read(stream, sink: List[str], label: str) -> None:
            for line in iter(stream.readline, ""):
                sink.append(line)
                print(f"{label}{line}", end="", file=_tty, flush=True)
            stream.close()

        t_out = threading.Thread(target=_read, args=(p.stdout, stdout_chunks, ""), daemon=True)
        t_err = threading.Thread(target=_read, args=(p.stderr, stderr_chunks, "[stderr] "), daemon=True)
        t_out.start()
        t_err.start()

        if print_mode and p.stdin:
            p.stdin.write(prompt)
            if not prompt.endswith("\n"):
                p.stdin.write("\n")
            p.stdin.close()

        try:
            rc = p.wait(timeout=timeout_s)
        except subprocess.TimeoutExpired:
            p.kill()
            t_out.join(timeout=1)
            t_err.join(timeout=1)
            dt_ms = int((time.time() - t0) * 1000)
            print(f"\n{'─' * 60}", file=_tty, flush=True)
            print(f"[claude-code] TIMEOUT after {timeout_s}s", file=_tty, flush=True)
            print(f"{'─' * 60}\n", file=_tty, flush=True)
            trace.emit(
                turn_id=turn_id,
                event_type="tool_call_timeout",
                severity="WARN",
                message="claude_code.run_claude timeout",
                data={"tool_name": "claude_code", "call_id": call_id, "timeout_s": timeout_s, "duration_ms": dt_ms},
            )
            raise

        t_out.join(timeout=2)
        t_err.join(timeout=2)

        stdout_str = "".join(stdout_chunks)
        stderr_str = "".join(stderr_chunks)
        dt_ms = int((time.time() - t0) * 1000)

        print(f"{'─' * 60}", file=_tty, flush=True)
        print(f"[claude-code] done  exit={rc}  {dt_ms}ms", file=_tty, flush=True)
        print(f"{'─' * 60}\n", file=_tty, flush=True)

        out_d = digest_payload(stdout_str)
        err_d = digest_payload(stderr_str)
        trace.emit(
            turn_id=turn_id,
            event_type="tool_call_finished",
            message="claude_code.run_claude finished",
            data={
                "tool_name": "claude_code",
                "call_id": call_id,
                "status": "ok" if rc == 0 else "error",
                "duration_ms": dt_ms,
                "returncode": rc,
                "stdout_len": out_d["len"],
                "stdout_sha256": out_d["sha256"],
                "stdout_preview": out_d["preview"],
                "stderr_len": err_d["len"],
                "stderr_sha256": err_d["sha256"],
                "stderr_preview": err_d["preview"],
            },
        )
        return {
            "ok": rc == 0,
            "returncode": rc,
            "stdout": stdout_str,
            "stderr": stderr_str,
            "cmd": cmd,
            "cwd": cwd,
        }
    except subprocess.TimeoutExpired:
        raise
    except Exception as e:
        dt_ms = int((time.time() - t0) * 1000)
        print(f"\n{'─' * 60}", file=_tty, flush=True)
        print(f"[claude-code] ERROR  {type(e).__name__}: {e}", file=_tty, flush=True)
        print(f"{'─' * 60}\n", file=_tty, flush=True)
        trace.emit(
            turn_id=turn_id,
            event_type="tool_call_error",
            severity="ERROR",
            message="claude_code.run_claude error",
            data={"tool_name": "claude_code", "call_id": call_id, "duration_ms": dt_ms, "error_type": type(e).__name__, "error": str(e)},
        )
        raise


def run_claude_stream(
    prompt: str,
    *,
    cwd: Optional[str] = None,
    bin_name: Optional[str] = None,
    extra_args: Optional[List[str]] = None,
    timeout_s: int = 180,
    add_dirs: Optional[List[str]] = None,
    dangerously_skip_permissions: bool = False,
    pass_prompt_as_arg: bool = False,
    log_path: Optional[str] = None,
) -> Dict[str, Any]:
    """Run Claude Code CLI and stream stdout/stderr.

    - Uses stdin by default for prompt.
    - Returns a dict with stdout/stderr captured as well.

    Note: requires a TTY-less compatible mode; uses -p/--print.
    """
    import subprocess
    import threading

    if cwd is None:
        cwd = str(repo_base())
    bin_path = bin_name or default_claude_bin()
    if not bin_path:
        raise FileNotFoundError("Claude CLI not found. Install and/or ensure it is on PATH or in ~/.local/bin/claude")

    cmd: List[str] = [bin_path, "-p"]

    if dangerously_skip_permissions:
        cmd.append("--dangerously-skip-permissions")

    if add_dirs:
        for d in add_dirs:
            cmd += ["--add-dir", d]

    if extra_args:
        cmd += extra_args

    if pass_prompt_as_arg:
        cmd.append(prompt)

    # ensure logging dir
    if log_path:
        lp = Path(log_path)
        lp.parent.mkdir(parents=True, exist_ok=True)
        log_f = lp.open('w', encoding='utf-8')
    else:
        log_f = None

    stdout_lines: List[str] = []
    stderr_lines: List[str] = []

    p = subprocess.Popen(
        cmd,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        cwd=cwd,
        bufsize=1,
    )

    start = time.time()

    _tty = sys.__stdout__

    def _reader(stream, sink, label):
        for line in iter(stream.readline, ''):
            sink.append(line)
            out = f"[{label}] {line.rstrip()}"
            print(out, file=_tty, flush=True)
            if log_f:
                log_f.write(out + "\n")
                log_f.flush()
        stream.close()

    t_out = threading.Thread(target=_reader, args=(p.stdout, stdout_lines, 'stdout'), daemon=True)
    t_err = threading.Thread(target=_reader, args=(p.stderr, stderr_lines, 'stderr'), daemon=True)
    t_out.start(); t_err.start()

    try:
        if p.stdin:
            p.stdin.write(prompt)
            if not prompt.endswith("\n"):
                p.stdin.write("\n")
            p.stdin.close()

        while True:
            rc = p.poll()
            if rc is not None:
                break
            if time.time() - start > timeout_s:
                p.kill()
                raise TimeoutError(f"Claude CLI timed out after {timeout_s}s")
            time.sleep(0.1)

        t_out.join(timeout=1)
        t_err.join(timeout=1)

        result = {
            "ok": rc == 0,
            "returncode": rc,
            "stdout": "".join(stdout_lines),
            "stderr": "".join(stderr_lines),
            "cmd": cmd,
            "cwd": cwd,
        }
        return result
    finally:
        if log_f:
            log_f.close()
