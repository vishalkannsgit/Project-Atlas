"""
manifest.py
===========
SQLite-backed download manifest for the Bulk Download service.

Stores the complete record of every download attempt so the team can:
  - Query which documents have been acquired.
  - Track failures for triage.
  - Detect duplicate hashes across runs.
  - Export a JSON file for downstream Atlas components.

Schema (downloads table)
------------------------
  id             INTEGER PK
  source         TEXT          (who / cdc / nih / …)
  description    TEXT
  original_url   TEXT
  final_url      TEXT
  filename       TEXT
  filepath       TEXT
  document_type  TEXT
  file_size      INTEGER       (bytes, NULL if download failed)
  sha256         TEXT          (unique across successes)
  http_status    INTEGER
  content_type   TEXT
  status         TEXT          (DownloadStatus enum value)
  error_msg      TEXT
  attempts       INTEGER
  downloaded_at  TEXT          (ISO-8601 UTC)
"""
from __future__ import annotations

import json
import logging
import sqlite3
from pathlib import Path
from typing import Optional

from .config import BulkDownloadConfig, settings as _default_settings
from .models import DownloadResult, DownloadStatus

logger = logging.getLogger(__name__)

_CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS downloads (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    source        TEXT    NOT NULL,
    description   TEXT    DEFAULT '',
    original_url  TEXT    NOT NULL,
    final_url     TEXT    DEFAULT '',
    filename      TEXT,
    filepath      TEXT,
    document_type TEXT    DEFAULT '',
    file_size     INTEGER,
    sha256        TEXT    UNIQUE,
    http_status   INTEGER,
    content_type  TEXT,
    status        TEXT    NOT NULL,
    error_msg     TEXT,
    attempts      INTEGER DEFAULT 1,
    downloaded_at TEXT    NOT NULL
);
"""

# sha256 uniqueness is now an inline column constraint (required for upsert)
_CREATE_IDX_SHA256 = ""  # kept for compatibility — column UNIQUE handles it

_CREATE_IDX_URL = """
CREATE INDEX IF NOT EXISTS idx_url ON downloads (original_url);
"""

_INSERT = """
INSERT INTO downloads (
    source, description, original_url, final_url,
    filename, filepath, document_type,
    file_size, sha256, http_status, content_type,
    status, error_msg, attempts, downloaded_at
)
VALUES (
    :source, :description, :original_url, :final_url,
    :filename, :filepath, :document_type,
    :file_size, :sha256, :http_status, :content_type,
    :status, :error_msg, :attempts, :downloaded_at
)
ON CONFLICT(sha256) DO UPDATE SET
    status        = excluded.status,
    downloaded_at = excluded.downloaded_at;
"""


class Manifest:
    """
    Thread-unsafe (use within a single async event loop / single thread).
    All writes are committed immediately (autocommit per operation).
    """

    def __init__(self, cfg: BulkDownloadConfig = _default_settings) -> None:
        self._db_path = cfg.manifest_db_path
        self._json_path = cfg.manifest_json_path
        self._conn: Optional[sqlite3.Connection] = None

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    def open(self) -> "Manifest":
        """Open (or create) the SQLite database and ensure the schema exists."""
        self._conn = sqlite3.connect(str(self._db_path))
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL;")
        self._conn.execute("PRAGMA foreign_keys=ON;")
        self._conn.execute(_CREATE_TABLE)
        if _CREATE_IDX_SHA256:
            self._conn.execute(_CREATE_IDX_SHA256)
        self._conn.execute(_CREATE_IDX_URL)
        self._conn.commit()
        logger.debug("Manifest DB opened: %s", self._db_path)
        return self

    def close(self) -> None:
        if self._conn:
            self._conn.close()
            self._conn = None

    def __enter__(self) -> "Manifest":
        return self.open()

    def __exit__(self, *_) -> None:
        self.close()

    # ── Write ─────────────────────────────────────────────────────────────────

    def record(self, result: DownloadResult) -> None:
        """
        Insert or update a DownloadResult in the manifest.
        Duplicate hashes are silently merged (ON CONFLICT … DO UPDATE).
        """
        self._require_open()
        d = result.to_dict()
        self._conn.execute(_INSERT, d)  # type: ignore[union-attr]
        self._conn.commit()             # type: ignore[union-attr]
        logger.debug("Recorded %s → %s", result.job.url, result.status.value)

    # ── Read / query ──────────────────────────────────────────────────────────

    def has_sha256(self, sha256: str) -> bool:
        """Return True if this hash is already recorded as a SUCCESS."""
        self._require_open()
        row = self._conn.execute(  # type: ignore[union-attr]
            "SELECT 1 FROM downloads WHERE sha256 = ? AND status = ?",
            (sha256, DownloadStatus.SUCCESS.value),
        ).fetchone()
        return row is not None

    def has_url(self, url: str) -> bool:
        """Return True if this URL was ever successfully downloaded."""
        self._require_open()
        row = self._conn.execute(  # type: ignore[union-attr]
            "SELECT 1 FROM downloads WHERE original_url = ? AND status = ?",
            (url, DownloadStatus.SUCCESS.value),
        ).fetchone()
        return row is not None

    def summary(self) -> dict[str, int]:
        """Return counts grouped by status."""
        self._require_open()
        rows = self._conn.execute(  # type: ignore[union-attr]
            "SELECT status, COUNT(*) AS cnt FROM downloads GROUP BY status"
        ).fetchall()
        return {row["status"]: row["cnt"] for row in rows}

    def all_records(self) -> list[dict]:
        """Return all rows as plain dicts."""
        self._require_open()
        rows = self._conn.execute(  # type: ignore[union-attr]
            "SELECT * FROM downloads ORDER BY downloaded_at DESC"
        ).fetchall()
        return [dict(r) for r in rows]

    # ── Export ────────────────────────────────────────────────────────────────

    def export_json(self, path: Optional[Path] = None) -> Path:
        """
        Write all manifest records to a JSON file.

        Args:
            path: Override the default export path from config.

        Returns:
            The Path where the JSON was written.
        """
        out = path or self._json_path
        records = self.all_records()
        out.write_text(
            json.dumps(records, indent=2, default=str),
            encoding="utf-8",
        )
        logger.info("Manifest exported to %s (%d records)", out, len(records))
        return out

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _require_open(self) -> None:
        if self._conn is None:
            raise RuntimeError(
                "Manifest is not open. Use `with Manifest() as m:` or call .open() first."
            )
