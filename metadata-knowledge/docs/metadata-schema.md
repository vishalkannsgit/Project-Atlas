# Metadata schema

`DocumentMetadata` is the canonical output model for this component.

| Field | Type | Purpose |
|---|---|---|
| schema_version | string | Contract version for integration compatibility |
| document_id | string | Stable document identifier from ingestion |
| source | string | Source system/dataset |
| title | string/null | Document title |
| publisher | string/null | Publisher/organization |
| publication_date | datetime/null | Publication date |
| version | string/null | Source version |
| language | string/null | Language code/name |
| specialty | string[] | Medical/domain specialties |
| keywords | string[] | Normalized keywords |
| document_type | enum | Research article, guideline, SOP, advisory, report, web page, unknown |
| authors | string[] | Document authors |
| license | string/null | Usage/license information |
| confidence_score | float | Overall enrichment confidence, 0..1 |
| processing_timestamp | datetime | Processing time |
| entities | Entity[] | Extracted semantic entities |

Entity records contain `name`, `normalized_name`, `entity_type`, `confidence`, and optional character offsets.
