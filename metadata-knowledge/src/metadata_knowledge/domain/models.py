from datetime import datetime, timezone
from pydantic import BaseModel, ConfigDict, Field, field_validator
from .enums import DocumentType, EntityType


class ParsedDocument(BaseModel):
    """Stable input contract produced by document-parsing/ingestion services."""
    model_config = ConfigDict(extra="ignore")

    document_id: str = Field(min_length=1)
    source: str = Field(min_length=1)
    title: str | None = None
    text: str = Field(min_length=1)
    file_type: str = Field(min_length=1)
    published_at: datetime | None = None
    language: str | None = None
    publisher: str | None = None
    authors: list[str] = Field(default_factory=list)
    version: str | None = None
    license: str | None = None


class Entity(BaseModel):
    name: str = Field(min_length=1)
    entity_type: EntityType
    confidence: float = Field(ge=0, le=1)
    normalized_name: str | None = None
    start: int | None = Field(default=None, ge=0)
    end: int | None = Field(default=None, ge=0)
    source: str = "metadata-knowledge"

    @field_validator("name")
    @classmethod
    def strip_name(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("entity name cannot be empty")
        return value


class DocumentMetadata(BaseModel):
    """Canonical metadata contract consumed by graph/vector/API components."""
    model_config = ConfigDict(extra="ignore")

    schema_version: str = "1.0"
    document_id: str
    source: str
    title: str | None = None
    publisher: str | None = None
    publication_date: datetime | None = None
    version: str | None = None
    language: str | None = None
    specialty: list[str] = Field(default_factory=list)
    keywords: list[str] = Field(default_factory=list)
    document_type: DocumentType = DocumentType.UNKNOWN
    authors: list[str] = Field(default_factory=list)
    license: str | None = None
    confidence_score: float = Field(default=0, ge=0, le=1)
    processing_timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    entities: list[Entity] = Field(default_factory=list)
