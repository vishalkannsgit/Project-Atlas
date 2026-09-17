import json
import logging
from typing import Optional, Dict, Any
from aiokafka import AIOKafkaProducer
from app.core.config import settings

logger = logging.getLogger("atlas.events")

class EventDispatcher:
    def __init__(self):
        self._producer: Optional[AIOKafkaProducer] = None

    async def get_producer(self) -> Optional[AIOKafkaProducer]:
        if not settings.KAFKA_ENABLED:
            return None
        if self._producer is None:
            self._producer = AIOKafkaProducer(
                bootstrap_servers=settings.KAFKA_BOOTSTRAP_SERVERS,
                value_serializer=lambda v: json.dumps(v).encode("utf-8")
            )
            await self._producer.start()
        return self._producer

    async def close(self):
        if self._producer:
            await self._producer.stop()
            self._producer = None

    async def emit_document_uploaded(
        self,
        document_id: str,
        tenant_id: str,
        storage_uri: str,
        sha256_hash: str,
        metadata_payload: Optional[Dict[str, Any]]
    ):
        event_payload = {
            "event_type": "DOCUMENT_UPLOADED",
            "document_id": document_id,
            "tenant_id": tenant_id,
            "storage_uri": storage_uri,
            "sha256_hash": sha256_hash,
            "metadata": metadata_payload or {}
        }

        if settings.KAFKA_ENABLED:
            try:
                producer = await self.get_producer()
                if producer:
                    await producer.send_and_wait(
                        settings.KAFKA_TOPIC_RAW_INGEST,
                        value=event_payload
                    )
                    logger.info("Published ingest event to Kafka topic '%s' for doc '%s'", settings.KAFKA_TOPIC_RAW_INGEST, document_id)
            except Exception as e:
                logger.error("Failed to publish event to Kafka: %s", e)
        else:
            logger.info("Kafka disabled. Local event dispatched: %s", event_payload)

event_dispatcher = EventDispatcher()