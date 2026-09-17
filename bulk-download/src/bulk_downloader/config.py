"""
config.py
=========
Central configuration for the Bulk Download service.

All paths are resolved relative to the Atlas monorepo root so the
service works regardless of where the Python process is invoked from.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


def _repo_root() -> Path:
    """Walk up from this file until we find the .git directory."""
    here = Path(__file__).resolve()
    for parent in here.parents:
        if (parent / ".git").exists():
            return parent
    # Fallback: treat project root as 3 levels up from this file
    # bulk-download/src/bulk_downloader/config.py → bulk-download/../..
    return here.parents[3]


@dataclass
class BulkDownloadConfig:
    """
    All tunable knobs for the bulk downloader.
    Override any field via environment variable or direct construction.
    """

    # ── Paths ────────────────────────────────────────────────────────────────
    repo_root: Path = field(default_factory=_repo_root)

    @property
    def data_raw_dir(self) -> Path:
        """Where downloaded source files are saved: data/raw/<source>/…"""
        p = self.repo_root / "data" / "raw"
        p.mkdir(parents=True, exist_ok=True)
        return p

    @property
    def data_staging_dir(self) -> Path:
        """Where the manifest and handoff artifacts land: data/staging/acquisition/"""
        p = self.repo_root / "data" / "staging" / "acquisition"
        p.mkdir(parents=True, exist_ok=True)
        return p

    @property
    def manifest_db_path(self) -> Path:
        return self.data_staging_dir / "manifest.db"

    @property
    def manifest_json_path(self) -> Path:
        return self.data_staging_dir / "manifest_export.json"

    @property
    def data_sources_dir(self) -> Path:
        """data_sources/ folder inside bulk-download/"""
        return self.repo_root / "bulk-download" / "data_sources"

    # ── Concurrency ──────────────────────────────────────────────────────────
    max_workers: int = field(
        default_factory=lambda: int(os.getenv("ATLAS_BD_WORKERS", "5"))
    )
    """Maximum simultaneous HTTP downloads."""

    # ── Retry / backoff ──────────────────────────────────────────────────────
    max_retries: int = field(
        default_factory=lambda: int(os.getenv("ATLAS_BD_MAX_RETRIES", "4"))
    )
    """Total retry attempts after the first failure (so 4 → up to 5 total attempts)."""

    backoff_base: float = field(
        default_factory=lambda: float(os.getenv("ATLAS_BD_BACKOFF_BASE", "2.0"))
    )
    """Base seconds for exponential backoff: wait = backoff_base ** attempt."""

    # ── Timeouts ─────────────────────────────────────────────────────────────
    connect_timeout: float = 10.0   # seconds to establish connection
    read_timeout: float = 60.0      # seconds to read the full response

    # ── File size limits ─────────────────────────────────────────────────────
    max_file_size_mb: int = field(
        default_factory=lambda: int(os.getenv("ATLAS_BD_MAX_FILE_MB", "100"))
    )

    @property
    def max_file_size_bytes(self) -> int:
        return self.max_file_size_mb * 1024 * 1024

    min_file_size_bytes: int = 512  # Reject obviously empty / error-page responses

    # ── HTTP behaviour ───────────────────────────────────────────────────────
    user_agent: str = (
        "Mozilla/5.0 (compatible; ProjectAtlas/0.1; "
        "+https://github.com/vishalkannsgit/Project-Atlas)"
    )
    chunk_size: int = 8 * 1024      # 8 KB streaming chunks

    # ── Retryable HTTP status codes ──────────────────────────────────────────
    retryable_statuses: frozenset[int] = field(
        default_factory=lambda: frozenset({429, 500, 502, 503, 504})
    )
    """HTTP codes that warrant a retry with backoff."""

    non_retryable_statuses: frozenset[int] = field(
        default_factory=lambda: frozenset({400, 401, 403, 404, 410})
    )
    """HTTP codes that should be immediately marked as failed, no retry."""


# Module-level singleton — import this everywhere
settings = BulkDownloadConfig()
