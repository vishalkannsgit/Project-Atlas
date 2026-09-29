"""
core/models.py

Defines the NORMALIZED data shapes that every connector must produce.
No connector (PubMed, NIH, RSS) is allowed to send data to Atlas in its own
"native" shape — everything is converted into these shared models first.

Why Pydantic:
- Atlas's backend is FastAPI, which uses Pydantic natively -> zero friction
  when this data is later validated on Atlas's side.
- Pydantic auto-validates types and required fields at creation time, so a
  connector bug (e.g. missing a required field) fails LOUD and EARLY,
  inside your own connector -- not silently inside Atlas's pipeline.
"""

from datetime import datetime
from enum import Enum
from typing import Any, Optional
from pydantic import BaseModel, Field


class SourceType(str, Enum):
    """Which kind of connector produced this record."""
    PUBMED = "pubmed"
    NIH = "nih"
    RSS = "rss"


class NormalizedRecord(BaseModel):
    """
    The ONE shape every connector must output, regardless of source.
    Atlas's ingestion API only ever sees this shape -- it never needs to know
    that PubMed's raw data was XML or that RSS's raw data was a feed entry.
    """
    source: SourceType
    record_id: str = Field(..., description="Unique ID within the source, e.g. PubMed's PMID")
    fetched_at: datetime = Field(default_factory=datetime.utcnow)
    title: Optional[str] = None
    url: Optional[str] = None
    published_at: Optional[datetime] = None
    payload: dict[str, Any] = Field(..., description="Raw/source-specific data, kept as-is for downstream parsing")
    checkpoint_marker: str = Field(..., description="Value used to resume sync from this point next time")


class ConnectorRunStatus(str, Enum):
    SUCCESS = "success"
    PARTIAL = "partial"
    FAILED = "failed"


class ConnectorError(BaseModel):
    error_type: str  # e.g. "rate_limit", "timeout", "parse_error", "auth_error"
    message: str
    occurred_at: datetime = Field(default_factory=datetime.utcnow)


class ConnectorRunResult(BaseModel):
    """
    Returned after every connector run. This is what gets logged, and what
    feeds the health check status.
    """
    source: SourceType
    status: ConnectorRunStatus
    records_fetched: int = 0
    records_sent_to_atlas: int = 0
    errors: list[ConnectorError] = Field(default_factory=list)
    next_checkpoint: Optional[str] = None
    started_at: datetime
    finished_at: datetime


class HealthStatus(str, Enum):
    OK = "ok"
    DEGRADED = "degraded"
    DOWN = "down"


class ConnectorHealth(BaseModel):
    """Returned by every connector's health_check() method."""
    source: SourceType
    status: HealthStatus
    last_success_at: Optional[datetime] = None
    last_error: Optional[str] = None
