from fastapi.testclient import TestClient
from metadata_knowledge.api.app import app


def test_health():
    response = TestClient(app).get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_process_endpoint():
    response = TestClient(app).post("/api/v1/metadata/process", json={
        "document_id": "doc-api-1", "source": "cdc", "title": "Asthma report",
        "text": "This report discusses asthma and treatment with aspirin.", "file_type": "pdf"
    })
    assert response.status_code == 200
    body = response.json()["metadata"]
    assert body["document_id"] == "doc-api-1"
    assert body["entities"]
