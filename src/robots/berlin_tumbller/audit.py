"""Append-only JSONL audit log for paid task executions.

One line per completed execute_task call. Default path is in /tmp; in Fly
deployment, set BERLIN_TUMBLLER_AUDIT_PATH to a location on the attached
volume so entries survive restarts.
"""

import json
import os
import time
from pathlib import Path

DEFAULT_PATH = Path("/tmp/berlin_tumbller_audit.jsonl")


def _path() -> Path:
    override = os.getenv("BERLIN_TUMBLLER_AUDIT_PATH")
    return Path(override) if override else DEFAULT_PATH


def append(entry: dict, path: Path | None = None) -> None:
    """Append `entry` as one JSON line, stamped with ts if not already set."""
    target = path if path is not None else _path()
    target.parent.mkdir(parents=True, exist_ok=True)
    stamped = {"ts": time.time(), **entry}
    with target.open("a") as f:
        f.write(json.dumps(stamped) + "\n")
