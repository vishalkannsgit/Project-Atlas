"""
core/health.py

Answers one question for each connector: "Are you currently healthy?"

Why this exists:
Without a health check, a connector could silently break (bad API key
expired, source website changed its format, network blocked) and nobody
would notice until someone realizes data stopped updating -- possibly days
later. This file gives a quick, reliable status check that a monitoring
dashboard (Epic 6, someone else's part) can call anytime.

How "health" is decided (kept simple on purpose):
- OK: last run succeeded, and it succeeded "recently enough"
  (within STALE_AFTER_HOURS).
- DEGRADED: last run had some errors, but still sent SOME data
  successfully (a "partial" run).
- DOWN: last run failed completely, OR it's been too long since any
  successful run (even if there's no recent error -- e.g. connector
  hasn't run at all in days, which is itself suspicious).
"""

import json
import logging
from datetime import datetime, timedelta
from pathlib import Path

from core.models import ConnectorHealth, HealthStatus, SourceType

logger = logging.getLogger("atlas_connectors.health")

# If a connector hasn't succeeded within this many hours, we consider it
# DOWN even if there's no explicit error -- e.g. a scheduled job silently
# stopped running.
STALE_AFTER_HOURS = 26  # a bit more than 24h, to allow for a daily schedule

# Stores the last run result for each connector, one small JSON file.
# Shape: { "pubmed": {"status": "success", "last_success_at": "...", "last_error": null} }
HEALTH_FILE = Path("config/health.json")


def _read_all() -> dict:
    if not HEALTH_FILE.exists():
        return {}
    try:
        with open(HEALTH_FILE, "r") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        logger.error(f"Failed to read health file, treating as empty: {e}")
        return {}


def _write_all(data: dict) -> None:
    HEALTH_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(HEALTH_FILE, "w") as f:
        json.dump(data, f, indent=2, default=str)


def record_run_outcome(source_name: str, status: str, error_message: str | None = None) -> None:
    """
    Called at the end of every connector run (from base_connector.py's
    run() method) to save what happened, so health_check() has something
    to report later.
    """
    data = _read_all()
    entry = data.get(source_name, {})

    now_iso = datetime.utcnow().isoformat()
    entry["last_run_status"] = status
    entry["last_run_at"] = now_iso
    if status == "success":
        entry["last_success_at"] = now_iso
        entry["last_error"] = None
    else:
        entry["last_error"] = error_message

    data[source_name] = entry
    _write_all(data)
    logger.info(f"Health recorded for '{source_name}': status={status}")


def check_health(source_name: str) -> ConnectorHealth:
    """
    Returns the current health status for a given connector.
    This is the function a monitoring dashboard or a manual check would call.
    """
    data = _read_all()
    entry = data.get(source_name)

    if not entry:
        # Connector has literally never run yet.
        return ConnectorHealth(
            source=SourceType(source_name),
            status=HealthStatus.DOWN,
            last_success_at=None,
            last_error="No run has ever been recorded for this connector.",
        )

    last_success_str = entry.get("last_success_at")
    last_success_at = datetime.fromisoformat(last_success_str) if last_success_str else None
    last_run_status = entry.get("last_run_status")
    last_error = entry.get("last_error")

    is_stale = (
        last_success_at is None
        or (datetime.utcnow() - last_success_at) > timedelta(hours=STALE_AFTER_HOURS)
    )

    if last_run_status == "failed" or is_stale:
        status = HealthStatus.DOWN
    elif last_run_status == "partial":
        status = HealthStatus.DEGRADED
    else:
        status = HealthStatus.OK

    return ConnectorHealth(
        source=SourceType(source_name),
        status=status,
        last_success_at=last_success_at,
        last_error=last_error,
    )
