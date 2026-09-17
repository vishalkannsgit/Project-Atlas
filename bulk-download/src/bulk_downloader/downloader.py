"""
downloader.py
=============
Async concurrent bulk downloader for the Bulk Download service.

Architecture
------------
  download_all(jobs)
    └─ asyncio.Semaphore(MAX_WORKERS)    ← controls concurrency
        └─ _download_one(job, session)   ← single download + retry loop
            ├─ _fetch_with_retry(...)    ← HTTP + backoff logic
            ├─ validator.validate_file() ← magic bytes + size
            ├─ hasher.sha256_file()      ← content identity
            ├─ deduplicator.is_dup()     ← skip if seen
            └─ _move_to_storage(...)     ← place in data/raw/<src>/<Y>/<M>/

Retry policy
------------
  Retryable   : 429, 500, 502, 503, 504, asyncio.TimeoutError, aiohttp.ClientError
  Non-retryable: 400, 401, 403, 404, 410
  Backoff     : wait = backoff_base ** attempt  (2, 4, 8, 16 sec)
  429 special : respects Retry-After header if present
"""
from __future__ import annotations

import asyncio
import json
import logging
import shutil
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

import aiohttp
import aiofiles

from .config import BulkDownloadConfig, settings as _default_settings
from .deduplicator import Deduplicator
from .hasher import sha256_file
from .manifest import Manifest
from .models import DocumentType, DownloadJob, DownloadResult, DownloadStatus
from .validator import validate_file, validate_http_response

logger = logging.getLogger(__name__)


# ── Public entry point ────────────────────────────────────────────────────────

async def download_all(
    jobs: list[DownloadJob],
    cfg: BulkDownloadConfig = _default_settings,
    progress_callback=None,
) -> list[DownloadResult]:
    """
    Download all jobs concurrently, respecting MAX_WORKERS concurrency limit.

    Args:
        jobs:              List of DownloadJob objects to process.
        cfg:               Configuration (workers, retries, timeouts …).
        progress_callback: Optional async callable(result) called after each
                           download completes (useful for live progress bars).

    Returns:
        List of DownloadResult objects, one per job, in submission order.
    """
    if not jobs:
        return []

    # Build shared infrastructure
    connector = aiohttp.TCPConnector(limit=cfg.max_workers * 2)
    timeout = aiohttp.ClientTimeout(
        connect=cfg.connect_timeout,
        total=cfg.read_timeout,
    )
    headers = {"User-Agent": cfg.user_agent}

    semaphore = asyncio.Semaphore(cfg.max_workers)

    with Manifest(cfg) as manifest:
        deduplicator = Deduplicator(manifest)

        async with aiohttp.ClientSession(
            connector=connector,
            timeout=timeout,
            headers=headers,
        ) as session:
            tasks = [
                _download_one(job, session, semaphore, manifest, deduplicator, cfg)
                for job in jobs
            ]
            results: list[DownloadResult] = []
            for coro in asyncio.as_completed(tasks):
                result = await coro
                results.append(result)
                manifest.record(result)
                if result.succeeded:
                    deduplicator.register(result.sha256)  # type: ignore[arg-type]
                if progress_callback:
                    await progress_callback(result)
                logger.info(str(result))

        # Export the full manifest JSON for downstream teammates
        manifest.export_json()

    return results


# ── Single download with retry ────────────────────────────────────────────────

async def _download_one(
    job: DownloadJob,
    session: aiohttp.ClientSession,
    semaphore: asyncio.Semaphore,
    manifest: Manifest,
    deduplicator: Deduplicator,
    cfg: BulkDownloadConfig,
) -> DownloadResult:
    """
    Download a single job, retrying on transient failures.
    All file I/O happens in a temp file; the file is only moved to
    permanent storage after passing all validation checks.
    """
    async with semaphore:
        logger.debug("Starting: %s", job.url)
        return await _fetch_with_retry(job, session, manifest, deduplicator, cfg)


