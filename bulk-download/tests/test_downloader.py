"""
test_downloader.py
==================
Tests for bulk_downloader.downloader

Strategy: mock at _try_download level with unittest.mock (version-safe).
This avoids aioresponses compatibility issues with aiohttp>=3.9 on Python 3.14+.
All tests are async and use pytest-asyncio.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import sys
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from bulk_downloader.config import BulkDownloadConfig
from bulk_downloader.downloader import (
    _build_dest_path,
    download_all,
    load_jobs_from_file,
    load_jobs_from_sources,
)
from bulk_downloader.models import DocumentType, DownloadJob, DownloadResult, DownloadStatus


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def tmp_cfg(tmp_path) -> BulkDownloadConfig:
    """Config whose data directories all live under tmp_path."""
    raw_dir = tmp_path / "data" / "raw"
    raw_dir.mkdir(parents=True)
    staging_dir = tmp_path / "data" / "staging" / "acquisition"
    staging_dir.mkdir(parents=True)
    sources_dir = tmp_path / "data_sources"
    sources_dir.mkdir(parents=True)

    cfg = BulkDownloadConfig.__new__(BulkDownloadConfig)
    # Set all fields manually so we bypass __post_init__ path resolution
    object.__setattr__(cfg, "repo_root", tmp_path)
    object.__setattr__(cfg, "max_workers", 2)
    object.__setattr__(cfg, "max_retries", 1)
    object.__setattr__(cfg, "backoff_base", 0.01)   # fast backoff in tests
    object.__setattr__(cfg, "connect_timeout", 5.0)
    object.__setattr__(cfg, "read_timeout", 10.0)
    object.__setattr__(cfg, "max_file_size_mb", 100)
    object.__setattr__(cfg, "min_file_size_bytes", 10)
    object.__setattr__(cfg, "user_agent", "TestAgent/1.0")
    object.__setattr__(cfg, "chunk_size", 8192)
    object.__setattr__(cfg, "retryable_statuses", frozenset({429, 500, 502, 503, 504}))
    object.__setattr__(cfg, "non_retryable_statuses", frozenset({400, 401, 403, 404, 410}))

    # Patch the property-based paths directly on this instance via a subclass trick
    # We override just the properties we need
    cfg._raw_dir = raw_dir
    cfg._staging_dir = staging_dir
    cfg._sources_dir = sources_dir

    # Monkey-patch properties on the instance's class
    # (we create a fresh per-test subclass so tests don't interfere)
    SubCls = type("TestCfg", (BulkDownloadConfig,), {
        "data_raw_dir":     property(lambda self: self._raw_dir),
        "data_staging_dir": property(lambda self: self._staging_dir),
        "manifest_db_path": property(lambda self: self._staging_dir / "manifest.db"),
        "manifest_json_path": property(lambda self: self._staging_dir / "manifest_export.json"),
        "data_sources_dir": property(lambda self: self._sources_dir),
    })
    cfg.__class__ = SubCls
    return cfg


@pytest.fixture
def pdf_job() -> DownloadJob:
    return DownloadJob(
        source="test",
        url="https://example.com/sample.pdf",
        document_type=DocumentType.PDF,
        allowed_domain="example.com",
        description="Test PDF",
    )


FAKE_PDF = b"%PDF-1.4\n" + b"fake pdf content " * 40


def _make_success_result(job: DownloadJob, filepath: Path) -> DownloadResult:
    sha = hashlib.sha256(FAKE_PDF).hexdigest()
    return DownloadResult(
        job=job,
        status=DownloadStatus.SUCCESS,
        filename=filepath.name,
        filepath=filepath,
        sha256=sha,
        file_size=len(FAKE_PDF),
        http_status=200,
        content_type="application/pdf",
        final_url=job.url,
        attempts=1,
        downloaded_at=datetime.now(timezone.utc),
    )


def _make_error_result(job: DownloadJob, status: DownloadStatus, http: int = None) -> DownloadResult:
    return DownloadResult(
        job=job,
        status=status,
        http_status=http,
        final_url=job.url,
        error_msg=f"Mocked {status.value}",
        attempts=1,
        downloaded_at=datetime.now(timezone.utc),
    )


# ── _build_dest_path ──────────────────────────────────────────────────────────

class TestBuildDestPath:
    def test_structure(self, pdf_job, tmp_cfg):
        sha = "a" * 64
        path = _build_dest_path(pdf_job, sha, tmp_cfg)
        assert "test" in path.parts
        # Year component
        assert any(p.isdigit() and len(p) == 4 for p in path.parts)

    def test_hash_prefix_in_filename(self, pdf_job, tmp_cfg):
        sha = "deadbeef" + "0" * 56
        path = _build_dest_path(pdf_job, sha, tmp_cfg)
        assert path.name.startswith("deadbeef")

    def test_different_hashes_give_different_paths(self, pdf_job, tmp_cfg):
        p1 = _build_dest_path(pdf_job, "a" * 64, tmp_cfg)
        p2 = _build_dest_path(pdf_job, "b" * 64, tmp_cfg)
        assert p1 != p2

    def test_sanitises_special_chars(self, tmp_cfg):
        job = DownloadJob(
            source="test",
            url="https://example.com/my file (2024).pdf",
            document_type=DocumentType.PDF,
        )
        path = _build_dest_path(job, "a" * 64, tmp_cfg)
        assert " " not in path.name
        assert "(" not in path.name


# ── load_jobs_from_file ───────────────────────────────────────────────────────

class TestLoadJobsFromFile:
    def test_loads_valid_json(self, tmp_path):
        data = [{"source": "who", "url": "https://who.int/doc.pdf", "document_type": "pdf"}]
        f = tmp_path / "sources.json"
        f.write_text(json.dumps(data))
        jobs = load_jobs_from_file(f)
        assert len(jobs) == 1
        assert jobs[0].document_type == DocumentType.PDF

    def test_raises_on_non_array(self, tmp_path):
        f = tmp_path / "bad.json"
        f.write_text(json.dumps({"url": "https://example.com"}))
        with pytest.raises(ValueError, match="JSON array"):
            load_jobs_from_file(f)

    def test_default_document_type_is_pdf(self, tmp_path):
        f = tmp_path / "s.json"
        f.write_text(json.dumps([{"source": "test", "url": "https://example.com/x"}]))
        jobs = load_jobs_from_file(f)
        assert jobs[0].document_type == DocumentType.PDF


# ── load_jobs_from_sources ────────────────────────────────────────────────────

class TestLoadJobsFromSources:
    def test_loads_multiple_sources(self, tmp_cfg):
        src = tmp_cfg.data_sources_dir
        (src / "alpha_sources.json").write_text(
            json.dumps([{"source": "alpha", "url": "https://example.com/a.pdf"}])
        )
        (src / "beta_sources.json").write_text(
            json.dumps([
                {"source": "beta", "url": "https://example.com/b.pdf"},
                {"source": "beta", "url": "https://example.com/c.pdf"},
            ])
        )
        jobs = load_jobs_from_sources(["alpha", "beta"], tmp_cfg)
        assert len(jobs) == 3

    def test_skips_missing_source(self, tmp_cfg):
        jobs = load_jobs_from_sources(["nonexistent"], tmp_cfg)
        assert jobs == []


# ── download_all integration tests (mocked at _fetch_with_retry level) ────────

@pytest.mark.asyncio
async def test_download_all_success(tmp_cfg, pdf_job, tmp_path):
    """
    Mock _fetch_with_retry to return a SUCCESS result with a real file.
    Verifies download_all records to manifest and returns correct status.
    """
    # Pre-create the file that the mock would have written
    fake_file = tmp_cfg.data_raw_dir / "test" / "2026" / "09" / "abc123_sample.pdf"
    fake_file.parent.mkdir(parents=True, exist_ok=True)
    fake_file.write_bytes(FAKE_PDF)

    mock_result = _make_success_result(pdf_job, fake_file)

    with patch(
        "bulk_downloader.downloader._fetch_with_retry",
        new=AsyncMock(return_value=mock_result),
    ):
        results = await download_all([pdf_job], tmp_cfg)

    assert len(results) == 1
    assert results[0].status == DownloadStatus.SUCCESS
    assert results[0].sha256 == hashlib.sha256(FAKE_PDF).hexdigest()
    # Manifest JSON should have been exported
    assert tmp_cfg.manifest_json_path.exists()


@pytest.mark.asyncio
async def test_download_all_http_error(tmp_cfg, pdf_job):
    """404 → HTTP_ERROR is passed through correctly."""
    mock_result = _make_error_result(pdf_job, DownloadStatus.HTTP_ERROR, http=404)

    with patch(
        "bulk_downloader.downloader._fetch_with_retry",
        new=AsyncMock(return_value=mock_result),
    ):
        results = await download_all([pdf_job], tmp_cfg)

    assert results[0].status == DownloadStatus.HTTP_ERROR
    assert results[0].http_status == 404


@pytest.mark.asyncio
async def test_download_all_invalid_file(tmp_cfg, pdf_job):
    """INVALID_FILE status propagates correctly."""
    mock_result = _make_error_result(pdf_job, DownloadStatus.INVALID_FILE)

    with patch(
        "bulk_downloader.downloader._fetch_with_retry",
        new=AsyncMock(return_value=mock_result),
    ):
        results = await download_all([pdf_job], tmp_cfg)

    assert results[0].status == DownloadStatus.INVALID_FILE


@pytest.mark.asyncio
async def test_download_all_duplicate(tmp_cfg, pdf_job, tmp_path):
    """Second call with same hash → DUPLICATE."""
    fake_file = tmp_cfg.data_raw_dir / "test" / "2026" / "09" / "abc123_sample.pdf"
    fake_file.parent.mkdir(parents=True, exist_ok=True)
    fake_file.write_bytes(FAKE_PDF)
    sha = hashlib.sha256(FAKE_PDF).hexdigest()

    success_result = _make_success_result(pdf_job, fake_file)
    dup_result = DownloadResult(
        job=pdf_job,
        status=DownloadStatus.DUPLICATE,
        sha256=sha,
        final_url=pdf_job.url,
        attempts=1,
        downloaded_at=datetime.now(timezone.utc),
    )

    # First call succeeds
    with patch(
        "bulk_downloader.downloader._fetch_with_retry",
        new=AsyncMock(return_value=success_result),
    ):
        r1 = await download_all([pdf_job], tmp_cfg)
    assert r1[0].status == DownloadStatus.SUCCESS

    # Second call is duplicate
    with patch(
        "bulk_downloader.downloader._fetch_with_retry",
        new=AsyncMock(return_value=dup_result),
    ):
        r2 = await download_all([pdf_job], tmp_cfg)
    assert r2[0].status == DownloadStatus.DUPLICATE


@pytest.mark.asyncio
async def test_download_all_multiple_jobs(tmp_cfg):
    """5 jobs all succeed; all results are returned."""
    jobs = [
        DownloadJob(
            source="test",
            url=f"https://example.com/doc{i}.pdf",
            document_type=DocumentType.PDF,
        )
        for i in range(5)
    ]

    def make_result(job, i):
        content = FAKE_PDF + f"-{i}".encode()
        sha = hashlib.sha256(content).hexdigest()
        return DownloadResult(
            job=job,
            status=DownloadStatus.SUCCESS,
            sha256=sha,
            file_size=len(content),
            http_status=200,
            final_url=job.url,
            attempts=1,
            downloaded_at=datetime.now(timezone.utc),
        )

    results_by_job = [make_result(j, i) for i, j in enumerate(jobs)]

    call_count = [0]

    async def mock_fetch(job, session, semaphore, manifest, deduplicator, cfg):
        idx = int(job.url.split("doc")[1].split(".")[0])
        return results_by_job[idx]

    with patch("bulk_downloader.downloader._download_one", new=mock_fetch):
        results = await download_all(jobs, tmp_cfg)

    assert len(results) == 5
    assert all(r.status == DownloadStatus.SUCCESS for r in results)
    hashes = [r.sha256 for r in results]
    assert len(set(hashes)) == 5  # all unique
