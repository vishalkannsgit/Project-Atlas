from fastapi import APIRouter, Depends, UploadFile, File, Header, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import Optional

from app.core.database import get_db
from app.models.document import Document
from app.schemas.document import DocumentUploadResponse, DocumentStatusResponse
from app.services.storage import storage_service
from app.services.events import event_dispatcher
from app.services.metadata import metadata_extractor
from app.services.scanner import malware_scanner
from app.services.archive import safe_archive_extractor
from app.core.metrics import UPLOAD_COUNTER, UPLOAD_LATENCY_SECONDS

router = APIRouter(prefix="/documents", tags=["documents"])


@router.post(
    "/upload",
    response_model=DocumentUploadResponse,
    status_code=status.HTTP_201_CREATED,
)
async def upload_document(
    file: UploadFile = File(...),
    tenant_id: str = Header(..., alias="X-Tenant-ID"),
    idempotency_key: Optional[str] = Header(None, alias="X-Idempotency-Key"),
    db: AsyncSession = Depends(get_db),
):
    with UPLOAD_LATENCY_SECONDS.time():
        # Tier 1 Idempotency check: Client-provided Idempotency-Key
        if idempotency_key:
            stmt = select(Document).where(
                Document.tenant_id == tenant_id,
                Document.idempotency_key == idempotency_key,
            )
            result = await db.execute(stmt)
            existing_doc = result.scalar_one_or_none()
            if existing_doc:
                UPLOAD_COUNTER.labels(
                    status="idempotent_duplicate_key",
                    tenant=tenant_id,
                    format=existing_doc.file_format,
                ).inc()
                return DocumentUploadResponse(
                    document_id=existing_doc.id,
                    tenant_id=existing_doc.tenant_id,
                    filename=existing_doc.filename,
                    file_format=existing_doc.file_format,
                    mime_type=existing_doc.mime_type,
                    sha256_hash=existing_doc.sha256_hash,
                    file_size_bytes=existing_doc.file_size_bytes,
                    storage_uri=existing_doc.storage_uri,
                    status=existing_doc.status,
                    message="Document already processed (matched idempotency key).",
                )

        # Validate magic bytes, content type, enforce size limits, and calculate SHA-256
        sha256_hash, file_size, file_ext, content_type = (
            await storage_service.validate_and_hash(file)
        )
        format_label = file_ext.lstrip(".")

        # Tier 2 Idempotency check: Content SHA-256 collision within tenant scope
        stmt = select(Document).where(
            Document.tenant_id == tenant_id,
            Document.sha256_hash == sha256_hash,
        )
        result = await db.execute(stmt)
        existing_hash_doc = result.scalar_one_or_none()
        if existing_hash_doc:
            UPLOAD_COUNTER.labels(
                status="idempotent_duplicate_hash",
                tenant=tenant_id,
                format=format_label,
            ).inc()
            return DocumentUploadResponse(
                document_id=existing_hash_doc.id,
                tenant_id=existing_hash_doc.tenant_id,
                filename=existing_hash_doc.filename,
                file_format=existing_hash_doc.file_format,
                mime_type=existing_hash_doc.mime_type,
                sha256_hash=existing_hash_doc.sha256_hash,
                file_size_bytes=existing_hash_doc.file_size_bytes,
                storage_uri=existing_hash_doc.storage_uri,
                status=existing_hash_doc.status,
                message="Document content identical to an existing document for this tenant.",
            )

        # In-memory buffer read for security inspection
        file_bytes = await file.read()
        await file.seek(0)

        # Security Scan: Inspect for malware/EICAR signatures
        is_clean, threat_name = await malware_scanner.scan_bytes(file_bytes)
        if not is_clean:
            UPLOAD_COUNTER.labels(
                status="quarantined",
                tenant=tenant_id,
                format=format_label,
            ).inc()
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=f"Security quarantine: file contains threat signature '{threat_name}'.",
            )

        # Process metadata based on format type
        archive_manifest = []
        if format_label == "zip":
            unpacked_files = safe_archive_extractor.extract_zip(file_bytes)
            for sub_name, sub_bytes in unpacked_files:
                # Run scanner on each unpacked item
                sub_clean, sub_threat = await malware_scanner.scan_bytes(sub_bytes)
                if not sub_clean:
                    UPLOAD_COUNTER.labels(
                        status="quarantined",
                        tenant=tenant_id,
                        format="zip",
                    ).inc()
                    raise HTTPException(
                        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                        detail=f"Security quarantine: archive entry '{sub_name}' contains threat '{sub_threat}'.",
                    )
                archive_manifest.append({
                    "filename": sub_name,
                    "size_bytes": len(sub_bytes),
                })
            extracted_meta = {
                "total_unpacked_files": len(unpacked_files),
                "entries": archive_manifest,
            }
        else:
            extracted_meta = metadata_extractor.extract(format_label, file_bytes)

        metadata_dict = {
            "original_extension": file_ext,
            "filename": file.filename or f"upload{file_ext}",
            "file_format": format_label,
            "mime_type": content_type,
            "extracted_properties": extracted_meta,
            "scan_status": "CLEAN",
        }

        # Save to configured storage backend (local disk or S3/MinIO)
        storage_uri = await storage_service.save_file(
            file=file,
            tenant_id=tenant_id,
            sha256_hash=sha256_hash,
            file_ext=file_ext,
            content_type=content_type,
        )

        # Persist document metadata record in database
        doc = Document(
            tenant_id=tenant_id,
            idempotency_key=idempotency_key,
            filename=file.filename or f"upload{file_ext}",
            sha256_hash=sha256_hash,
            file_size_bytes=file_size,
            file_format=format_label,
            mime_type=content_type,
            storage_uri=storage_uri,
            status="UPLOADED",
            metadata_json=metadata_dict,
        )
        db.add(doc)
        await db.commit()
        await db.refresh(doc)

        # Dispatch event using original event dispatcher
        await event_dispatcher.emit_document_uploaded(
            document_id=doc.id,
            tenant_id=doc.tenant_id,
            storage_uri=doc.storage_uri,
            sha256_hash=doc.sha256_hash,
            metadata_payload=metadata_dict,
        )

        UPLOAD_COUNTER.labels(
            status="success",
            tenant=tenant_id,
            format=format_label,
        ).inc()

        return DocumentUploadResponse(
            document_id=doc.id,
            tenant_id=doc.tenant_id,
            filename=doc.filename,
            file_format=doc.file_format,
            mime_type=doc.mime_type,
            sha256_hash=doc.sha256_hash,
            file_size_bytes=doc.file_size_bytes,
            storage_uri=doc.storage_uri,
            status=doc.status,
            message="Document uploaded and onboarded successfully.",
        )


@router.get("/{document_id}", response_model=DocumentStatusResponse)
async def get_document_status(
    document_id: str,
    tenant_id: str = Header(..., alias="X-Tenant-ID"),
    db: AsyncSession = Depends(get_db),
):
    stmt = select(Document).where(
        Document.id == document_id,
        Document.tenant_id == tenant_id,
    )
    result = await db.execute(stmt)
    doc = result.scalar_one_or_none()

    if not doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found for the specified tenant.",
        )

    return doc