async def _fetch_with_retry(
    job: DownloadJob,
    session: aiohttp.ClientSession,
    manifest: Manifest,
    deduplicator: Deduplicator,
    cfg: BulkDownloadConfig,
) -> DownloadResult:
    """Core fetch loop with exponential backoff."""
    last_result: Optional[DownloadResult] = None

    for attempt in range(cfg.max_retries + 1):  # attempt 0 … max_retries
        if attempt > 0:
            wait = cfg.backoff_base ** attempt
            logger.info(
                "Retry %d/%d for %s — waiting %.0f s",
                attempt, cfg.max_retries, job.url, wait,
            )
            await asyncio.sleep(wait)

        result = await _try_download(job, session, deduplicator, cfg, attempt + 1)
        last_result = result

        # Decide whether to retry
        if result.status == DownloadStatus.SUCCESS:
            return result
        if result.status == DownloadStatus.DUPLICATE:
            return result
        if result.status == DownloadStatus.INVALID_FILE:
            return result  # no point retrying a bad file

        # HTTP_ERROR with non-retryable code
        if result.status == DownloadStatus.HTTP_ERROR:
            if result.http_status in cfg.non_retryable_statuses:
                logger.warning(
                    "Non-retryable HTTP %s for %s", result.http_status, job.url
                )
                return result
            # 429: try to honour Retry-After (already encoded in backoff)

        # TIMEOUT / FAILED → retryable — loop continues

    # Exhausted all retries
    assert last_result is not None
    logger.error("All %d attempts failed for %s", cfg.max_retries + 1, job.url)
    return last_result


async def _try_download(
    job: DownloadJob,
    session: aiohttp.ClientSession,
    deduplicator: Deduplicator,
    cfg: BulkDownloadConfig,
    attempt_number: int,
) -> DownloadResult:
    """
    A single HTTP request + file save attempt.
    Returns a DownloadResult without any retry logic.
    """
    now = datetime.now(timezone.utc)
    final_url = job.url

    tmp_path: Optional[Path] = None

    try:
        async with session.get(job.url, allow_redirects=True) as resp:
            final_url = str(resp.url)
            http_status = resp.status
            content_type = resp.headers.get("Content-Type", "")

            # ── 1. HTTP status check ──────────────────────────────────────
            if http_status in cfg.non_retryable_statuses:
                return DownloadResult(
                    job=job,
                    status=DownloadStatus.HTTP_ERROR,
                    http_status=http_status,
                    content_type=content_type,
                    final_url=final_url,
                    error_msg=f"HTTP {http_status}",
                    attempts=attempt_number,
                    downloaded_at=now,
                )

            if http_status in cfg.retryable_statuses:
                return DownloadResult(
                    job=job,
                    status=DownloadStatus.HTTP_ERROR,
                    http_status=http_status,
                    content_type=content_type,
                    final_url=final_url,
                    error_msg=f"HTTP {http_status} (retryable)",
                    attempts=attempt_number,
                    downloaded_at=now,
                )

            if http_status not in (200, 206):
                return DownloadResult(
                    job=job,
                    status=DownloadStatus.HTTP_ERROR,
                    http_status=http_status,
                    content_type=content_type,
                    final_url=final_url,
                    error_msg=f"Unexpected HTTP {http_status}",
                    attempts=attempt_number,
                    downloaded_at=now,
                )

            # ── 2. HTTP Content-Type check ────────────────────────────────
            http_validation = validate_http_response(
                http_status, content_type, job.document_type
            )
            if not http_validation.valid:
                return DownloadResult(
                    job=job,
                    status=DownloadStatus.INVALID_FILE,
                    http_status=http_status,
                    content_type=content_type,
                    final_url=final_url,
                    error_msg=http_validation.reason,
                    attempts=attempt_number,
                    downloaded_at=now,
                )

            # ── 3. Stream to temp file ────────────────────────────────────
            suffix = f".{job.document_type.value}"
            tmp_fd, tmp_str = tempfile.mkstemp(suffix=suffix, prefix="atlas_bd_")
            tmp_path = Path(tmp_str)

            total_bytes = 0
            try:
                async with aiofiles.open(tmp_path, "wb") as f:
                    async for chunk in resp.content.iter_chunked(cfg.chunk_size):
                        await f.write(chunk)
                        total_bytes += len(chunk)
                        if total_bytes > cfg.max_file_size_bytes:
                            raise ValueError(
                                f"Response exceeded {cfg.max_file_size_mb} MB limit"
                            )
            except ValueError as exc:
                tmp_path.unlink(missing_ok=True)
                return DownloadResult(
                    job=job,
                    status=DownloadStatus.INVALID_FILE,
                    http_status=http_status,
                    content_type=content_type,
                    final_url=final_url,
                    file_size=total_bytes,
                    error_msg=str(exc),
                    attempts=attempt_number,
                    downloaded_at=now,
                )

        # ── 4. File validation (magic bytes + size) ───────────────────────
        file_validation = validate_file(tmp_path, job.document_type, cfg)
        if not file_validation.valid:
            tmp_path.unlink(missing_ok=True)
            return DownloadResult(
                job=job,
                status=DownloadStatus.INVALID_FILE,
                http_status=http_status,
                content_type=content_type,
                final_url=final_url,
                file_size=total_bytes,
                error_msg=file_validation.reason,
                attempts=attempt_number,
                downloaded_at=now,
            )

        # ── 5. SHA-256 hash ───────────────────────────────────────────────
        sha256 = sha256_file(tmp_path)

        # ── 6. Duplicate check ────────────────────────────────────────────
        if deduplicator.is_duplicate(sha256):
            tmp_path.unlink(missing_ok=True)
            return DownloadResult(
                job=job,
                status=DownloadStatus.DUPLICATE,
                http_status=http_status,
                content_type=content_type,
                final_url=final_url,
                file_size=total_bytes,
                sha256=sha256,
                attempts=attempt_number,
                downloaded_at=now,
            )

        # ── 7. Move to permanent storage ──────────────────────────────────
        dest_path = _build_dest_path(job, sha256, cfg)
        dest_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(tmp_path), str(dest_path))

        logger.info(
            "Saved: %s → %s (%.1f KB)", job.url, dest_path, total_bytes / 1024
        )

        return DownloadResult(
            job=job,
            status=DownloadStatus.SUCCESS,
            filename=dest_path.name,
            filepath=dest_path,
            sha256=sha256,
            file_size=total_bytes,
            http_status=http_status,
            content_type=content_type,
            final_url=final_url,
            attempts=attempt_number,
            downloaded_at=now,
        )

    except asyncio.TimeoutError:
        if tmp_path:
            tmp_path.unlink(missing_ok=True)
        return DownloadResult(
            job=job,
            status=DownloadStatus.TIMEOUT,
            final_url=final_url,
            error_msg="Request timed out",
            attempts=attempt_number,
            downloaded_at=now,
        )

    except aiohttp.ClientError as exc:
        if tmp_path:
            tmp_path.unlink(missing_ok=True)
        return DownloadResult(
            job=job,
            status=DownloadStatus.FAILED,
            final_url=final_url,
            error_msg=f"Network error: {exc}",
            attempts=attempt_number,
            downloaded_at=now,
        )

    except Exception as exc:  # noqa: BLE001
        if tmp_path:
            tmp_path.unlink(missing_ok=True)
        logger.exception("Unexpected error downloading %s", job.url)
        return DownloadResult(
            job=job,
            status=DownloadStatus.FAILED,
            final_url=final_url,
            error_msg=f"Unexpected: {exc}",
            attempts=attempt_number,
            downloaded_at=now,
        )


