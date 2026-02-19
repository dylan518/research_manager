"""Runtime environment configuration for research_manager."""

from __future__ import annotations

import os


def get_rm_env() -> str:
    """Return the current runtime environment.

    Reads the RM_ENV environment variable. Defaults to "dev" so that
    trace logging is active unless explicitly set to another value (e.g. "prod").
    """
    return os.getenv("RM_ENV", "dev")
