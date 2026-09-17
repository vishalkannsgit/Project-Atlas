"""
test_hasher.py
==============
Tests for bulk_downloader.hasher
"""
from __future__ import annotations

import hashlib
import tempfile
from pathlib import Path

import pytest

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from bulk_downloader.hasher import sha256_file, sha256_bytes


class TestSha256Bytes:
    def test_known_value(self):
        """SHA-256 of b'hello' is well-known."""
        expected = hashlib.sha256(b"hello").hexdigest()
        assert sha256_bytes(b"hello") == expected

    def test_empty_bytes(self):
        expected = hashlib.sha256(b"").hexdigest()
        assert sha256_bytes(b"") == expected

    def test_returns_64_char_hex(self):
        result = sha256_bytes(b"test")
        assert len(result) == 64
        assert all(c in "0123456789abcdef" for c in result)


class TestSha256File:
    def test_known_content(self, tmp_path):
        content = b"Project Atlas bulk downloader"
        f = tmp_path / "test.bin"
        f.write_bytes(content)

        expected = hashlib.sha256(content).hexdigest()
        assert sha256_file(f) == expected

    def test_large_file_streaming(self, tmp_path):
        """Confirm streaming works for a file larger than a single chunk."""
        content = b"X" * (64 * 1024)  # 64 KB — spans multiple 8 KB chunks
        f = tmp_path / "large.bin"
        f.write_bytes(content)

        expected = hashlib.sha256(content).hexdigest()
        assert sha256_file(f) == expected

    def test_two_identical_files_same_hash(self, tmp_path):
        content = b"%PDF-1.4 fake pdf content"
        f1 = tmp_path / "a.pdf"
        f2 = tmp_path / "b.pdf"
        f1.write_bytes(content)
        f2.write_bytes(content)

        assert sha256_file(f1) == sha256_file(f2)

    def test_different_content_different_hash(self, tmp_path):
        f1 = tmp_path / "a.bin"
        f2 = tmp_path / "b.bin"
        f1.write_bytes(b"content A")
        f2.write_bytes(b"content B")

        assert sha256_file(f1) != sha256_file(f2)

    def test_file_not_found_raises(self, tmp_path):
        missing = tmp_path / "does_not_exist.pdf"
        with pytest.raises(FileNotFoundError):
            sha256_file(missing)

    def test_custom_chunk_size(self, tmp_path):
        """Hashing is chunk-size independent."""
        content = b"A" * 1000
        f = tmp_path / "f.bin"
        f.write_bytes(content)

        hash_default = sha256_file(f)
        hash_tiny = sha256_file(f, chunk_size=16)
        assert hash_default == hash_tiny
