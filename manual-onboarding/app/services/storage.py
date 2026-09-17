import os
import hashlib
from typing import Tuple
from fastapi import UploadFile, HTTPException, status
import aioboto3
from app.core.config import settings

class StorageService:
    def __init__(self):
        self.session = aioboto3.Session()

    async def validate_and_hash(self, file: UploadFile) -> Tuple[str, int, bytes]:
        """
        Validates the PDF magic byte signature, enforces size limits,
        and streams content to generate an immutable SHA-256 digest.
        """
        hasher = hashlib.sha256()
        total_size = 0
        first_chunk = True
        header_bytes = b""

        while True:
            chunk = await file.read(64 * 1024)
            if not chunk:
                break
            
            if first_chunk:
                header_bytes = chunk[:5]
                if not header_bytes.startswith(b"%PDF-"):
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail="Invalid file format: Document must be a valid PDF with '%PDF-' magic bytes."
                    )
                first_chunk = False

            total_size += len(chunk)
            if total_size > settings.MAX_FILE_SIZE_BYTES:
                raise HTTPException(
                    status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                    detail=f"File exceeds maximum allowed size of {settings.MAX_FILE_SIZE_BYTES / (1024 * 1024)} MB."
                )

            hasher.update(chunk)

        await file.seek(0)
        return hasher.hexdigest(), total_size, header_bytes

    async def save_file(self, file: UploadFile, tenant_id: str, sha256_hash: str) -> str:
        """
        Persists the file to the configured storage backend (Local Disk or S3/MinIO).
        """
        if settings.STORAGE_BACKEND.lower() == "s3":
            return await self._save_to_s3(file, tenant_id, sha256_hash)
        return await self._save_to_local(file, tenant_id, sha256_hash)

    async def _save_to_local(self, file: UploadFile, tenant_id: str, sha256_hash: str) -> str:
        tenant_dir = os.path.join(settings.LOCAL_STORAGE_DIR, tenant_id)
        os.makedirs(tenant_dir, exist_ok=True)
        file_path = os.path.join(tenant_dir, f"{sha256_hash}.pdf")

        with open(file_path, "wb") as f:
            while True:
                chunk = await file.read(64 * 1024)
                if not chunk:
                    break
                f.write(chunk)

        await file.seek(0)
        return f"file://{os.path.abspath(file_path)}"

    async def _save_to_s3(self, file: UploadFile, tenant_id: str, sha256_hash: str) -> str:
        s3_key = f"{tenant_id}/{sha256_hash}.pdf"
        async with self.session.client(
            "s3",
            endpoint_url=settings.S3_ENDPOINT_URL,
            aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
            aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
            region_name=settings.AWS_REGION
        ) as s3_client:
            await s3_client.upload_fileobj(
                file.file,
                settings.S3_BUCKET_NAME,
                s3_key,
                ExtraArgs={"ContentType": "application/pdf"}
            )

        await file.seek(0)
        return f"s3://{settings.S3_BUCKET_NAME}/{s3_key}"

storage_service = StorageService()