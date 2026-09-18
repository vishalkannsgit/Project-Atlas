# Manual Onboarding Microservice (Project Atlas)

A high-throughput, asynchronous document onboarding microservice built with FastAPI, SQLAlchemy 2.0 (async), Pydantic v2, and Prometheus observability.

---

## Supported Formats & Signatures

The ingestion engine enforces strict magic-byte sniffing combined with extension matching to prevent MIME-spoofing attacks:

| Format | Extension | Container Signature | Detected MIME Type |
|---|---|---|---|
| **PDF** | `.pdf` | `%PDF-` (`0x25 0x50 0x44 0x46 0x2D`) | `application/pdf` |
| **Word** | `.docx` | `PK\x03\x04` (Zip archive) | `application/vnd.openxmlformats-officedocument.wordprocessingml.document` |
| **PowerPoint** | `.pptx` | `PK\x03\x04` (Zip archive) | `application/vnd.openxmlformats-officedocument.presentationml.presentation` |
| **Excel** | `.xlsx` | `PK\x03\x04` (Zip archive) | `application/vnd.openxmlformats-officedocument.spreadsheetml.sheet` |

---

## Architecture & Data Flow

1. **Ingestion & Sniffing:** Streams 64 KB chunks, validates leading magic bytes against expected file extensions, and computes an immutable SHA-256 digest in a single pass.
2. **Two-Tier Idempotency Guard:**
   - **Tier 1 (Header):** Matches client-provided `X-Idempotency-Key` within tenant scope.
   - **Tier 2 (Content Hash):** Detects duplicate content by SHA-256 digest per tenant, eliminating redundant storage and duplicate downstream events.
3. **Storage Abstraction:** Persists to local disk or AWS S3/MinIO via asynchronous streaming (`aioboto3`).
4. **Event Emission:** Dispatches `DOCUMENT_UPLOADED` events to Redpanda/Kafka via `aiokafka` (with non-blocking local fallback).
5. **Observability:**
   - Health check at `/healthz`
   - Prometheus metrics at `/metrics` tracking upload volume, tenant activity, and format distribution (`manual_onboarding_uploads_total`).
6. In-Memory Metadata Extraction:
   - Streams byte buffers directly into format-specific parsers (pypdf, python-docx, python-pptx, openpyxl) without writing temporary files to disk.
   - Extracts structural properties: author, title, creation timestamps, page counts (PDF), paragraph counts (DOCX), slide counts (PPTX), and sheet counts/names (XLSX).
   - Enriches metadata_json before persisting the record to the database and publishing the ingest event.
7. Anti-Malware & Security Scanner:
   - In-memory inspection of byte streams before files touch persistent storage or emit events.
   - Built-in heuristics for known signatures (including standard EICAR test vectors).
   - Optional daemon offloading to ClamAV via TCP socket with configurable timeouts.
   - Malicious files are rejected with HTTP 422 (Unprocessable Content), labeled as 'quarantined' in metrics, and blocked from storage.
8. Safe Archive Handling (ZIP Ingestion):
   - In-memory unpacking with guards against path traversal (Zip Slip vulnerability).
   - Rejection thresholds for file count limits, excessive aggregate uncompressed size, and high compression ratios (Zip bomb protection).
   - Recursive inspection running magic-byte validation and malware scanning on each archive member before ingestion.

---

## Directory Structure

