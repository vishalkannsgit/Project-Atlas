from pydantic import BaseModel, Field, ConfigDict
from typing import Optional, Any, Dict
from datetime import datetime
from app.models.document import DocumentStatus

class DocumentUploadResponse(BaseModel):
    """Response returned immediately upon accepting the file."""
    document_id: str = Field(..., description="Unique tracking identifier for the document")
    tenant_id: str = Field(..., description="Tenant workspace identifier")
    original_filename: str = Field(..., description="Original filename uploaded")
    file_size_bytes: int = Field(..., description="Size of file in bytes")
    sha256_hash: str = Field(..., description="SHA-256 digest of the file contents")
    status: DocumentStatus = Field(..., description="Current processing state")
    message: str = Field(default="Document uploaded and queued for processing")
    is_duplicate: bool = Field(default=False, description="True if identical file was previously uploaded")

class DocumentStatusResponse(BaseModel):
    """Detailed response for status polling."""
    model_config = ConfigDict(from_attributes=True)

    document_id: str = Field(..., alias="id")
    tenant_id: str
    original_filename: str
    file_size_bytes: int
    sha256_hash: str
    status: DocumentStatus
    storage_uri: str
    metadata_payload: Optional[Dict[str, Any]] = None
    error_message: Optional[str] = None
    created_at: datetime
    updated_at: datetime