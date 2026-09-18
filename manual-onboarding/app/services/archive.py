import io
import os
import zipfile
import logging
from typing import List, Tuple
from fastapi import HTTPException, status
from app.core.config import settings

logger = logging.getLogger("atlas.archive")


class SafeArchiveExtractor:
    @staticmethod
    def extract_zip(archive_bytes: bytes) -> List[Tuple[str, bytes]]:
        """
        Safely unpacks a ZIP archive in-memory with guards against
        path traversal (Zip Slip), file count limits, and zip bombs.
        
        Returns:
            List of tuples: [(sanitized_filename, file_bytes), ...]
        """
        extracted_files: List[Tuple[str, bytes]] = []

        try:
            zip_buffer = io.BytesIO(archive_bytes)
            with zipfile.ZipFile(zip_buffer, "r") as zf:
                infolist = zf.infolist()

                # Guard 1: File count limit
                if len(infolist) > settings.ZIP_MAX_FILES:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail=f"Archive contains {len(infolist)} files, exceeding limit of {settings.ZIP_MAX_FILES}.",
                    )

                total_uncompressed = 0

                for info in infolist:
                    # Ignore directories
                    if info.is_dir():
                        continue

                    # Guard 2: Path Traversal (Zip Slip)
                    norm_name = os.path.normpath(info.filename)
                    if norm_name.startswith("..") or os.path.isabs(norm_name) or "/../" in info.filename:
                        raise HTTPException(
                            status_code=status.HTTP_400_BAD_REQUEST,
                            detail=f"Path traversal detected in archive entry: {info.filename}",
                        )

                    # Guard 3: Compression Ratio (Zip bomb defense)
                    if info.compress_size > 0:
                        ratio = info.file_size / info.compress_size
                        if ratio > settings.ZIP_MAX_COMPRESSION_RATIO:
                            raise HTTPException(
                                status_code=status.HTTP_400_BAD_REQUEST,
                                detail=f"Suspicious compression ratio ({ratio:.1f}) detected for {info.filename}.",
                            )

                    # Guard 4: Aggregate uncompressed size
                    total_uncompressed += info.file_size
                    if total_uncompressed > settings.ZIP_MAX_UNCOMPRESSED_BYTES:
                        raise HTTPException(
                            status_code=status.HTTP_400_BAD_REQUEST,
                            detail="Aggregate uncompressed archive size exceeds allowed threshold.",
                        )

                    file_data = zf.read(info)
                    base_filename = os.path.basename(norm_name)
                    if base_filename:
                        extracted_files.append((base_filename, file_data))

        except zipfile.BadZipFile:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid or corrupt ZIP archive.",
            )

        if not extracted_files:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="ZIP archive contains no readable files.",
            )

        return extracted_files


safe_archive_extractor = SafeArchiveExtractor()