```text
manual-onboarding/
├── app/
│   ├── api/          # Route handlers (upload, status check)
│   ├── core/         # Config, metrics, and async database engine
│   ├── models/       # SQLAlchemy 2.0 ORM definitions
│   ├── schemas/      # Pydantic v2 validation contracts
│   ├── services/     # Storage abstraction and event dispatchers
│   └── main.py       # FastAPI application factory and lifespan hooks
├── tests/            # Automated pytest integration test suite
├── Dockerfile        # Containerization specification
├── docker-compose.yml# Local multi-service orchestration (App, MinIO, Redpanda)
├── requirements.txt  # Pinned dependencies
└── pytest.ini        # Test runner configuration

---

## Configuration & Environment Variables

* PROJECT_NAME: Project Atlas - Manual Onboarding (Service display name)
* API_V1_STR: /api/v1 (Global API route prefix)
* DATABASE_URL: sqlite+aiosqlite:///./onboarding.db (Async database connection string)
* STORAGE_BACKEND: local (Storage provider: 'local' or 's3')
* LOCAL_STORAGE_DIR: ./data/uploads (Root directory for local file storage)
* MAX_FILE_SIZE_BYTES: 52428800 (Maximum permitted file upload size: 50 MB)
* KAFKA_ENABLED: false (Toggle Kafka/Redpanda event streaming)
* KAFKA_BOOTSTRAP_SERVERS: localhost:9092 (Kafka/Redpanda connection address)
* KAFKA_TOPIC_RAW_INGEST: document.uploaded (Topic name for ingest events)
* CLAMAV_ENABLED: false (Toggle network socket ClamAV engine)
* CLAMAV_HOST: localhost (ClamAV daemon host address)
* CLAMAV_PORT: 3310 (ClamAV TCP port)
* SCANNER_TIMEOUT_SECONDS: 5.0 (Maximum wait time for scan responses)
* ZIP_MAX_FILES: 100 (Maximum number of entries permitted per ZIP archive)
* ZIP_MAX_UNCOMPRESSED_BYTES: 104857600 (Maximum total uncompressed payload: 100 MB)
* ZIP_MAX_COMPRESSION_RATIO: 100.0 (Threshold for suspected zip-bomb detection)

1. Upload Document
Path: POST /api/v1/documents/upload
Headers:
X-Tenant-ID: string (Required)
X-Idempotency-Key: string (Optional)
Body: multipart/form-data with key file
Success Response (201 Created):

{
  "document_id": "4d1685a2-3f19-4cb5-8d59-5f21272ce100",
  "tenant_id": "tenant_123",
  "filename": "spec.docx",
  "file_format": "docx",
  "mime_type": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
  "sha256_hash": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
  "file_size_bytes": 10240,
  "storage_uri": "file:///path/to/uploads/tenant_123/e3b0...docx",
  "status": "UPLOADED",
  "message": "Document uploaded and onboarded successfully."
}

2. Status Check
Path: GET /api/v1/documents/{document_id}
Headers:
X-Tenant-ID: string (Required)
Success Response (200 OK):
{
  "id": "4d1685a2-3f19-4cb5-8d59-5f21272ce100",
  "tenant_id": "tenant_123",
  "filename": "spec.docx",
  "file_format": "docx",
  "mime_type": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
  "sha256_hash": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
  "file_size_bytes": 10240,
  "storage_uri": "file:///path/to/uploads/tenant_123/e3b0...docx",
  "status": "UPLOADED",
  "metadata_json": { "original_extension": ".docx" },
  "created_at": "2026-09-18T00:00:00Z",
  "updated_at": "2026-09-18T00:00:00Z"
}

1. Environment Setup
Bash
cd manual-onboarding
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt

2. Run the Service
Bash
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000

3. Run the Test Suite
Bash
pytest -v

---

## Infrastructure & Local Services (Docker Compose)

When running the service dependencies via `docker-compose up -d`, the following local management consoles and service endpoints are active:

| Service | Protocol / Role | Host Endpoint | Default Credentials |
|---|---|---|---|
| **Manual Onboarding API** | FastAPI / HTTP | `http://localhost:8000` | N/A |
| **API Interactive Docs** | Swagger UI / OpenAPI | `http://localhost:8000/docs` | N/A |
| **Prometheus Metrics** | Scrape Target | `http://localhost:8000/metrics` | N/A |
| **MinIO S3 API** | Object Storage Backend | `http://localhost:9000` | `minioadmin` / `minioadmin` |
| **MinIO Web Console** | Storage Management UI | `http://localhost:9001` | `minioadmin` / `minioadmin` |
| **Redpanda Broker** | Kafka Event Bus | `localhost:9092` | N/A |
| **Redpanda Console** | Kafka Topic & Event UI | `http://localhost:8080` | N/A |

### Starting Supporting Infrastructure

To spin up MinIO and Redpanda locally before starting the app:

```bash
docker-compose up -d minio redpanda console

To verify topics or inspect incoming document.uploaded events, open the Redpanda Console at http://localhost:8080.

Docker Deployment & Verification
1. Local Stack Architecture:
   - FastAPI Application (atlas_onboarding_service): Runs on port 8000.
   - MinIO S3 Storage (atlas_minio): Port 9000 (API) and 9001 (Web Console).
   - MinIO Bucket Initializer (atlas_minio_init): Automatically provisions atlas-raw-documents.
   - Redpanda Streaming (atlas_redpanda): Port 19092 (External) and 9092 (Internal).
   - Redpanda Web Console (atlas_redpanda_console): Port 8080.

2. Volume & State Persistence:
   - SQLite Database: Mounted via directory mapping (./data:/app/data) to prevent single-file lock collisions on Windows hosts.
   - MinIO Object Storage: Backed by docker named volume minio_data.

3. Running the Stack:
   - Start all containers:
     docker-compose up -d --build
   - Check container health:
     docker-compose ps
   - View application logs:
     docker logs -f atlas_onboarding_service

4. Verification Endpoints:
   - Health Check: GET http://localhost:8000/healthz
   - Prometheus Metrics: GET http://localhost:8000/metrics/
   - MinIO Web UI: http://localhost:9001 (Credentials: minioadmin / minioadmin)
   - Redpanda Web UI: http://localhost:8080


- [x] Milestone 1: Multi-Format Ingestion (.pdf, .docx, .pptx, .xlsx) & Signature Sniffing
- [x] Milestone 2: In-Memory Document Metadata Extraction
- [x] Milestone 3: Validation & Anti-Malware / Quarantine Scanner Pipeline
- [x] Milestone 4: Safe ZIP Archive Upload & Decompression (Zip-bomb / Path-traversal Guards)
- [x] Milestone 5: End-to-End Test Suite & Docker Orchestration

When you are done testing or working on the project, spin the stack down:
DOS
docker-compose down

When you are ready to work on Project Atlas again, simply bring it back up:
DOS
docker-compose up -d