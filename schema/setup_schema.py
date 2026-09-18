"""
Schema setup for Project Atlas Knowledge Graph.
Run this ONCE before ingesting any data.

Why this matters for speed:
Without constraints, every MERGE does a full label scan to check
for duplicates. With a uniqueness constraint, Neo4j uses an index
lookup instead - this is the difference between O(n) and O(log n)
per write, which matters a lot once you're past a few thousand nodes.
"""

import os
from neo4j import GraphDatabase

URI = os.getenv("NEO4J_URI", "bolt://localhost:7687")
AUTH = (os.getenv("NEO4J_USER", "neo4j"), os.getenv("NEO4J_PASSWORD", "your_new_password"))

# One constraint per entity type. Each creates a backing index automatically.
CONSTRAINTS = [
    "CREATE CONSTRAINT disease_id IF NOT EXISTS FOR (n:Disease) REQUIRE n.id IS UNIQUE",
    "CREATE CONSTRAINT drug_id IF NOT EXISTS FOR (n:Drug) REQUIRE n.id IS UNIQUE",
    "CREATE CONSTRAINT procedure_id IF NOT EXISTS FOR (n:Procedure) REQUIRE n.id IS UNIQUE",
    "CREATE CONSTRAINT symptom_id IF NOT EXISTS FOR (n:Symptom) REQUIRE n.id IS UNIQUE",
    "CREATE CONSTRAINT organization_id IF NOT EXISTS FOR (n:Organization) REQUIRE n.id IS UNIQUE",
    "CREATE CONSTRAINT specialty_id IF NOT EXISTS FOR (n:Specialty) REQUIRE n.id IS UNIQUE",
    "CREATE CONSTRAINT guideline_id IF NOT EXISTS FOR (n:Guideline) REQUIRE n.id IS UNIQUE",
    "CREATE CONSTRAINT labtest_id IF NOT EXISTS FOR (n:LabTest) REQUIRE n.id IS UNIQUE",
    "CREATE CONSTRAINT device_id IF NOT EXISTS FOR (n:Device) REQUIRE n.id IS UNIQUE",
    "CREATE CONSTRAINT document_id IF NOT EXISTS FOR (n:Document) REQUIRE n.id IS UNIQUE",
]

# Extra indexes on fields you'll filter/search by often (not just the unique id)
INDEXES = [
    "CREATE INDEX disease_name IF NOT EXISTS FOR (n:Disease) ON (n.name)",
    "CREATE INDEX drug_name IF NOT EXISTS FOR (n:Drug) ON (n.name)",
    "CREATE INDEX procedure_name IF NOT EXISTS FOR (n:Procedure) ON (n.name)",
    "CREATE INDEX symptom_name IF NOT EXISTS FOR (n:Symptom) ON (n.name)",
    "CREATE INDEX document_source IF NOT EXISTS FOR (n:Document) ON (n.source)",
]


def setup_schema():
    driver = GraphDatabase.driver(URI, auth=AUTH)
    with driver.session() as session:
        print("Creating constraints...")
        for stmt in CONSTRAINTS:
            session.run(stmt)
            print(f"  OK: {stmt.split('FOR')[0].strip()}")

        print("\nCreating indexes...")
        for stmt in INDEXES:
            session.run(stmt)
            print(f"  OK: {stmt.split('FOR')[0].strip()}")

        # Confirm what's actually live
        print("\nCurrent constraints in DB:")
        for record in session.run("SHOW CONSTRAINTS"):
            print(f"  {record['name']} -> {record['labelsOrTypes']} ({record['properties']})")

    driver.close()
    print("\nSchema setup complete.")


if __name__ == "__main__":
    setup_schema()
