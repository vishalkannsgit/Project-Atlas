import uuid
import json
import time
from typing import Optional
from fastapi import APIRouter, UploadFile, File, Form, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.database import get_db
from app.models.document import Document, DocumentStatus
from app.schemas.document import DocumentUploadResponse, DocumentStatusResponse
from app.services.storage import storage_service
from app.services.events import event_dispatcher
from app.core.metrics import UPLOAD_COUNT, UPLOAD_LATENCY

router = APIRouter(prefix="/onboarding/documents", tags=["Manual Onboarding"])

@router.post("/upload", response_model=DocumentUploadResponse, status_code=status.HTTP_202_ACCEPTED)
async def upload_pdf(
    file: UploadFile = File(..., description="PDF file to ingest"),
    tenant_id: str = Form(..., description="Tenant / Organization ID"),
    idempotency_key: Optional[str] = Form(None, description="Optional client idempotency key"),
    metadata: Optional[str] = Form(None, description="JSON-serialized domain-agnostic metadata"),
    db: AsyncSession = Depends(get_db)
):
    start_time = time.time()

    # Parse optional domain-agnostic metadata if provided
    metadata_payload = None
    if metadata and metadata.strip():
        try:
            metadata_payload = json.loads(metadata.strip())
        except json.JSONDecodeError:
            UPLOAD_COUNT.labels(tenant_id=tenant_id, status="failed_invalid_json").inc()
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid metadata format: Must be valid JSON string."
            )

    # Validate PDF signature and stream hash
    try:
        sha256_hash, file_size, _ = await storage_service.validate_and_hash(file)
    except HTTPException:
        UPLOAD_COUNT.labels(tenant_id=tenant_id, status="failed_validation").inc()
        raise

    # 1. Idempotency Check: By idempotency_key (if provided)
    if idempotency_key:
        query_idem = select(Document).where(
            Document.tenant_id == tenant_id,
            Document.idempotency_key == idempotency_key
        )
        result = await db.execute(query_idem)
        existing_doc = result.scalar_one_or_none()
        if existing_doc:
            UPLOAD_COUNT.labels(tenant_id=tenant_id, status="duplicate_key").inc()
            return DocumentUploadResponse(
                document_id=existing_doc.id,
                tenant_id=existing_doc.tenant_id,
                original_filename=existing_doc.original_filename,
                file_size_bytes=existing_doc.file_size_bytes,
                sha256_hash=existing_doc.sha256_hash,
                status=existing_doc.status,
                message="Duplicate upload detected by idempotency key; returning existing document.",
                is_duplicate=True
            )

    # 2. Content Duplicate Check: By SHA-256 within the same tenant
    query_hash = select(Document).where(
        Document.tenant_id == tenant_id,
        Document.sha256_hash == sha256_hash
    )
    result = await db.execute(query_hash)
    existing_hash_doc = result.scalar_one_or_none()
    if existing_hash_doc:
        UPLOAD_COUNT.labels(tenant_id=tenant_id, status="duplicate_hash").inc()
        return DocumentUploadResponse(
            document_id=existing_hash_doc.id,
            tenant_id=existing_hash_doc.tenant_id,
            original_filename=existing_hash_doc.original_filename,
            file_size_bytes=existing_hash_doc.file_size_bytes,
            sha256_hash=existing_hash_doc.sha256_hash,
            status=existing_hash_doc.status,
            message="Identical document content previously ingested; skipping reprocessing.",
            is_duplicate=True
        )

    # 3. Persist file bytes to storage
    storage_uri = await storage_service.save_file(file, tenant_id, sha256_hash)

    # 4. Create document record in database
    document_id = str(uuid.uuid4())
    new_document = Document(
        id=document_id,
        tenant_id=tenant_id,
        idempotency_key=idempotency_key,
        original_filename=file.filename or "unknown.pdf",
        file_size_bytes=file_size,
        sha256_hash=sha256_hash,
        mime_type="application/pdf",
        storage_uri=storage_uri,
        status=DocumentStatus.QUEUED,
        metadata_payload=metadata_payload
    )

    db.add(new_document)
    await db.commit()
    await db.refresh(new_document)

    # 5. Emit event to hand off to Project Atlas ingestion queue
    await event_dispatcher.emit_document_uploaded(
        document_id=document_id,
        tenant_id=tenant_id,
        storage_uri=storage_uri,
        sha256_hash=sha256_hash,
        metadata_payload=metadata_payload
    )

    # Record metrics
    UPLOAD_COUNT.labels(tenant_id=tenant_id, status="success").inc()
    UPLOAD_LATENCY.observe(time.time() - start_time)

    return DocumentUploadResponse(
        document_id=document_id,
        tenant_id=tenant_id,
        original_filename=new_document.original_filename,
        file_size_bytes=file_size,
        sha256_hash=sha256_hash,
        status=DocumentStatus.QUEUED,
        message="Document successfully uploaded and queued for Project Atlas pipeline.",
        is_duplicate=False
    )

@router.get("/{document_id}/status", response_model=DocumentStatusResponse)
async def get_document_status(
    document_id: str,
    db: AsyncSession = Depends(get_db)
):
    query = select(Document).where(Document.id == document_id)
    result = await db.execute(query)
    doc = result.scalar_one_or_none()

    if not doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Document with ID '{document_id}' not found."
        )

    return doc