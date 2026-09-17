from ..domain.models import DocumentMetadata
from ..domain.exceptions import MetadataValidationError


class MetadataValidator:
    def validate(self, metadata: DocumentMetadata) -> DocumentMetadata:
        if not metadata.document_id.strip():
            raise MetadataValidationError("document_id is required")
        if not metadata.source.strip():
            raise MetadataValidationError("source is required")
        if metadata.confidence_score < 0 or metadata.confidence_score > 1:
            raise MetadataValidationError("confidence_score must be between 0 and 1")
        return metadata
