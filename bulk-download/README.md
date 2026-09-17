# 📥 Bulk Download Service

**Project Atlas — Data Acquisition Component**

> Reliably downloads, validates, deduplicates, tracks, and stages large numbers of public health documents (PDFs, HTML) from government sources for the downstream Atlas AI pipeline.

---

## 📋 Table of Contents

- [What This Does](#what-this-does)
- [Why This Exists in Atlas](#why-this-exists-in-atlas)
- [Architecture & Pipeline](#architecture--pipeline)
- [Technology Choices & Why](#technology-choices--why)
- [Project Structure](#project-structure)
- [How Each Component Works](#how-each-component-works)
- [Getting Started](#getting-started)
- [Running the Downloader](#running-the-downloader)
- [Running Tests](#running-tests)
- [Configuration](#configuration)
- [Download Status Codes](#download-status-codes)
- [Retry Policy](#retry-policy)
- [Output Files](#output-files)
- [Adding New Sources](#adding-new-sources)
- [Atlas Handoff (For Teammates)](#atlas-handoff-for-teammates)
- [What is NOT in Git](#what-is-not-in-git)

---

## What This Does

The Bulk Download Service is the **first stage** of the Project Atlas knowledge pipeline. Its sole job is:

```
Find documents → Download them safely → Validate them → Remove duplicates → Store them → Hand off to processing
```

Concretely:

```
WHO / CDC / NIH / FDA sources
            ↓
     Load URL list from data_sources/
            ↓
   Async concurrent downloads (5 workers)
            ↓
   HTTP status check (200? 404? 429?)
            ↓
   Content-Type check (PDF? HTML error page?)
            ↓
   Magic bytes check (is it actually a PDF?)
            ↓
   File size check (not empty? not 200MB?)
            ↓
   SHA-256 hash (content fingerprint)
            ↓
   Duplicate check (seen before? skip it)
            ↓
   data/raw/<source>/<YYYY>/<MM>/
            ↓
   Manifest DB (SQLite) + JSON export
            ↓
   data/staging/acquisition/  ← teammate picks up here
```

---

## Why This Exists in Atlas

Atlas is an AI-Native Knowledge Engineering Platform. Before any document can be:
- Parsed → Chunked → Embedded → Stored in Qdrant

…it first has to be **reliably acquired**. That sounds simple, but at scale it is not:

| Problem | Why it matters |
|---------|----------------|
| Links go dead (404) | WHO/CDC URLs change constantly |
| Servers return HTML error pages with status 200 | A naive downloader stores garbage |
| Same document served at two URLs | Without dedup, you embed it twice |
| Rate limits and temporary server errors | Without retry logic, you lose documents |
| 1000s of documents across many sources | Manual downloading doesn't scale |
| Team needs to know what was acquired | Without a manifest, no one knows what's staged |

This service solves all of these before any document reaches the processing team.

---

## Architecture & Pipeline

```
┌─────────────────────────────────────────────────────────────┐
│                    BULK DOWNLOAD SERVICE                     │
│                                                              │
│  data_sources/*.json                                         │
│        │                                                     │
│        ▼                                                     │
│  load_jobs_from_sources()   ← URL + source + type           │
│        │                                                     │
│        ▼                                                     │
│  asyncio.Semaphore(5)       ← max 5 concurrent workers      │
│     │       │       │                                        │
│  Worker1  Worker2  Worker3  ...                              │
│     │                                                        │
│     ├── GET request (aiohttp, streaming)                     │
│     │                                                        │
│     ├── validate_http_response()                             │
│     │       ✓ HTTP 200/206                                   │
│     │       ✓ Content-Type matches expected                  │
│     │                                                        │
│     ├── stream to temp file (8KB chunks)                     │
│     │                                                        │
│     ├── validate_file()                                      │
│     │       ✓ magic bytes (%PDF, <!DOCTYPE…)                 │
│     │       ✓ size within limits                             │
│     │                                                        │
│     ├── sha256_file()  → content fingerprint                 │
│     │                                                        │
│     ├── deduplicator.is_duplicate()                          │
│     │       → in-memory set (current run)                    │
│     │       → SQLite manifest (previous runs)                │
│     │                                                        │
│     └── move to data/raw/<source>/<YYYY>/<MM>/               │
│                                                              │
│  manifest.record()  → SQLite DB                              │
│  manifest.export_json()  → JSON for teammates                │
│                                                              │
└─────────────────────────────────────────────────────────────┘
         │
         ▼
data/staging/acquisition/manifest_export.json
         │
         ▼   (picked up by processing teammate)
    Parser → Chunker → Embedding (Ollama) → Qdrant
```

---

## Technology Choices & Why

### `asyncio` + `aiohttp` — Async HTTP

**Why not `requests`?**

`requests` is synchronous. If you download 100 files with `requests`, they happen **one at a time**. With 5-second download times each, 100 files = 500 seconds.

`asyncio` + `aiohttp` allows multiple downloads to happen **simultaneously** within a single thread:

```
requests (sync):   ──PDF1──PDF2──PDF3──PDF4──PDF5──   (sequential)
aiohttp (async):   ──PDF1──
                       ──PDF2──
                           ──PDF3──
                               ──PDF4──   (concurrent)
                                   ──PDF5──
```

**Why not `ThreadPoolExecutor`?**

Threads work, but they have overhead and share memory awkwardly. `asyncio` handles I/O-bound tasks (like HTTP) more efficiently with no thread overhead.

**`asyncio.Semaphore`** is used to cap concurrency at `MAX_WORKERS = 5`. Without it, launching 1000 requests simultaneously would get us IP-blocked instantly.

---

### `aiofiles` — Async file writes

When streaming a large PDF from HTTP, writing each chunk to disk synchronously would block the event loop. `aiofiles` wraps file I/O in a thread pool so it doesn't block other downloads.

---

### `SQLite` (stdlib) — Manifest database

**Why not a plain JSON file?**

| Feature | JSON file | SQLite |
|---------|-----------|--------|
| Query by status | Requires loading entire file | `SELECT * WHERE status='SUCCESS'` |
| Query by hash | Load & scan | Indexed lookup |
| Concurrent writes | Manual locking | WAL mode handles it |
| Cross-run persistence | Manual merge | Just works |
| No extra dependencies | ✓ | ✓ (stdlib) |

SQLite is built into Python's stdlib, requires no server, and gives us a proper queryable database. We use **WAL (Write-Ahead Logging)** mode for safer concurrent access.

We also export a `manifest_export.json` after every run so teammates don't need to query SQLite — they just read JSON.

---

### SHA-256 — Content hashing

**Why hash files?**

A URL is an *address*, not an *identity*. Two different URLs can point to the same document. Two different URLs can point to different versions of the same document.

SHA-256 gives us **content identity** — a fingerprint of the actual bytes. If `sha256(file_A) == sha256(file_B)`, they are byte-for-byte identical. We only store unique content, never duplicates.

We use **streaming hashing** (8KB chunks) so a 100MB PDF never has to be fully loaded into memory.

---

### Magic bytes validation — Not just trusting Content-Type

A common failure mode with government websites:

```
GET https://example.gov/report.pdf
HTTP 200 OK
Content-Type: application/pdf

<html><body>Session expired. Please log in.</body></html>
```

The URL says PDF, the header says PDF, but the content is HTML. A naive downloader stores a useless HTML error page.

**Magic bytes** are the first few bytes of a file that identify its real type:
- `%PDF` → real PDF
- `<!DOCTYPE` → HTML
- `PK` → ZIP (Office docx)

We check these *after* downloading to catch this exact scenario.

---

### Exponential backoff — Retry logic

Government servers rate-limit, overload, and return 503s. Without retry logic, a temporary hiccup means permanently missing a document.

```
Attempt 1 fails (500) → wait 2s → retry
Attempt 2 fails (503) → wait 4s → retry
Attempt 3 fails (429) → wait 8s → retry
Attempt 4 fails       → wait 16s → retry
Attempt 5 fails       → mark FAILED, move on
```

We specifically distinguish:
- **Retryable**: 429, 500, 502, 503, 504, timeout, connection error
- **Non-retryable**: 404, 403, 401, 410 — retrying these wastes time

---

## Project Structure

```
bulk-download/
│
├── src/
│   └── bulk_downloader/          ← Python package
│       ├── __init__.py
│       ├── config.py             ← All settings (paths, workers, timeouts)
│       ├── models.py             ← DownloadJob + DownloadResult dataclasses
│       ├── downloader.py         ← Core async engine + retry loop + file storage
│       ├── validator.py          ← HTTP + magic-bytes file validation
│       ├── hasher.py             ← SHA-256 streaming hasher
│       ├── deduplicator.py       ← Duplicate detection (in-memory + DB)
│       └── manifest.py           ← SQLite manifest + JSON export
│
├── tests/
│   ├── __init__.py
│   ├── test_hasher.py            ← 6 tests
│   ├── test_validator.py         ← 16 tests
│   ├── test_deduplicator.py      ← 9 tests
│   └── test_downloader.py        ← 17 tests
│
├── data_sources/
│   ├── who_sources.json          ← 5 seed URLs (WHO/FDA)
│   ├── cdc_sources.json          ← 5 seed URLs (CDC Stacks)
│   └── nih_sources.json          ← 5 seed URLs (NIH/FDA)
│
├── scripts/
│   └── run_bulk_download.py      ← CLI entry point
│
├── requirements.txt
├── pytest.ini
└── README.md                     ← you are here
```

---

## How Each Component Works

### `config.py`
Single `BulkDownloadConfig` dataclass that holds every setting. Paths are resolved by walking up the directory tree to find `.git/` (repo root). All numeric settings can be overridden via environment variables — useful for CI or adjusting concurrency per machine.

### `models.py`
Two dataclasses:
- **`DownloadJob`** — what to download (URL, source, expected type)
- **`DownloadResult`** — what happened (status, hash, file path, error, timing)

`DownloadStatus` is a string enum so it serialises cleanly to JSON/SQLite without extra code.

### `downloader.py`
The orchestrator. `download_all(jobs)` creates an `aiohttp.ClientSession` and an `asyncio.Semaphore`, then gathers all download coroutines. Each job goes through:
1. `_download_one` (acquires semaphore slot)
2. `_fetch_with_retry` (retry loop with exponential backoff)
3. `_try_download` (single HTTP attempt → validate → hash → deduplicate → save)

### `validator.py`
Two-stage validation:
1. **HTTP stage** — checks status code and Content-Type header
2. **File stage** — reads the first 512 bytes and checks magic bytes; also checks size limits

The magic byte map covers PDF, HTML, DOC, DOCX, XML.

### `hasher.py`
Streams file in 8KB chunks through `hashlib.sha256`. Memory usage is constant regardless of file size.

### `deduplicator.py`
Two layers:
1. **In-memory set** — O(1) check for hashes seen in the current run (fastest)
2. **SQLite manifest** — durable check for hashes from all previous runs

On a DB hit, the hash is promoted to the in-memory set so subsequent checks skip the DB.

### `manifest.py`
SQLite database with a single `downloads` table. Uses WAL journal mode for safety. The `sha256` column has an inline `UNIQUE` constraint enabling SQLite's native upsert (`ON CONFLICT … DO UPDATE`) for atomic insert-or-update.

---

## Getting Started

### Requirements

- Python 3.11 or higher (tested on 3.14)
- `libmagic` is **not** required — we use our own magic byte implementation

### Setup

```bash
# From the repo root
cd bulk-download

# Create virtual environment
python3 -m venv .venv
source .venv/bin/activate        # Linux / macOS
# .venv\Scripts\activate         # Windows

# Install dependencies
pip install -r requirements.txt
```

---

## Running the Downloader

### Download all built-in sources (WHO + CDC + NIH)

```bash
python scripts/run_bulk_download.py --sources who cdc nih
```

### Preview what would run (no downloads)

```bash
python scripts/run_bulk_download.py --sources who cdc nih --dry-run
```

### Adjust concurrency

```bash
# 3 workers (gentler on servers)
python scripts/run_bulk_download.py --sources who cdc nih --workers 3

# 10 workers (faster, use with care)
python scripts/run_bulk_download.py --sources cdc --workers 10
```

### Download a single source

```bash
python scripts/run_bulk_download.py --sources cdc
```

### Use a custom URL file

Create your own JSON file:
```json
[
  {
    "source": "my_agency",
    "url": "https://example.gov/report.pdf",
    "document_type": "pdf",
    "allowed_domain": "example.gov",
    "description": "Annual Health Report 2024"
  }
]
```

Then run:
```bash
python scripts/run_bulk_download.py --url-file my_urls.json
```

### See detailed debug logging

```bash
python scripts/run_bulk_download.py --sources who cdc nih --verbose
```

### Expected output

```
════════════════════════════════════════════════════════════
  Project Atlas — Bulk Downloader
  Jobs: 15  |  Workers: 5  |  Max retries: 4
  Output: /path/to/data/raw
  Manifest: /path/to/data/staging/acquisition/manifest.db
════════════════════════════════════════════════════════════

11:07:47 [INFO] ✅ [SUCCESS]  cdc_164153_DS1.pdf  (654 KB)
11:07:47 [INFO] ✅ [SUCCESS]  jnc7full.pdf        (955 KB)
...

════════════════════════════════════════════════════════════
  Download Summary
────────────────────────────────────────────────────────────
  ✅  SUCCESS          13  █████████████
  ♻️   DUPLICATE         2  ██
────────────────────────────────────────────────────────────
  TOTAL                15
════════════════════════════════════════════════════════════

  Manifest DB  : data/staging/acquisition/manifest.db
  Manifest JSON: data/staging/acquisition/manifest_export.json
  Raw files    : data/raw
```

---

## Running Tests

All tests use mocked HTTP — **no real network requests** are made during testing.

### Run all tests

```bash
cd bulk-download
pytest tests/ -v
```

### Run a specific test file

```bash
pytest tests/test_validator.py -v
pytest tests/test_hasher.py -v
pytest tests/test_deduplicator.py -v
pytest tests/test_downloader.py -v
```

### Run a specific test

```bash
pytest tests/test_validator.py::TestValidateFile::test_pdf_served_as_html -v
```

### Expected result

```
tests/test_deduplicator.py::TestDeduplicator::test_new_hash_is_not_duplicate     PASSED
tests/test_deduplicator.py::TestDeduplicator::test_registered_hash_is_duplicate  PASSED
...
tests/test_validator.py::TestValidateFile::test_pdf_served_as_html               PASSED
tests/test_validator.py::TestValidateFile::test_file_too_small                   PASSED
...

Results: 48 passed in 0.14s
```

### What each test file covers

| File | Tests | What's covered |
|------|-------|----------------|
| `test_hasher.py` | 6 | Known SHA-256 values, streaming, large files, missing files |
| `test_validator.py` | 16 | HTTP status checks, Content-Type mismatch, magic bytes, size limits |
| `test_deduplicator.py` | 9 | In-run cache, DB lookup, cache promotion, independence of hashes |
| `test_downloader.py` | 17 | Path building, JSON loading, success path, HTTP errors, deduplication, concurrency |

---

## Configuration

Settings live in `config.py` and can be overridden via environment variables:

| Setting | Env Var | Default | Description |
|---------|---------|---------|-------------|
| Workers | `ATLAS_BD_WORKERS` | `5` | Max concurrent downloads |
| Max retries | `ATLAS_BD_MAX_RETRIES` | `4` | Retry attempts after first failure |
| Backoff base | `ATLAS_BD_BACKOFF_BASE` | `2.0` | `wait = base ** attempt` seconds |
| Max file size | `ATLAS_BD_MAX_FILE_MB` | `100` | Files larger than this are rejected |

Override example:
```bash
ATLAS_BD_WORKERS=8 ATLAS_BD_MAX_RETRIES=3 python scripts/run_bulk_download.py --sources cdc
```

---

## Download Status Codes

Every download ends in exactly one status:

| Status | Icon | Meaning | Retried? |
|--------|------|---------|----------|
| `SUCCESS` | ✅ | Downloaded, validated, stored | — |
| `DUPLICATE` | ♻️ | SHA-256 already in manifest | — |
| `INVALID_FILE` | ⚠️ | Content-Type or magic-bytes mismatch | No |
| `HTTP_ERROR` | ❌ | 4xx/5xx not retried, or retries exhausted | Depends |
| `TIMEOUT` | ⏱️ | Connection/read timeout exhausted | Yes |
| `FAILED` | 💥 | Any other unrecoverable error | Yes |

---

## Retry Policy

| Condition | Action |
|-----------|--------|
| HTTP 429 (rate limited) | Retry — respects `Retry-After` header |
| HTTP 500, 502, 503, 504 | Retry with backoff |
| HTTP 400, 401, 403, 404, 410 | **Immediate failure** — no retry |
| Connection error | Retry with backoff |
| Timeout | Retry with backoff |
| Invalid file (wrong type) | **Immediate failure** — retrying won't fix this |

**Backoff schedule:**

```
Attempt 1 fails → wait  2 s → retry
Attempt 2 fails → wait  4 s → retry
Attempt 3 fails → wait  8 s → retry
Attempt 4 fails → wait 16 s → retry
Attempt 5 fails → mark FAILED
```

---

## Output Files

### Downloaded documents

```
data/
└── raw/
    ├── cdc/
    │   └── 2026/
    │       └── 09/
    │           ├── 7501cf051537_cdc_164153_DS1.pdf   (654 KB)
    │           └── 0c77c619f68b_cdc_157638_DS1.pdf   (1.2 MB)
    ├── nih/
    │   └── 2026/
    │       └── 09/
    │           └── 248adee76157_jnc7full.pdf         (955 KB)
    └── who/
        └── 2026/
            └── 09/
                └── 06a64f30e22a_download             (844 KB)
```

**Filename format:** `<first 12 chars of SHA-256>_<original filename>`

The hash prefix ensures:
- No filename collisions (even if two sources serve `report.pdf`)
- Filename encodes content identity (same hash = same file)

### Manifest files

```
data/
└── staging/
    └── acquisition/
        ├── manifest.db            ← SQLite database (queryable)
        └── manifest_export.json   ← JSON export (for teammates)
```

**Sample manifest record:**
```json
{
  "source": "cdc",
  "description": "CDC MMWR Vol 73 No 39 (Oct 2024)",
  "original_url": "https://stacks.cdc.gov/view/cdc/164153/cdc_164153_DS1.pdf",
  "final_url": "https://stacks.cdc.gov/view/cdc/164153/cdc_164153_DS1.pdf",
  "filename": "7501cf051537_cdc_164153_DS1.pdf",
  "filepath": "/path/to/data/raw/cdc/2026/09/7501cf051537_cdc_164153_DS1.pdf",
  "document_type": "pdf",
  "file_size": 670018,
  "sha256": "7501cf051537...",
  "http_status": 200,
  "content_type": "application/pdf",
  "status": "SUCCESS",
  "error_msg": null,
  "attempts": 1,
  "downloaded_at": "2026-09-17T05:37:47+00:00"
}
```

---

## Adding New Sources

1. Create `data_sources/<name>_sources.json`:

```json
[
  {
    "source": "my_source",
    "url": "https://data.example.gov/reports/annual2024.pdf",
    "document_type": "pdf",
    "allowed_domain": "data.example.gov",
    "description": "Annual Health Statistics 2024"
  },
  {
    "source": "my_source",
    "url": "https://data.example.gov/reports/quarterly.pdf",
    "document_type": "pdf",
    "allowed_domain": "data.example.gov",
    "description": "Q3 2024 Quarterly Report"
  }
]
```

2. Test the URLs first:
```bash
curl -sI "https://data.example.gov/reports/annual2024.pdf" | grep "Content-Type"
# Should return: Content-Type: application/pdf
```

3. Run:
```bash
python scripts/run_bulk_download.py --sources my_source
```

---

## Atlas Handoff (For Teammates)

Once the downloader runs, your processing teammate reads from the manifest:

```python
import json
from pathlib import Path

manifest = json.loads(
    Path("data/staging/acquisition/manifest_export.json").read_text()
)

for doc in manifest:
    if doc["status"] == "SUCCESS":
        filepath = doc["filepath"]
        sha256   = doc["sha256"]
        source   = doc["source"]
        # → pass to parser → chunker → Ollama embedder → Qdrant
        process_document(filepath, metadata={
            "source": source,
            "sha256": sha256,
            "original_url": doc["original_url"],
        })
```

The manifest tells the processing team:
- **Which files exist** and where they are on disk
- **What source** they came from (for metadata tagging)
- **The SHA-256** (for deduplication in the vector DB)
- **The original URL** (for citation / provenance)

---

## What is NOT in Git

> ⚠️ **Critical rule for the team: never commit downloaded data.**

The root `.gitignore` excludes:

```gitignore
data/raw/           ← all downloaded source documents
data/staging/       ← manifest DB and JSON exports
*.db                ← SQLite databases
*.pdf               ← downloaded PDFs
*.html              ← downloaded HTML
manifest_export.json
```

**Your Git commits should contain:**
- ✅ Code (`src/`, `tests/`, `scripts/`)
- ✅ Source URL lists (`data_sources/*.json`)
- ✅ Configuration (`requirements.txt`, `pytest.ini`)
- ✅ Documentation (`README.md`)

**Never:**
- ❌ PDFs, HTML files, XML files
- ❌ `manifest.db` or `manifest_export.json`
- ❌ The `data/` directory

---

## Real Download Test Results (Sept 2026)

Pipeline tested live against 15 URLs from 3 sources:

```
════════════════════════════════════════════════════════════
  Download Summary
────────────────────────────────────────────────────────────
  ✅  SUCCESS          13  █████████████
  ♻️   DUPLICATE         2  ██   (same content, 2 URLs — correctly deduplicated)
────────────────────────────────────────────────────────────
  TOTAL                15  |  8.8 MB  |  ~6 seconds
════════════════════════════════════════════════════════════
```

**Deduplication in action:** Two FDA URLs served the same PDF bytes. The second was correctly caught as `DUPLICATE` and not stored twice — demonstrating hash-based dedup works across different URLs from different sources.

---

*Part of [Project Atlas](https://github.com/vishalkannsgit/Project-Atlas) — AI-Native Knowledge Engineering Platform*
