# Integration guide

## Document parsing -> metadata knowledge

Call `MetadataPipeline.process()` in-process when services share a Python runtime, or `POST /api/v1/metadata/process` when deployed independently.

Do not import implementations from sibling Atlas folders. Depend on the stable JSON/Pydantic contract instead.

## Metadata knowledge -> knowledge graph

Use `DocumentMetadata.entities` as the initial graph input. Each entity has a type, canonical candidate name and confidence. The graph service owns Neo4j labels, relationship modeling and Cypher.

## Metadata knowledge -> vector indexing

Use the metadata output as payload/filter metadata attached to chunks. The embedding service owns chunking/embeddings/Qdrant operations.

## Kafka

The event interface is deliberately small. A Kafka adapter should publish only after metadata validation/persistence succeeds and should include `document_id`, schema version and event timestamp. Event schema evolution should be backward compatible.
