import os
import hashlib
from typing import Tuple
from fastapi import UploadFile, HTTPException, status
import aioboto3
from app.core.config import settings

# Mapping extensions to content types and expected container signatures
ALLOWED_EXTENSIONS = {
    ".pdf": "application/pdf",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ".zip": "application/zip",
}


class StorageService:
    def __init__(self):
        self.session = aioboto3.Session()

    def _validate_magic_bytes(self, chunk: bytes, filename: str) -> Tuple[str, str]:
        """
        Validates magic byte signatures against the file extension.
        Returns a tuple of (extension, content_type).
        """
        ext = ("." + filename.rsplit(".", 1)[-1].lower()) if "." in filename else ""
        if ext not in ALLOWED_EXTENSIONS:
            allowed = ", ".join(ALLOWED_EXTENSIONS.keys())
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Unsupported file format '{ext}'. Allowed extensions: {allowed}",
            )

        # PDF validation
        if ext == ".pdf":
            if not chunk.startswith(b"%PDF-"):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Invalid file signature: Content does not match a valid PDF.",
                )
        # Office formats (DOCX, PPTX, XLSX) are ZIP-based containers
        elif ext in [".docx", ".pptx", ".xlsx", ".zip"]:
            if not chunk.startswith(b"PK\x03\x04"):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Invalid file signature: Content does not match a valid {ext.upper()} archive.",
                )

        return ext, ALLOWED_EXTENSIONS[ext]

    async def validate_and_hash(self, file: UploadFile) -> Tuple[str, int, str, str]:
        """
        Validates the magic byte signature, enforces size limits,
        and streams content to generate an immutable SHA-256 digest.
        Returns: (sha256_hash, total_size, file_extension, content_type)
        """
        hasher = hashlib.sha256()
        total_size = 0
        first_chunk = True
        file_ext = ""
        content_type = ""

        filename = file.filename or ""

        while True:
            chunk = await file.read(64 * 1024)
            if not chunk:
                break

            if first_chunk:
                file_ext, content_type = self._validate_magic_bytes(chunk, filename)
                first_chunk = False

            total_size += len(chunk)
            if total_size > settings.MAX_FILE_SIZE_BYTES:
                raise HTTPException(
                    status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                    detail=f"File exceeds maximum allowed size of {settings.MAX_FILE_SIZE_BYTES / (1024 * 1024)} MB.",
                )

            hasher.update(chunk)

        if total_size == 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Empty file uploaded.",
            )

        await file.seek(0)
        return hasher.hexdigest(), total_size, file_ext, content_type

    async def save_file(
        self,
        file: UploadFile,
        tenant_id: str,
        sha256_hash: str,
        file_ext: str,
        content_type: str,
    ) -> str:
        """
        Persists the file to the configured storage backend (Local Disk or S3/MinIO)
        using the proper extension and MIME content type.
        """
        if settings.STORAGE_BACKEND.lower() == "s3":
            return await self._save_to_s3(
                file, tenant_id, sha256_hash, file_ext, content_type
            )
        return await self._save_to_local(file, tenant_id, sha256_hash, file_ext)

    async def _save_to_local(
        self, file: UploadFile, tenant_id: str, sha256_hash: str, file_ext: str
    ) -> str:
        tenant_dir = os.path.join(settings.LOCAL_STORAGE_DIR, tenant_id)
        os.makedirs(tenant_dir, exist_ok=True)
        file_path = os.path.join(tenant_dir, f"{sha256_hash}{file_ext}")

        with open(file_path, "wb") as f:
            while True:
                chunk = await file.read(64 * 1024)
                if not chunk:
                    break
                f.write(chunk)

        await file.seek(0)
        return f"file://{os.path.abspath(file_path)}"

    async def _save_to_s3(
        self,
        file: UploadFile,
        tenant_id: str,
        sha256_hash: str,
        file_ext: str,
        content_type: str,
    ) -> str:
        s3_key = f"{tenant_id}/{sha256_hash}{file_ext}"
        async with self.session.client(
            "s3",
            endpoint_url=settings.S3_ENDPOINT_URL,
            aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
            aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
            region_name=settings.AWS_REGION,
        ) as s3_client:
            await s3_client.upload_fileobj(
                file.file,
                settings.S3_BUCKET_NAME,
                s3_key,
                ExtraArgs={"ContentType": content_type},
            )

        await file.seek(0)
        return f"s3://{settings.S3_BUCKET_NAME}/{s3_key}"


storage_service = StorageService()