"""
Query layer - what the Search & API module (Epic 5) will call
to pull graph context alongside vector search results.

Each function returns plain Python dicts/lists so it's easy to
wrap in a FastAPI endpoint later.
"""

import os
from neo4j import GraphDatabase

URI = os.getenv("NEO4J_URI", "bolt://localhost:7687")
AUTH = (os.getenv("NEO4J_USER", "neo4j"), os.getenv("NEO4J_PASSWORD", "your_new_password"))


class GraphQueries:
    def __init__(self):
        self.driver = GraphDatabase.driver(URI, auth=AUTH)

    def close(self):
        self.driver.close()

    def get_entity_neighbors(self, entity_id: str, depth: int = 1):
        """All nodes/relationships connected to a given entity, up to `depth` hops."""
        query = f"""
        MATCH (n {{id: $entity_id}})-[r*1..{depth}]-(neighbor)
        RETURN DISTINCT neighbor.id AS id, neighbor.name AS name,
               labels(neighbor) AS labels
        """
        with self.driver.session() as session:
            result = session.run(query, entity_id=entity_id)
            return [dict(record) for record in result]

    def get_diseases_treated_by_drug(self, drug_name: str):
        query = """
        MATCH (d:Drug {name: $drug_name})-[:TREATS]->(disease:Disease)
        RETURN disease.id AS id, disease.name AS name
        """
        with self.driver.session() as session:
            result = session.run(query, drug_name=drug_name)
            return [dict(record) for record in result]

    def get_document_entities(self, document_id: str):
        """All entities extracted from a specific document - useful for
        cross-checking extraction quality (Epic 7)."""
        query = """
        MATCH (e)-[:MENTIONED_IN]->(d:Document {id: $document_id})
        RETURN e.id AS id, e.name AS name, labels(e) AS labels
        """
        with self.driver.session() as session:
            result = session.run(query, document_id=document_id)
            return [dict(record) for record in result]

    def search_by_name(self, name_fragment: str, limit: int = 10):
        """Case-insensitive partial name search across all entity types."""
        query = """
        MATCH (n)
        WHERE toLower(n.name) CONTAINS toLower($fragment)
        RETURN n.id AS id, n.name AS name, labels(n) AS labels
        LIMIT $limit
        """
        with self.driver.session() as session:
            result = session.run(query, fragment=name_fragment, limit=limit)
            return [dict(record) for record in result]


if __name__ == "__main__":
    gq = GraphQueries()
    print("Diseases treated by Metformin:")
    print(gq.get_diseases_treated_by_drug("Metformin"))

    print("\nEntities in doc-001:")
    print(gq.get_document_entities("doc-001"))

    print("\nSearch 'gluc':")
    print(gq.search_by_name("gluc"))

    gq.close()
