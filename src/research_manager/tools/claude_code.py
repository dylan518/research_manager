from __future__ import annotations

import os
import shutil
import subprocess
import threading
import time
from typing import Any, Dict, List, Optional


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
    timeout_s: int = 1800,
) -> Dict[str, Any]:
    """Run Claude Code CLI non-interactively.

    By default, uses -p/--print and passes the prompt via stdin for reliability.
    If pass_prompt_as_arg=True, also appends the prompt as the final CLI argument.
    Use add_dirs to grant Claude tool access to directories.
    """
    if bin_name is None:
        bin_name = default_claude_bin()

    cmd: List[str] = [bin_name]

    if print_mode:
        cmd.append('-p')

    if add_dirs:
        for d in add_dirs:
            cmd += ['--add-dir', d]

    if extra_args:
        cmd += list(extra_args)

    if pass_prompt_as_arg:
        cmd.append(prompt)

    p = subprocess.run(
        cmd,
        input=prompt if print_mode else None,
        text=True,
        capture_output=True,
        cwd=cwd,
        timeout=timeout_s,
    )

    return {
        "ok": p.returncode == 0,
        "returncode": p.returncode,
        "stdout": p.stdout,
        "stderr": p.stderr,
        "cmd": cmd,
        "cwd": cwd,
    }


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
        ensure_dir(lp.parent)
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

    def _reader(stream, sink, label):
        for line in iter(stream.readline, ''):
            sink.append(line)
            out = f"[{label}] {line.rstrip()}"
            print(out)
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
