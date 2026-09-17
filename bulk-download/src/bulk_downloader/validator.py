"""
validator.py
============
File and HTTP response validation for the Bulk Download service.

Validates:
  1. HTTP status code is acceptable (200 / 206).
  2. Content-Type header matches the expected document type.
  3. File magic bytes (first N bytes) confirm the declared type.
  4. File size is within configured limits.

Why magic bytes?
  A server might return a 200 with Content-Type: application/pdf but
  actually serve an HTML error page.  Checking the actual file header
  catches this.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from .config import BulkDownloadConfig, settings as _default_settings
from .models import DocumentType


# ── Magic byte signatures ──────────────────────────────────────────────────────

# Maps DocumentType → list of byte-prefix tuples that are acceptable
_MAGIC: dict[DocumentType, list[bytes]] = {
    DocumentType.PDF: [
        b"%PDF",          # Standard PDF header
    ],
    DocumentType.HTML: [
        b"<!DOCTYPE",
        b"<!doctype",
        b"<html",
        b"<HTML",
        b"<?xml",         # Some WHO docs use XHTML
    ],
    DocumentType.DOC: [
        b"\xd0\xcf\x11\xe0",   # OLE compound document (old .doc)
    ],
    DocumentType.DOCX: [
        b"PK\x03\x04",   # ZIP archive (modern Office formats)
    ],
    DocumentType.XML: [
        b"<?xml",
        b"<",
    ],
}

# Maps Content-Type (prefix) → DocumentType
_CONTENT_TYPE_MAP: dict[str, DocumentType] = {
    "application/pdf":                        DocumentType.PDF,
    "text/html":                              DocumentType.HTML,
    "application/xhtml":                      DocumentType.HTML,
    "application/msword":                     DocumentType.DOC,
    "application/vnd.openxmlformats":         DocumentType.DOCX,
    "application/vnd.ms-word":                DocumentType.DOC,
    "text/xml":                               DocumentType.XML,
    "application/xml":                        DocumentType.XML,
}

MAGIC_PROBE_BYTES = 512  # Read first 512 bytes for magic detection


# ── Result ────────────────────────────────────────────────────────────────────

@dataclass
class ValidationResult:
    valid: bool
    reason: str = ""
    detected_type: Optional[DocumentType] = None

    def __bool__(self) -> bool:
        return self.valid


# ── Public API ────────────────────────────────────────────────────────────────

def validate_http_response(
    http_status: int,
    content_type: str,
    expected_type: DocumentType,
) -> ValidationResult:
    """
    Check HTTP status and Content-Type header.

    Args:
        http_status:   The integer HTTP response status code.
        content_type:  Raw Content-Type header value (may include charset).
        expected_type: The DocumentType we expect.

    Returns:
        ValidationResult — valid=True if acceptable, with a reason string.
    """
    # 1. Status check
    if http_status not in (200, 206):
        return ValidationResult(
            valid=False,
            reason=f"Unexpected HTTP status {http_status}",
        )

    # 2. Content-Type check (lenient: we look for a prefix match)
    ct_base = content_type.split(";")[0].strip().lower()
    detected = _detect_type_from_content_type(ct_base)

    if detected is None:
        # Unknown content type — warn but allow magic-bytes check to decide
        return ValidationResult(
            valid=True,
            reason=f"Unknown Content-Type '{ct_base}', will rely on magic bytes",
            detected_type=None,
        )

    if detected != expected_type:
        return ValidationResult(
            valid=False,
            reason=(
                f"Content-Type mismatch: expected {expected_type.value}, "
                f"got '{ct_base}' (→ {detected.value})"
            ),
            detected_type=detected,
        )

    return ValidationResult(valid=True, detected_type=detected)


def validate_file(
    path: Path,
    expected_type: DocumentType,
    cfg: BulkDownloadConfig = _default_settings,
) -> ValidationResult:
    """
    Validate a downloaded file using magic bytes and size checks.

    Args:
        path:          Path to the downloaded file.
        expected_type: The DocumentType we expect.
        cfg:           Config object (for size limits).

    Returns:
        ValidationResult.
    """
    if not path.exists():
        return ValidationResult(valid=False, reason=f"File not found: {path}")

    size = path.stat().st_size

    # 1. Size — minimum
    if size < cfg.min_file_size_bytes:
        return ValidationResult(
            valid=False,
            reason=f"File too small ({size} bytes < {cfg.min_file_size_bytes} minimum)",
        )

    # 2. Size — maximum
    if size > cfg.max_file_size_bytes:
        return ValidationResult(
            valid=False,
            reason=(
                f"File too large ({size / 1_048_576:.1f} MB "
                f"> {cfg.max_file_size_mb} MB limit)"
            ),
        )

    # 3. Magic bytes
    with open(path, "rb") as fh:
        header = fh.read(MAGIC_PROBE_BYTES)

    detected = _detect_type_from_magic(header)

    if detected is None:
        return ValidationResult(
            valid=False,
            reason="Unrecognised file signature (magic bytes do not match any known type)",
            detected_type=None,
        )

    if detected != expected_type:
        return ValidationResult(
            valid=False,
            reason=(
                f"Magic bytes mismatch: expected {expected_type.value}, "
                f"detected {detected.value}"
            ),
            detected_type=detected,
        )

    return ValidationResult(valid=True, detected_type=detected)


# ── Internal helpers ──────────────────────────────────────────────────────────

def _detect_type_from_content_type(ct: str) -> Optional[DocumentType]:
    for prefix, doc_type in _CONTENT_TYPE_MAP.items():
        if ct.startswith(prefix):
            return doc_type
    return None


def _detect_type_from_magic(header: bytes) -> Optional[DocumentType]:
    for doc_type, signatures in _MAGIC.items():
        for sig in signatures:
            if header.startswith(sig):
                return doc_type
    return None
