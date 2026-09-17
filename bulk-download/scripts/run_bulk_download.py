#!/usr/bin/env python3
"""
run_bulk_download.py
====================
CLI entry point for the Project Atlas Bulk Download service.

Usage examples
--------------
# Download from all three built-in sources with 5 workers:
    python scripts/run_bulk_download.py --sources who cdc nih

# Use more workers:
    python scripts/run_bulk_download.py --sources who --workers 8

# Provide a custom URL list file:
    python scripts/run_bulk_download.py --url-file my_urls.json

# Just show what would run (dry run):
    python scripts/run_bulk_download.py --sources who cdc nih --dry-run

Environment variable overrides
-------------------------------
    ATLAS_BD_WORKERS        int   (default 5)
    ATLAS_BD_MAX_RETRIES    int   (default 4)
    ATLAS_BD_BACKOFF_BASE   float (default 2.0)
    ATLAS_BD_MAX_FILE_MB    int   (default 100)
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from pathlib import Path
from collections import Counter

# Make sure the package is importable when run from repo root or scripts/
_HERE = Path(__file__).resolve().parent
_SERVICE_ROOT = _HERE.parent
sys.path.insert(0, str(_SERVICE_ROOT / "src"))

from bulk_downloader.config import BulkDownloadConfig
from bulk_downloader.downloader import download_all, load_jobs_from_file, load_jobs_from_sources
from bulk_downloader.models import DownloadStatus


# ── Logging setup ─────────────────────────────────────────────────────────────

def _configure_logging(verbose: bool) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)-7s] %(name)s — %(message)s",
        datefmt="%H:%M:%S",
    )
    # Quieten noisy third-party loggers
    logging.getLogger("aiohttp").setLevel(logging.WARNING)
    logging.getLogger("asyncio").setLevel(logging.WARNING)


# ── CLI ───────────────────────────────────────────────────────────────────────

def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="run_bulk_download",
        description="Project Atlas — Bulk Document Downloader",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )

    source_group = p.add_mutually_exclusive_group(required=True)
    source_group.add_argument(
        "--sources",
        nargs="+",
        metavar="SOURCE",
        help="Built-in source names to download (e.g. who cdc nih)",
    )
    source_group.add_argument(
        "--url-file",
        type=Path,
        metavar="FILE",
        help="Path to a custom JSON file with download job definitions",
    )

    p.add_argument(
        "--workers",
        type=int,
        default=None,
        metavar="N",
        help="Max concurrent downloads (overrides ATLAS_BD_WORKERS env var)",
    )
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="List jobs that would be downloaded without actually downloading",
    )
    p.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Enable DEBUG logging",
    )

    return p


# ── Main ──────────────────────────────────────────────────────────────────────

async def main(args: argparse.Namespace) -> int:
    """Async main — returns exit code."""
    _configure_logging(args.verbose)
    log = logging.getLogger("atlas.bulk_download")

    cfg = BulkDownloadConfig()
    if args.workers:
        cfg.max_workers = args.workers

    # ── Load jobs ──────────────────────────────────────────────────────────
    if args.url_file:
        if not args.url_file.exists():
            log.error("URL file not found: %s", args.url_file)
            return 1
        jobs = load_jobs_from_file(args.url_file)
        log.info("Loaded %d jobs from %s", len(jobs), args.url_file)
    else:
        jobs = load_jobs_from_sources(args.sources, cfg)

    if not jobs:
        log.error("No download jobs found. Check your source files.")
        return 1

    # ── Dry run ────────────────────────────────────────────────────────────
    if args.dry_run:
        print(f"\n{'─'*60}")
        print(f"  DRY RUN — {len(jobs)} jobs would be downloaded")
        print(f"{'─'*60}")
        for i, job in enumerate(jobs, 1):
            desc = job.description or job.url.split("/")[-1]
            print(f"  {i:>3}. [{job.source:>10}] {desc}")
            print(f"       {job.url}")
        print(f"{'─'*60}\n")
        return 0

    # ── Run downloads ──────────────────────────────────────────────────────
    print(f"\n{'═'*60}")
    print(f"  Project Atlas — Bulk Downloader")
    print(f"  Jobs: {len(jobs)}  |  Workers: {cfg.max_workers}  |  Max retries: {cfg.max_retries}")
    print(f"  Output: {cfg.data_raw_dir}")
    print(f"  Manifest: {cfg.manifest_db_path}")
    print(f"{'═'*60}\n")

    results = await download_all(jobs, cfg)

    # ── Summary table ──────────────────────────────────────────────────────
    counts = Counter(r.status for r in results)
    total = len(results)

    status_icons = {
        DownloadStatus.SUCCESS:      ("✅", "SUCCESS"),
        DownloadStatus.DUPLICATE:    ("♻️ ", "DUPLICATE"),
        DownloadStatus.INVALID_FILE: ("⚠️ ", "INVALID_FILE"),
        DownloadStatus.HTTP_ERROR:   ("❌", "HTTP_ERROR"),
        DownloadStatus.TIMEOUT:      ("⏱️ ", "TIMEOUT"),
        DownloadStatus.FAILED:       ("💥", "FAILED"),
    }

    print(f"\n{'═'*60}")
    print(f"  Download Summary")
    print(f"{'─'*60}")
    for status, (icon, label) in status_icons.items():
        count = counts.get(status, 0)
        if count > 0:
            bar = "█" * count
            print(f"  {icon}  {label:<14} {count:>4}  {bar}")
    print(f"{'─'*60}")
    print(f"  {'TOTAL':<18} {total:>4}")
    print(f"{'═'*60}")
    print(f"\n  Manifest DB  : {cfg.manifest_db_path}")
    print(f"  Manifest JSON: {cfg.manifest_json_path}")
    print(f"  Raw files    : {cfg.data_raw_dir}\n")

    # Return non-zero if any downloads failed (not just duplicates)
    hard_failures = sum(
        counts.get(s, 0)
        for s in (DownloadStatus.FAILED, DownloadStatus.HTTP_ERROR, DownloadStatus.TIMEOUT)
    )
    return 1 if hard_failures > 0 else 0


def cli() -> None:
    parser = _build_parser()
    args = parser.parse_args()
    exit_code = asyncio.run(main(args))
    sys.exit(exit_code)


if __name__ == "__main__":
    cli()