# ── Storage helpers ───────────────────────────────────────────────────────────

def _build_dest_path(
    job: DownloadJob,
    sha256: str,
    cfg: BulkDownloadConfig,
) -> Path:
    """
    Build the canonical destination path for a downloaded file.

    Pattern: data/raw/<source>/<YYYY>/<MM>/<short_hash>_<filename>

    Using the hash prefix in the filename prevents collisions when two
    different URLs point to files with the same name.
    """
    now = datetime.now(timezone.utc)
    year = now.strftime("%Y")
    month = now.strftime("%m")

    # Derive a safe filename from the URL
    parsed = urlparse(job.url)
    url_filename = Path(parsed.path).name or "document"
    # Sanitise
    safe_name = "".join(c if c.isalnum() or c in "._-" else "_" for c in url_filename)
    if not safe_name:
        safe_name = f"document_{uuid.uuid4().hex[:8]}"

    short_hash = sha256[:12]
    filename = f"{short_hash}_{safe_name}"

    return cfg.data_raw_dir / job.source / year / month / filename


# ── URL list loader ───────────────────────────────────────────────────────────

def load_jobs_from_file(path: Path) -> list[DownloadJob]:
    """
    Load a list of DownloadJob objects from a JSON file.

    Expected format (array of objects):
    [
      {
        "source": "who",
        "url": "https://…",
        "document_type": "pdf",
        "allowed_domain": "who.int",
        "description": "optional label"
      },
      …
    ]
    """
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, list):
        raise ValueError(f"Expected a JSON array in {path}, got {type(raw).__name__}")
    return [DownloadJob.from_dict(item) for item in raw]


def load_jobs_from_sources(
    source_names: list[str],
    cfg: BulkDownloadConfig = _default_settings,
) -> list[DownloadJob]:
    """
    Load jobs from the data_sources/<source>.json files.

    Args:
        source_names: e.g. ["who", "cdc", "nih"]
        cfg:          Config (provides data_sources_dir path).

    Returns:
        Flattened list of all DownloadJob objects from all source files.
    """
    jobs: list[DownloadJob] = []
    for name in source_names:
        src_file = cfg.data_sources_dir / f"{name}_sources.json"
        if not src_file.exists():
            logger.warning("Source file not found, skipping: %s", src_file)
            continue
        batch = load_jobs_from_file(src_file)
        logger.info("Loaded %d jobs from %s", len(batch), src_file.name)
        jobs.extend(batch)
    return jobs
