from pydantic import BaseModel, ConfigDict
from typing import Optional, Any, Dict, List
from datetime import datetime


class DocumentUploadResponse(BaseModel):
    document_id: str
    tenant_id: str
    filename: str
    file_format: str
    mime_type: str
    sha256_hash: str
    file_size_bytes: int
    storage_uri: str
    status: str
    message: str
    extracted_documents: Optional[List["DocumentUploadResponse"]] = None

    model_config = ConfigDict(from_attributes=True)


class DocumentStatusResponse(BaseModel):
    id: str
    tenant_id: str
    filename: str
    file_format: str
    mime_type: str
    sha256_hash: str
    file_size_bytes: int
    storage_uri: str
    status: str
    metadata_json: Optional[Dict[str, Any]] = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)