"""
core/checkpoint.py

Handles saving and reading "checkpoints" -- a bookmark of how far each
connector has successfully synced up to.

Why this exists:
Without checkpoints, every connector run would have to re-fetch ALL data
from the beginning of time, every single time. That's slow, wasteful, and
does not scale to the "100,000+ documents" target mentioned in the Atlas
Business Proposal. Checkpointing lets each connector only fetch what's NEW
since its last successful run.

Storage choice: local JSON file, one entry per connector.
Why JSON file (not a database) for now:
- Simple, zero extra setup, works immediately for development and the
  Thursday deadline.
- Isolated behind this one file -- if we later need to switch to
  PostgreSQL (which Atlas already uses, per the Business Proposal's tech
  stack) or Redis, ONLY this file changes. No connector code changes,
  because connectors only ever call get_checkpoint()/set_checkpoint()
  from base_connector.py, never touch storage directly.
"""

import json
import logging
from pathlib import Path
from threading import Lock

logger = logging.getLogger("atlas_connectors.checkpoint")

# All checkpoints are stored in one small JSON file, shaped like:
# { "pubmed": "2026-09-17T15:00:00", "nih": "2026-09-16T10:00:00" }
CHECKPOINT_FILE = Path("config/checkpoints.json")

# Prevents two connectors writing to the file at the exact same moment
# from corrupting it (basic thread-safety for local file access).
_lock = Lock()


def _read_all() -> dict[str, str]:
    if not CHECKPOINT_FILE.exists():
        return {}
    try:
        with open(CHECKPOINT_FILE, "r") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        logger.error(f"Failed to read checkpoint file, treating as empty: {e}")
        return {}


def _write_all(data: dict[str, str]) -> None:
    CHECKPOINT_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(CHECKPOINT_FILE, "w") as f:
        json.dump(data, f, indent=2)


def get_checkpoint(source_name: str) -> str | None:
    """
    Read the last saved checkpoint for a given connector (e.g. "pubmed").
    Returns None if no checkpoint exists yet (meaning: this is the first
    run, do a full sync).
    """
    with _lock:
        data = _read_all()
        value = data.get(source_name)
        logger.info(f"Checkpoint read for '{source_name}': {value}")
        return value


def set_checkpoint(source_name: str, marker: str) -> None:
    """
    Save a new checkpoint for a given connector after a successful run.
    """
    with _lock:
        data = _read_all()
        data[source_name] = marker
        _write_all(data)
        logger.info(f"Checkpoint saved for '{source_name}': {marker}")
