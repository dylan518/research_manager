from __future__ import annotations

import hashlib
import json
import os
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

from research_manager.config import get_rm_env
from research_manager.tools.fs_utils import repo_base


REDACT_KEYS_SUBSTR = ("KEY", "TOKEN", "SECRET")


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _sha256_text(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8", errors="ignore")).hexdigest()


def _preview(s: str, n: int = 400) -> str:
    s = s or ""
    
    return s[:n]


def _redact_env_like(text: str) -> str:
    if not text:
        return text
    # simple redaction: avoid leaking known env var values
    for k, v in os.environ.items():
        if not v:
            continue
        upper = k.upper()
        if k == "S2_KEY" or any(sub in upper for sub in REDACT_KEYS_SUBSTR):
            if v in text:
                text = text.replace(v, "[REDACTED]")
    return text


@dataclass
class TraceLogger:
    session_id: str
    path: Path
    env: str = "dev"
    _lock: threading.Lock = threading.Lock()

    def emit(
        self,
        *,
        turn_id: int,
        event_type: str,
        severity: str = "INFO",
        message: str = "",
        data: Optional[Dict[str, Any]] = None,
    ) -> None:
        if self.env != "dev":
            return
        if data is None:
            data = {}
        rec = {
            "ts": _utc_now_iso(),
            "session_id": self.session_id,
            "turn_id": turn_id,
            "event_type": event_type,
            "severity": severity,
            "message": message,
            "data": data,
        }
        line = json.dumps(rec, ensure_ascii=True)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._lock:
            with self.path.open("a", encoding="utf-8") as f:
                f.write(line + "\n")


def default_session_id() -> str:
    return f"sess_{int(time.time())}_{os.getpid()}"


def default_trace_path(session_id: str) -> Path:
    base = repo_base()
    return base / "state" / "dev" / "traces" / f"{session_id}.jsonl"


def get_trace_logger(session_id: Optional[str] = None) -> TraceLogger:
    env = get_rm_env()
    if session_id is None:
        session_id = os.getenv("RM_SESSION_ID") or default_session_id()
    path = default_trace_path(session_id)
    return TraceLogger(session_id=session_id, path=path, env=env)


def digest_payload(text: str) -> Dict[str, Any]:
    text = text or ""
    text = _redact_env_like(text)
    return {
        "len": len(text),
        "sha256": _sha256_text(text),
        "preview": _preview(text),
    }
