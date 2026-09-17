from datetime import datetime, timezone
from ..domain.models import DocumentMetadata
from .confidence import ConfidenceScorer


class MetadataEnricher:
    def __init__(self, scorer: ConfidenceScorer | None = None):
        self.scorer = scorer or ConfidenceScorer()

    async def enrich(self, metadata: DocumentMetadata) -> DocumentMetadata:
        extraction_confidence = (
            sum(entity.confidence for entity in metadata.entities) / len(metadata.entities)
            if metadata.entities else 0.5
        )
        completeness = self.scorer.completeness(metadata)
        metadata.confidence_score = self.scorer.calculate(
            extraction_confidence=extraction_confidence,
            metadata_completeness=completeness,
            source_reliability=0.8,
        )
        metadata.processing_timestamp = datetime.now(timezone.utc)
        return metadata
