from abc import ABC, abstractmethod
from ..domain.models import DocumentMetadata


class MetadataEventPublisher(ABC):
    @abstractmethod
    async def publish_processed(self, metadata: DocumentMetadata) -> None: ...


class NoOpEventPublisher(MetadataEventPublisher):
    """Default publisher. A Kafka adapter can implement the same contract later."""
    async def publish_processed(self, metadata: DocumentMetadata) -> None:
        return None
