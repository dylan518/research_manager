from __future__ import annotations

import os
import shutil
import subprocess
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

    # Claude Code in --print mode is most reliable when prompt is provided via stdin.
    # Optionally also pass it as an argument for compatibility.
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
