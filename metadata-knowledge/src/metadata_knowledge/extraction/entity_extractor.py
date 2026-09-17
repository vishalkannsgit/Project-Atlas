from abc import ABC, abstractmethod
from ..domain.models import Entity, ParsedDocument


class EntityExtractor(ABC):
    @abstractmethod
    async def extract(self, document: ParsedDocument) -> list[Entity]:
        """Extract semantic entities from a parsed document."""
