#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Tuple


def _parse_ts(ts: str) -> datetime:
    if ts.endswith('Z'):
        ts = ts[:-1] + '+00:00'
    return datetime.fromisoformat(ts)


def load_events(path: Path) -> List[Dict[str, Any]]:
    events: List[Dict[str, Any]] = []
    for line in path.read_text(encoding='utf-8').splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            events.append(json.loads(line))
        except Exception:
            continue
    return events


def summarize(events: List[Dict[str, Any]]) -> Dict[str, Any]:
    if not events:
        return {"ok": True, "empty": True}

    tss = [_parse_ts(e['ts']) for e in events if isinstance(e.get('ts'), str)]
    turn_ids = [e.get('turn_id') for e in events if isinstance(e.get('turn_id'), int)]

    tool_stats = defaultdict(lambda: {"count": 0, "ok": 0, "error": 0, "timeout": 0, "total_duration_ms": 0})
    slow_calls: List[Tuple[int, str, str]] = []
    errors = defaultdict(int)

    for e in events:
        et = e.get('event_type')
        d = e.get('data') or {}

        if et == 'tool_call_finished':
            tool = d.get('tool_name', 'unknown')
            tool_stats[tool]['count'] += 1
            status = d.get('status', 'ok')
            if status == 'ok':
                tool_stats[tool]['ok'] += 1
            else:
                tool_stats[tool]['error'] += 1
            dur = int(d.get('duration_ms') or 0)
            tool_stats[tool]['total_duration_ms'] += dur
            slow_calls.append((dur, tool, d.get('call_id', '?')))

        elif et == 'tool_call_timeout':
            tool = d.get('tool_name', 'unknown')
            tool_stats[tool]['count'] += 1
            tool_stats[tool]['timeout'] += 1
            dur = int(d.get('duration_ms') or 0)
            tool_stats[tool]['total_duration_ms'] += dur
            slow_calls.append((dur, tool, d.get('call_id', '?')))

        elif et == 'tool_call_error':
            tool = d.get('tool_name', 'unknown')
            tool_stats[tool]['count'] += 1
            tool_stats[tool]['error'] += 1
            k = f"{tool}:{d.get('error_type','Error')}"
            errors[k] += 1

    mem = defaultdict(int)
    for e in events:
        et = e.get('event_type')
        if et in {'memory_read', 'memory_write', 'memory_snapshot_created', 'summary_generated'}:
            mem[et] += 1

    return {
        "ok": True,
        "start_ts": min(tss).isoformat() if tss else None,
        "end_ts": max(tss).isoformat() if tss else None,
        "turns": {"count": len(set(turn_ids)) if turn_ids else 0, "min": min(turn_ids) if turn_ids else None, "max": max(turn_ids) if turn_ids else None},
        "tools": dict(tool_stats),
        "slowest_calls": [
            {"duration_ms": dur, "tool_name": tool, "call_id": call_id}
            for dur, tool, call_id in sorted(slow_calls, reverse=True)[:5]
        ],
        "errors": dict(sorted(errors.items(), key=lambda kv: kv[1], reverse=True)),
        "memory_events": dict(mem),
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument('trace', type=str)
    ap.add_argument('--json', dest='as_json', action='store_true')
    args = ap.parse_args()

    path = Path(args.trace)
    events = load_events(path)
    s = summarize(events)

    if args.as_json:
        print(json.dumps(s, indent=2))
        return

    if s.get('empty'):
        print('empty trace')
        return

    print(f"Trace: {path}")
    print(f"Start: {s.get('start_ts')}")
    print(f"End:   {s.get('end_ts')}")
    print(f"Turns: {s.get('turns')}")

    print("
Tools:")
    for tool, st in sorted((s.get('tools') or {}).items()):
        print(f"- {tool}: calls={st['count']} ok={st['ok']} error={st['error']} timeout={st['timeout']} total_ms={st['total_duration_ms']}")

    print("
Slowest calls:")
    for c in s.get('slowest_calls', []):
        print(f"- {c['tool_name']} {c['call_id']}: {c['duration_ms']}ms")

    if s.get('errors'):
        print("
Errors:")
        for k, v in s['errors'].items():
            print(f"- {k}: {v}")

    if s.get('memory_events'):
        print("
Memory events:")
        for k, v in s['memory_events'].items():
            print(f"- {k}: {v}")


if __name__ == '__main__':
    main()
