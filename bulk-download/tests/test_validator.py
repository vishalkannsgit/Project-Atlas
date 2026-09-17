"""
test_validator.py
=================
Tests for bulk_downloader.validator
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from bulk_downloader.config import BulkDownloadConfig
from bulk_downloader.models import DocumentType
from bulk_downloader.validator import (
    validate_file,
    validate_http_response,
)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_config(min_bytes: int = 512, max_mb: int = 100) -> BulkDownloadConfig:
    cfg = BulkDownloadConfig()
    cfg.min_file_size_bytes = min_bytes
    cfg.max_file_size_mb = max_mb
    return cfg


def _write(tmp_path, name, content: bytes) -> Path:
    p = tmp_path / name
    p.write_bytes(content)
    return p


PDF_HEADER = b"%PDF-1.4" + b" " * 600
HTML_HEADER = b"<!DOCTYPE html><html><body>Hello</body></html>" + b" " * 550
HTML_HEADER_LOWER = b"<!doctype html><html></html>" + b" " * 550
SMALL_FILE = b"%PDF" + b"x" * 10  # too small
HUGE_FILE = b"%PDF" + b"x" * (101 * 1024 * 1024)   # over 100 MB in memory — we don't write this


# ── validate_http_response ────────────────────────────────────────────────────

class TestValidateHttpResponse:
    def test_200_correct_pdf_content_type(self):
        r = validate_http_response(200, "application/pdf", DocumentType.PDF)
        assert r.valid

    def test_206_accepted(self):
        r = validate_http_response(206, "application/pdf", DocumentType.PDF)
        assert r.valid

    def test_404_invalid(self):
        r = validate_http_response(404, "text/html", DocumentType.PDF)
        assert not r.valid
        assert "404" in r.reason

    def test_content_type_mismatch_html_instead_of_pdf(self):
        """The classic case: server returns an error page as text/html."""
        r = validate_http_response(200, "text/html; charset=utf-8", DocumentType.PDF)
        assert not r.valid
        assert "mismatch" in r.reason.lower()

    def test_html_doc_type_valid(self):
        r = validate_http_response(200, "text/html", DocumentType.HTML)
        assert r.valid

    def test_unknown_content_type_passes_with_warning(self):
        """Unknown content-type is not immediately rejected — magic bytes decide."""
        r = validate_http_response(200, "application/octet-stream", DocumentType.PDF)
        assert r.valid  # lenient; magic bytes will do final check
        assert "Unknown" in r.reason or r.detected_type is None

    def test_content_type_with_charset_stripped(self):
        """charset= portion must be stripped before matching."""
        r = validate_http_response(
            200, "application/pdf; charset=utf-8", DocumentType.PDF
        )
        assert r.valid

    def test_non_200_non_206_status(self):
        for status in [301, 400, 403, 500, 503]:
            r = validate_http_response(status, "application/pdf", DocumentType.PDF)
            assert not r.valid, f"Expected invalid for HTTP {status}"


# ── validate_file ─────────────────────────────────────────────────────────────

class TestValidateFile:
    def test_valid_pdf(self, tmp_path):
        p = _write(tmp_path, "doc.pdf", PDF_HEADER)
        cfg = _make_config(min_bytes=10)
        r = validate_file(p, DocumentType.PDF, cfg)
        assert r.valid
        assert r.detected_type == DocumentType.PDF

    def test_valid_html(self, tmp_path):
        p = _write(tmp_path, "page.html", HTML_HEADER)
        cfg = _make_config(min_bytes=10)
        r = validate_file(p, DocumentType.HTML, cfg)
        assert r.valid

    def test_html_lowercase_doctype(self, tmp_path):
        p = _write(tmp_path, "page.html", HTML_HEADER_LOWER)
        cfg = _make_config(min_bytes=10)
        r = validate_file(p, DocumentType.HTML, cfg)
        assert r.valid

    def test_pdf_served_as_html(self, tmp_path):
        """Content is actually an HTML error page but extension says .pdf."""
        p = _write(tmp_path, "tricky.pdf", HTML_HEADER)
        cfg = _make_config(min_bytes=10)
        r = validate_file(p, DocumentType.PDF, cfg)
        assert not r.valid
        assert "mismatch" in r.reason.lower()

    def test_file_too_small(self, tmp_path):
        p = _write(tmp_path, "tiny.pdf", b"%PDF" + b"x" * 5)
        cfg = _make_config(min_bytes=512)
        r = validate_file(p, DocumentType.PDF, cfg)
        assert not r.valid
        assert "small" in r.reason.lower()

    def test_file_too_large(self, tmp_path):
        # Write a file that is 2 bytes over the 1 MB limit
        content = b"%PDF" + b"X" * (1024 * 1024 + 2)
        p = _write(tmp_path, "huge.pdf", content)
        cfg = _make_config(min_bytes=10, max_mb=1)
        r = validate_file(p, DocumentType.PDF, cfg)
        assert not r.valid
        assert "large" in r.reason.lower()

    def test_missing_file(self, tmp_path):
        p = tmp_path / "ghost.pdf"
        cfg = _make_config(min_bytes=10)
        r = validate_file(p, DocumentType.PDF, cfg)
        assert not r.valid
        assert "not found" in r.reason.lower()

    def test_unrecognised_binary_rejected(self, tmp_path):
        p = _write(tmp_path, "weird.pdf", b"\x00\x01\x02\x03" + b"x" * 600)
        cfg = _make_config(min_bytes=10)
        r = validate_file(p, DocumentType.PDF, cfg)
        assert not r.valid
