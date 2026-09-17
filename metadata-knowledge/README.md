# Atlas Metadata Knowledge

Standalone Project Atlas component for **metadata extraction, normalization, entity extraction, enrichment, validation and persistence contracts**.

## Responsibility boundary

This component owns the transformation:

`ParsedDocument -> DocumentMetadata + Entities`

It intentionally does **not** own crawling, document parsing, embeddings, Neo4j, Qdrant, Temporal, Kafka infrastructure, or UI. Those systems can integrate through the contracts in `domain/`, `repositories/`, and `events/`.

## Quick start

```bash
cd metadata-knowledge
python -m venv .venv
# Windows: .venv\\Scripts\\activate
# Linux/macOS: source .venv/bin/activate
pip install -e ".[test]"
pytest
uvicorn metadata_knowledge.api.app:app --reload
```

Health check: `GET /health`

Process a parsed document: `POST /api/v1/metadata/process`

## Integration contract

The document-parsing component sends a `ParsedDocument` containing at minimum:

- `document_id`
- `source`
- `text`
- `file_type`

Optional source metadata includes title, publisher, publication date, language, authors, version and license.

The output is `DocumentMetadata`. It contains the project proposal fields plus normalized semantic entities and confidence scores.

Example request:

```json
{
  "document_id": "PMC123456",
  "source": "pubmed_central",
  "title": "Type 2 Diabetes Guideline",
  "text": "Clinical guideline about Type 2 diabetes and insulin. HbA1c is monitored.",
  "file_type": "xml",
  "language": "en",
  "publisher": "NIH"
}
```

## Replacing the baseline extractor

`MetadataExtractor` and `EntityExtractor` are interfaces. A future LLM adapter can implement them without changing `MetadataPipeline`:

```python
class LLMMetadataExtractor(MetadataExtractor):
    async def extract(self, document: ParsedDocument) -> dict:
        ...

class LLMEntityExtractor(EntityExtractor):
    async def extract(self, document: ParsedDocument) -> list[Entity]:
        ...
```

This is the intended integration point for LiteLLM/Instructor.

## Persistence

`MetadataRepository` is the persistence boundary. `InMemoryMetadataRepository` is provided for tests/local development. A PostgreSQL adapter can implement the same interface without changing extraction or pipeline code.

## Events

`MetadataEventPublisher` is the event boundary. `NoOpEventPublisher` is the local default. A Kafka implementation can publish a `metadata.processed` event after successful processing.

## Entity types

The initial contract supports:

`DISEASE`, `DRUG`, `PROCEDURE`, `SYMPTOM`, `ORGANIZATION`, `SPECIALTY`, `GUIDELINE`, `LAB_TEST`, `MEDICAL_DEVICE`.

The included rule-based extractor is intentionally conservative and is a development baseline, not a medical NLP system. Production entity extraction should use the project's selected LLM/NLP adapter and validation/evaluation process.
