# Knowledge Graph Module — Project Atlas

Owner: Vishal Kanna B (`feature/knowledge-graph`)
Part of Epic 4 (Knowledge Engineering), Sprint 4.

## What this does

Takes extracted entities + relationships (from document-parsing /
metadata-knowledge / ai-retrieval-embeddings modules) and writes them
into a Neo4j knowledge graph. Exposes a query layer for the Search &
API module (Epic 5) to pull graph context alongside vector search.

Built and tested against **mock data** — real integration happens once
upstream modules (parsing, metadata, embeddings) are ready.

## Folder structure

```
knowledge-graph/
├── schema/
│   └── setup_schema.py      # Run ONCE - creates constraints + indexes
├── mock_data/
│   └── sample_entities.json # Fake extraction output to develop against
├── src/
│   ├── ingest.py             # Batched, fast ingestion (UNWIND + MERGE)
│   └── queries.py            # Query layer for retrieval/API use
├── tests/
│   └── test_ingest.py        # Tests against the ingested mock data
└── README.md
```

## Setup

1. Neo4j running locally via Docker:
   ```
   docker run -d --name neo4j-atlas -p 7474:7474 -p 7687:7687 -e NEO4J_AUTH=neo4j/password123 neo4j:latest
   ```
2. Update the password in `schema/setup_schema.py`, `src/ingest.py`,
   and `src/queries.py` to match what you set on first login at
   `localhost:7474`.
3. Install driver: `pip install neo4j`

## Run order

```bash
# 1. Create constraints/indexes (once)
python schema/setup_schema.py

# 2. Ingest mock data
python src/ingest.py mock_data/sample_entities.json

# 3. Try some queries
python src/queries.py

# 4. Run tests
pytest tests/test_ingest.py -v
```

## Why it's fast

- **Constraints create indexes** on every entity's `id` — MERGE becomes
  an index lookup instead of a full label scan.
- **Batched UNWIND writes** — one network round-trip per entity type
  or relationship type, not one per row. Ingesting 1,000 nodes this
  way is a single query, not 1,000 queries.
- **MERGE, not CREATE** — safe to re-run the same document without
  creating duplicates. Required for the "incremental updates without
  full reprocessing" non-functional requirement.

## Schema (current)

**Node labels:** Disease, Drug, Procedure, Symptom, Organization,
Specialty, Guideline, LabTest, Device, Document

**Relationship types used in mock data:** TREATS, CAUSES, DIAGNOSES,
MONITORS, PUBLISHES, RECOMMENDS, MANAGES, MENTIONED_IN

New relationship types can be added freely — `ingest.py` groups and
batches by whatever relationship types appear in the input JSON, no
code changes needed.

## Known gaps / next steps

- Real entity resolution (matching synonyms, not just exact `id`) —
  currently `id` is assumed unique per source; cross-source dedup
  (e.g., "T2DM" vs "Type 2 Diabetes" from two different documents)
  is not yet handled.
- No error/retry logic yet for failed writes (needed for Epic 6
  monitoring/audit).
- No pagination on `search_by_name` for large graphs.
- Integration point with document-parsing / metadata-knowledge /
  ai-retrieval-embeddings modules is not wired up — waiting on their
  output format.
