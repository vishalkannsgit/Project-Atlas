import enum
from datetime import datetime, timezone
from sqlalchemy import Column, String, Integer, DateTime, Enum, JSON
from app.core.database import Base

class DocumentStatus(str, enum.Enum):
    QUEUED = "QUEUED"
    PROCESSING = "PROCESSING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"

class Document(Base):
    __tablename__ = "documents"

    # Primary identifier (UUID)
    id = Column(String(36), primary_key=True, index=True)
    
    # Multi-tenancy and tracking
    tenant_id = Column(String(64), nullable=False, index=True)
    idempotency_key = Column(String(64), nullable=True, index=True)
    
    # File specifications
    original_filename = Column(String(255), nullable=False)
    file_size_bytes = Column(Integer, nullable=False)
    sha256_hash = Column(String(64), nullable=False, index=True)
    mime_type = Column(String(64), nullable=False, default="application/pdf")
    
    # Storage URI (e.g., s3://bucket/path.pdf or file:///local/path.pdf)
    storage_uri = Column(String(512), nullable=False)
    
    # Processing status and domain-agnostic metadata
    status = Column(Enum(DocumentStatus), default=DocumentStatus.QUEUED, nullable=False)
    metadata_payload = Column(JSON, nullable=True)
    error_message = Column(String(1024), nullable=True)
    
    # Timestamps
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False)