"""
test_deduplicator.py
====================
Tests for bulk_downloader.deduplicator
"""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from bulk_downloader.deduplicator import Deduplicator


def _mock_manifest(has_sha: bool = False) -> MagicMock:
    """Return a mock Manifest that returns `has_sha` for has_sha256 calls."""
    m = MagicMock()
    m.has_sha256.return_value = has_sha
    return m


class TestDeduplicator:
    def test_new_hash_is_not_duplicate(self):
        dedup = Deduplicator(_mock_manifest(has_sha=False))
        assert not dedup.is_duplicate("abc123")

    def test_registered_hash_is_duplicate_in_run(self):
        dedup = Deduplicator(_mock_manifest(has_sha=False))
        sha = "deadbeef" * 8
        dedup.register(sha)
        assert dedup.is_duplicate(sha)

    def test_hash_in_db_is_duplicate(self):
        """Simulate a hash that exists in the manifest DB from a previous run."""
        dedup = Deduplicator(_mock_manifest(has_sha=True))
        sha = "cafebabe" * 8
        assert dedup.is_duplicate(sha)

    def test_db_check_only_called_once_for_same_hash(self):
        """After first DB hit, subsequent checks use the in-memory cache."""
        manifest = _mock_manifest(has_sha=True)
        dedup = Deduplicator(manifest)
        sha = "11223344" * 8

        # First call hits DB
        assert dedup.is_duplicate(sha)
        # Second call should be served from in-memory cache
        assert dedup.is_duplicate(sha)

        # has_sha256 should only have been called once
        manifest.has_sha256.assert_called_once_with(sha)

    def test_different_hashes_are_independent(self):
        dedup = Deduplicator(_mock_manifest(has_sha=False))
        dedup.register("hash_a" + "0" * 58)
        assert not dedup.is_duplicate("hash_b" + "0" * 58)

    def test_seen_count_increments(self):
        dedup = Deduplicator(_mock_manifest(has_sha=False))
        assert dedup.seen_count() == 0
        dedup.register("aaa" + "0" * 61)
        dedup.register("bbb" + "0" * 61)
        assert dedup.seen_count() == 2

    def test_register_then_is_duplicate(self):
        dedup = Deduplicator(_mock_manifest(has_sha=False))
        sha = "f" * 64
        assert not dedup.is_duplicate(sha)
        dedup.register(sha)
        assert dedup.is_duplicate(sha)
        # DB should NOT have been called for the second check
        # (in-memory fast path)

    def test_multiple_different_hashes(self):
        dedup = Deduplicator(_mock_manifest(has_sha=False))
        hashes = [f"{i:064d}" for i in range(20)]
        for h in hashes:
            dedup.register(h)
        for h in hashes:
            assert dedup.is_duplicate(h)

    def test_empty_string_hash(self):
        """Edge case: empty string hash should still work."""
        dedup = Deduplicator(_mock_manifest(has_sha=False))
        dedup.register("")
        assert dedup.is_duplicate("")
