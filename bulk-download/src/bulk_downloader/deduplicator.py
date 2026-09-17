"""
deduplicator.py
===============
Duplicate detection for the Bulk Download service.

Two-layer strategy:
  1. In-memory set  — fast O(1) check for hashes seen in the current run.
  2. SQLite manifest — durable check for hashes from previous runs.

This prevents:
  - Downloading the same content under two different URLs.
  - Re-downloading files already acquired in a previous pipeline run.
"""
from __future__ import annotations

import logging

from .manifest import Manifest

logger = logging.getLogger(__name__)


class Deduplicator:
    """
    Stateful duplicate detector backed by the Manifest DB.

    Usage
    -----
    with Manifest() as m:
        dedup = Deduplicator(m)
        if dedup.is_duplicate(sha256):
            # skip
        else:
            dedup.register(sha256)   # mark as seen for this run
    """

    def __init__(self, manifest: Manifest) -> None:
        self._manifest = manifest
        # In-memory set tracks hashes added *during the current run*
        # so we don't hit SQLite on every check.
        self._seen_this_run: set[str] = set()

    def is_duplicate(self, sha256: str) -> bool:
        """
        Return True if this SHA-256 has already been downloaded.

        Checks in order (fastest first):
          1. Current-run in-memory set.
          2. Persistent manifest DB (previous runs).

        Args:
            sha256: Hex digest to check.

        Returns:
            True  → already seen; the caller should record DUPLICATE.
            False → new content; the caller should proceed.
        """
        # Fast path — seen in this run
        if sha256 in self._seen_this_run:
            logger.debug("Duplicate (in-run): %s", sha256[:16])
            return True

        # Slow path — check DB (previous runs)
        if self._manifest.has_sha256(sha256):
            logger.debug("Duplicate (DB): %s", sha256[:16])
            # Promote to in-memory so subsequent checks are fast
            self._seen_this_run.add(sha256)
            return True

        return False

    def register(self, sha256: str) -> None:
        """
        Mark a hash as seen for the current run.
        Call this *after* a successful download and DB record.

        Args:
            sha256: Hex digest that was just successfully stored.
        """
        self._seen_this_run.add(sha256)
        logger.debug("Registered new hash: %s", sha256[:16])

    def seen_count(self) -> int:
        """Number of unique hashes observed in the current run."""
        return len(self._seen_this_run)
