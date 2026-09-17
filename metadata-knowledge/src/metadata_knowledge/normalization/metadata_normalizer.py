from abc import ABC, abstractmethod
from ..domain.models import DocumentMetadata


class MetadataNormalizer(ABC):
    @abstractmethod
    async def normalize(self, metadata: DocumentMetadata) -> DocumentMetadata:
        """Return canonicalized metadata."""


class DefaultMetadataNormalizer(MetadataNormalizer):
    async def normalize(self, metadata: DocumentMetadata) -> DocumentMetadata:
        metadata.keywords = self._unique(metadata.keywords, lower=False)
        metadata.specialty = self._unique(metadata.specialty, lower=False)
        metadata.authors = self._unique(metadata.authors, lower=False)
        for entity in metadata.entities:
            entity.name = " ".join(entity.name.split())
            entity.normalized_name = entity.normalized_name or entity.name.casefold()
        return metadata

    @staticmethod
    def _unique(values: list[str], lower: bool) -> list[str]:
        seen: set[str] = set()
        result: list[str] = []
        for value in values:
            value = " ".join(value.split())
            key = value.casefold() if lower else value.casefold()
            if value and key not in seen:
                seen.add(key)
                result.append(value.lower() if lower else value)
        return result
