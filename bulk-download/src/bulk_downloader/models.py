"""
models.py
=========
Shared dataclasses and enums for the Bulk Download service.

DownloadJob  → input  (what to download)
DownloadResult → output (what happened)
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Optional


# ── Status ────────────────────────────────────────────────────────────────────

class DownloadStatus(str, Enum):
    """
    Every download ends in exactly one of these states.
    Using str-enum means status values serialize cleanly to JSON.
    """
    SUCCESS       = "SUCCESS"        # Downloaded, validated, stored
    INVALID_FILE  = "INVALID_FILE"   # Content-type or magic-bytes mismatch
    HTTP_ERROR    = "HTTP_ERROR"     # 4xx/5xx not retried, or retries exhausted
    TIMEOUT       = "TIMEOUT"        # Connection/read timeout exhausted
    DUPLICATE     = "DUPLICATE"      # SHA-256 already in manifest
    FAILED        = "FAILED"         # Any other unrecoverable error


class DocumentType(str, Enum):
    PDF   = "pdf"
    HTML  = "html"
    DOC   = "doc"
    DOCX  = "docx"
    XML   = "xml"
    UNKNOWN = "unknown"


# ── Input ─────────────────────────────────────────────────────────────────────

@dataclass
class DownloadJob:
    """
    Describes a single document to acquire.
    Loaded from data_sources/<source>.json.
    """
    source: str
    """Logical source name: 'who' | 'cdc' | 'nih' | …"""

    url: str
    """Original URL to fetch."""

    document_type: DocumentType = DocumentType.PDF
    """Expected document type — used for validation."""

    allowed_domain: str = ""
    """
    Domain the URL must belong to (optional guard against open-redirect
    responses that serve content from a different origin).
    Empty string = no domain restriction.
    """

    description: str = ""
    """Human-readable label for logging / manifest."""

    @classmethod
    def from_dict(cls, d: dict) -> "DownloadJob":
        return cls(
            source=d["source"],
            url=d["url"],
            document_type=DocumentType(d.get("document_type", "pdf")),
            allowed_domain=d.get("allowed_domain", ""),
            description=d.get("description", ""),
        )


# ── Output ────────────────────────────────────────────────────────────────────

@dataclass
class DownloadResult:
    """
    The complete record of a single download attempt.
    Written to the manifest DB after each download.
    """
    job: DownloadJob

    status: DownloadStatus

    # ── File info (None if download did not succeed) ──────────────────────
    filename: Optional[str]   = None
    filepath: Optional[Path]  = None
    sha256:   Optional[str]   = None
    file_size: Optional[int]  = None

    # ── HTTP info ─────────────────────────────────────────────────────────
    http_status:  Optional[int] = None
    content_type: Optional[str] = None
    final_url:    str           = ""
    """URL after all redirects, may differ from job.url."""

    # ── Error info ────────────────────────────────────────────────────────
    error_msg: Optional[str] = None
    attempts:  int           = 1
    """How many HTTP attempts were made (1 = no retry needed)."""

    # ── Timing ────────────────────────────────────────────────────────────
    downloaded_at: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc)
    )

    # ── Convenience properties ────────────────────────────────────────────

    @property
    def succeeded(self) -> bool:
        return self.status == DownloadStatus.SUCCESS

    @property
    def is_duplicate(self) -> bool:
        return self.status == DownloadStatus.DUPLICATE

    def to_dict(self) -> dict:
        """Serialise to a plain dict suitable for JSON export."""
        return {
            "source":        self.job.source,
            "description":   self.job.description,
            "original_url":  self.job.url,
            "final_url":     self.final_url or self.job.url,
            "filename":      self.filename,
            "filepath":      str(self.filepath) if self.filepath else None,
            "document_type": self.job.document_type.value,
            "file_size":     self.file_size,
            "sha256":        self.sha256,
            "http_status":   self.http_status,
            "content_type":  self.content_type,
            "status":        self.status.value,
            "error_msg":     self.error_msg,
            "attempts":      self.attempts,
            "downloaded_at": self.downloaded_at.isoformat(),
        }

    def __str__(self) -> str:
        icon = {
            DownloadStatus.SUCCESS:      "✅",
            DownloadStatus.DUPLICATE:    "♻️ ",
            DownloadStatus.INVALID_FILE: "⚠️ ",
            DownloadStatus.HTTP_ERROR:   "❌",
            DownloadStatus.TIMEOUT:      "⏱️ ",
            DownloadStatus.FAILED:       "💥",
        }.get(self.status, "?")
        name = self.filename or self.job.url.split("/")[-1] or self.job.url
        return f"{icon} [{self.status.value:>12}] {name}"
