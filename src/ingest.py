"""
Ingestion engine for Project Atlas Knowledge Graph.

SPEED DESIGN:
- Uses UNWIND to batch-write all nodes of a type in ONE query,
  instead of one query per node (this is 10-100x faster at scale).
- Uses MERGE on the unique `id` (backed by the constraint from
  setup_schema.py) so re-ingesting the same document never creates
  duplicates - it just updates properties.
- Relationships are also batched the same way.
- One driver/session per ingest run, not per node.

Usage:
    python ingest.py mock_data/sample_entities.json
"""

import os
import sys
import json
import time
from neo4j import GraphDatabase

URI = os.getenv("NEO4J_URI", "bolt://localhost:7687")
AUTH = (os.getenv("NEO4J_USER", "neo4j"), os.getenv("NEO4J_PASSWORD", "your_new_password"))

# Maps JSON entity keys -> Neo4j node label
ENTITY_LABEL_MAP = {
    "diseases": "Disease",
    "drugs": "Drug",
    "procedures": "Procedure",
    "symptoms": "Symptom",
    "organizations": "Organization",
    "specialties": "Specialty",
    "guidelines": "Guideline",
    "lab_tests": "LabTest",
    "devices": "Device",
}

# One generic batched MERGE query, parameterized by label.
# Label can't be parameterized directly in Cypher, so we build
# the query string per label (safe here since labels come from
# our fixed map above, never from raw user input).
def batch_merge_nodes_query(label: str) -> str:
    return f"""
    UNWIND $rows AS row
    MERGE (n:{label} {{id: row.id}})
    SET n.name = row.name,
        n.synonyms = row.synonyms,
        n.updated_at = datetime()
    """

BATCH_MERGE_DOCUMENT = """
UNWIND $rows AS row
MERGE (d:Document {id: row.id})
SET d.source = row.source,
    d.title = row.title,
    d.publication_date = row.publication_date,
    d.publisher = row.publisher,
    d.document_type = row.document_type,
    d.language = row.language,
    d.confidence_score = row.confidence_score,
    d.updated_at = datetime()
"""

# Relationships: grouped by (from_label, type, to_label) so each
# distinct combination is still just one UNWIND query.
BATCH_MERGE_RELATIONSHIP = """
UNWIND $rows AS row
MATCH (a {{id: row.from}})
MATCH (b {{id: row.to}})
MERGE (a)-[r:{rel_type}]->(b)
SET r.updated_at = datetime()
"""


def ingest(json_path: str):
    start = time.time()

    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    driver = GraphDatabase.driver(URI, auth=AUTH)

    with driver.session() as session:
        # 1. Document node
        session.run(BATCH_MERGE_DOCUMENT, rows=[data["document"]])
        print(f"Ingested 1 document")

        # 2. All entity types, one batched query per type
        total_entities = 0
        for key, label in ENTITY_LABEL_MAP.items():
            rows = data["entities"].get(key, [])
            if not rows:
                continue
            session.run(batch_merge_nodes_query(label), rows=rows)
            print(f"Ingested {len(rows)} {label} node(s)")
            total_entities += len(rows)

        # 3. Relationships, grouped by type so each group is one query
        rel_groups = {}
        for rel in data.get("relationships", []):
            rel_groups.setdefault(rel["type"], []).append(
                {"from": rel["from"], "to": rel["to"]}
            )

        total_rels = 0
        for rel_type, rows in rel_groups.items():
            query = BATCH_MERGE_RELATIONSHIP.format(rel_type=rel_type)
            session.run(query, rows=rows)
            print(f"Ingested {len(rows)} [{rel_type}] relationship(s)")
            total_rels += len(rows)

    driver.close()

    elapsed = time.time() - start
    print(f"\nDone. {total_entities} entities, {total_rels} relationships "
          f"in {elapsed:.3f}s")


if __name__ == "__main__":
    path = sys.argv[1] if len(sys.argv) > 1 else "mock_data/sample_entities.json"
    ingest(path)
