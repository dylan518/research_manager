from __future__ import annotations

import os


def get_env(name: str, default: str | None = None) -> str | None:
    return os.getenv(name, default)


def get_rm_env() -> str:
    value = (get_env("RM_ENV", "dev") or "dev").strip().lower()
    if value not in {"dev", "prod"}:
        raise ValueError("RM_ENV must be one of: dev, prod")
    return value
