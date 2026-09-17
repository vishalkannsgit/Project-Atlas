from abc import ABC, abstractmethod
from ..domain.models import DocumentMetadata


class MetadataRepository(ABC):
    @abstractmethod
    async def save(self, metadata: DocumentMetadata) -> None: ...

    @abstractmethod
    async def get(self, document_id: str) -> DocumentMetadata | None: ...


class InMemoryMetadataRepository(MetadataRepository):
    """Useful for tests and local development; no external infrastructure required."""
    def __init__(self):
        self._items: dict[str, DocumentMetadata] = {}

    async def save(self, metadata: DocumentMetadata) -> None:
        self._items[metadata.document_id] = metadata

    async def get(self, document_id: str) -> DocumentMetadata | None:
        return self._items.get(document_id)
