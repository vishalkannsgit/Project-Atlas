"""
bulk_downloader
===============
Project Atlas — Data Acquisition: Bulk Download Service

Reliably downloads, validates, deduplicates, and stages large numbers
of documents (PDFs, HTML) from public health sources (WHO, CDC, NIH)
for the downstream Atlas processing pipeline.

Pipeline:
    URL List → Download Queue → Async Workers
             → Validator → Hasher → Deduplicator
             → data/raw/<source>/<YYYY>/<MM>/
             → Manifest (SQLite + JSON export)
             → data/staging/acquisition/
"""
from importlib.metadata import version, PackageNotFoundError

try:
    __version__ = version("bulk-downloader")
except PackageNotFoundError:
    __version__ = "0.1.0"

__all__ = [
    "config",
    "models",
    "downloader",
    "validator",
    "hasher",
    "deduplicator",
    "manifest",
]
