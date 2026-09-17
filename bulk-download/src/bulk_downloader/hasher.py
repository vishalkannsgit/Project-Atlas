"""
hasher.py
=========
SHA-256 file hashing for the Bulk Download service.

Streams files in fixed-size chunks so arbitrarily large documents
(100 MB+ PDFs) never have to be fully loaded into memory.
"""
from __future__ import annotations

import hashlib
from pathlib import Path


CHUNK_SIZE = 8 * 1024  # 8 KB — matches the download chunk size


def sha256_file(path: Path, chunk_size: int = CHUNK_SIZE) -> str:
    """
    Compute the SHA-256 hex digest of a file by streaming it in chunks.

    Args:
        path:       Absolute path to the file.
        chunk_size: Read buffer size in bytes (default 8 KB).

    Returns:
        64-character lowercase hex string, e.g. 'abc123…'.

    Raises:
        FileNotFoundError: if *path* does not exist.
        OSError:           on any other I/O failure.
    """
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        while chunk := fh.read(chunk_size):
            h.update(chunk)
    return h.hexdigest()


def sha256_bytes(data: bytes) -> str:
    """
    Compute SHA-256 of an in-memory bytes object.
    Useful in tests or for small payloads.
    """
    return hashlib.sha256(data).hexdigest()
