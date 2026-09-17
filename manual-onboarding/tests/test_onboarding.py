import io
import uuid
import pytest
from httpx import AsyncClient, ASGITransport

from app.core.config import settings

# Force local backend during pytest runs regardless of .env file
settings.STORAGE_BACKEND = "local"
settings.KAFKA_ENABLED = False

from app.main import app

MOCK_PDF_BYTES = b"%PDF-1.4 Minimal Mock PDF byte buffer for automated testing"
INVALID_FILE_BYTES = b"This is plain text and not a real PDF file."

@pytest.mark.asyncio
async def test_health_check():
    """Verify that the observability health endpoint responds with 200 OK."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/healthz")
        assert response.status_code == 200
        assert response.json()["status"] == "healthy"

@pytest.mark.asyncio
async def test_upload_valid_pdf_and_idempotency():
    """Test standard upload flow and duplicate detection with isolated tenant."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Unique tenant per test run to prevent collision with persistent sqlite records
        test_tenant = f"tenant_{uuid.uuid4().hex[:8]}"
        file_payload = ("sample_document.pdf", io.BytesIO(MOCK_PDF_BYTES), "application/pdf")

        # 1. Initial Upload
        response = await client.post(
            "/api/v1/onboarding/documents/upload",
            data={"tenant_id": test_tenant, "metadata": '{"category": "test"}'},
            files={"file": file_payload}
        )
        assert response.status_code == 202
        data = response.json()
        assert "document_id" in data
        assert data["status"] == "QUEUED"
        assert data["is_duplicate"] is False
        doc_id = data["document_id"]

        # 2. Check Document Status
        status_resp = await client.get(f"/api/v1/onboarding/documents/{doc_id}/status")
        assert status_resp.status_code == 200
        assert status_resp.json()["tenant_id"] == test_tenant

        # 3. Duplicate Upload (Idempotency test)
        dup_file_payload = ("sample_document.pdf", io.BytesIO(MOCK_PDF_BYTES), "application/pdf")
        dup_response = await client.post(
            "/api/v1/onboarding/documents/upload",
            data={"tenant_id": test_tenant},
            files={"file": dup_file_payload}
        )
        assert dup_response.status_code == 202
        dup_data = dup_response.json()
        assert dup_data["is_duplicate"] is True
        assert dup_data["document_id"] == doc_id

@pytest.mark.asyncio
async def test_reject_invalid_pdf_magic_bytes():
    """Ensure non-PDF files are rejected with a 400 Bad Request."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        invalid_file = ("fake.pdf", io.BytesIO(INVALID_FILE_BYTES), "application/pdf")
        response = await client.post(
            "/api/v1/onboarding/documents/upload",
            data={"tenant_id": "test_tenant_invalid"},
            files={"file": invalid_file}
        )
        assert response.status_code == 400
        assert "Invalid file format" in response.json()["detail"]

@pytest.mark.asyncio
async def test_get_nonexistent_document_status():
    """Ensure querying an unknown document ID returns 404 Not Found."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/v1/onboarding/documents/non-existent-uuid/status")
        assert response.status_code == 404