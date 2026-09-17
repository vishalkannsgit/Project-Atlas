from abc import ABC, abstractmethod
from ..domain.models import ParsedDocument


class MetadataExtractor(ABC):
    @abstractmethod
    async def extract(self, document: ParsedDocument) -> dict:
        """Return fields accepted by DocumentMetadata."""
