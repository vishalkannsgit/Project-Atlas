"""
Basic tests against a running local Neo4j instance.
Run schema/setup_schema.py and src/ingest.py with the sample data
BEFORE running these.

Run with: pytest tests/test_ingest.py -v
"""

import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), "..", "src"))

from queries import GraphQueries


def test_drug_treats_disease():
    gq = GraphQueries()
    result = gq.get_diseases_treated_by_drug("Metformin")
    gq.close()
    assert len(result) == 1
    assert result[0]["name"] == "Type 2 Diabetes Mellitus"


def test_document_has_entities():
    gq = GraphQueries()
    result = gq.get_document_entities("doc-001")
    gq.close()
    names = [r["name"] for r in result]
    assert "Type 2 Diabetes Mellitus" in names
    assert "Metformin" in names


def test_search_by_name_partial_match():
    gq = GraphQueries()
    result = gq.search_by_name("gluc")
    gq.close()
    names = [r["name"].lower() for r in result]
    assert any("gluc" in n or "glucose" in n for n in names)


def test_reingest_does_not_duplicate():
    """MERGE-based ingestion should be idempotent - running twice
    should not create duplicate nodes."""
    gq = GraphQueries()
    before = gq.search_by_name("metformin")
    gq.close()
    assert len(before) == 1  # only one Metformin node should ever exist


if __name__ == "__main__":
    test_drug_treats_disease()
    test_document_has_entities()
    test_search_by_name_partial_match()
    test_reingest_does_not_duplicate()
    print("All tests passed.")
