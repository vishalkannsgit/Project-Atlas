class MetadataKnowledgeError(Exception):
    """Base exception for this component."""


class MetadataValidationError(MetadataKnowledgeError):
    """Raised when metadata cannot satisfy the canonical contract."""
