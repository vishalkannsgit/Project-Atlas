# Project Atlas - Document Onboarding Microservice

A production-ready asynchronous document onboarding service built with **FastAPI**, **SQLAlchemy 2.0 (async)**, and **Pydantic v2**.

---

## Features
- **Security & Integrity:** Validates PDF magic-byte signatures (`%PDF-`), computes SHA-256 hashes using a 64 KB memory-safe stream, and enforces a 50 MB file size limit.
- **Idempotency & Deduplication:** Prevents duplicate processing via client-supplied idempotency keys and tenant-scoped SHA-256 content hashes.
- **Storage Abstraction:** Supports local disk storage for development and S3/MinIO for cloud deployment.
- **Event-Driven Handoff:** Publishes an `ingest.raw` event with payload metadata for downstream processing.
- **Observability:** Exposes Prometheus metrics at `/metrics` and Kubernetes-compatible probes at `/healthz`.

---

## Directory Structure
```text
atlas_onboarding/
├── app/
│   ├── api/          # Route handlers (upload, status)
│   ├── core/         # Settings and async database engine
│   ├── models/       # SQLAlchemy ORM definitions
│   ├── schemas/      # Pydantic v2 validation contracts
│   ├── services/     # Storage and event handoff logic
│   └── main.py       # Application factory and lifespan hooks
├── tests/            # Automated pytest integration test suite
├── Dockerfile        # Containerization configuration
├── docker-compose.yml# Multi-service deployment specification
├── requirements.txt  # Pinned dependencies
└── pytest.ini        # Test runner configuration

Installation:
DOS:
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt

Running the Server:
DOS:
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload

Interactive API documentation will be available at:
Swagger UI: http://127.0.0.1:8000/docs
ReDoc: http://127.0.0.1:8000/redoc