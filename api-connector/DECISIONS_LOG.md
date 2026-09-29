# Project Atlas — Data Acquisition / API Connector Platform
## Decisions Log (living document)

This file is updated as each piece is built. At project completion, this becomes
the source material for the final technical documentation.

**Owner:** [Your Name]
**Role:** Data Acquisition Engineer (Epic 2 — API Connectors, per Project Atlas backlog)
**Scope:** PubMed connector, NIH connector, RSS connector, shared connector framework
(auth, retry, checkpointing, health checks, contract tests)
**Development environment:** Antigravity — Google's AI-powered agentic coding
IDE (built on VS Code, uses Gemini models). In simple terms: it's a code editor
where you describe what you need in plain language, and an AI agent writes,
tests, and checks the code for you. Used here for writing, running, and
verifying the connector code locally before final deployment.
**Documentation style rule:** All documentation in this log — and the final
project document generated from it — uses simple, plain English. Avoid heavy
jargon; explain technical terms in plain words wherever they first appear.
This is intentional so the document is easy to understand for reviewers who
are not deep in the technical details.

---

## Step 0 — Project Structure

**What:** Created a folder structure separating shared infrastructure (`core/`) from
specific connectors (`connectors/`), the Atlas API client (`clients/`), and tests (`tests/`).

**Why this structure:**
- Per Project Atlas NFR: "Extensible connector framework" — new connectors (WHO, CDC,
  future sources) should be addable without touching shared logic.
- Per NFR: "Domain-independent architecture" — `core/` has zero healthcare-specific code;
  only files inside `connectors/` know about PubMed/NIH/RSS specifics.
- Separating `clients/atlas_client.py` means if Atlas's ingestion API changes, only
  one file needs updating — not every connector.

**Tools/tech chosen:** Python (matches Atlas's FastAPI backend stack, per Business
Proposal Section 10 — keeps the whole platform in one language for the team).

---

## Step 1 — Component Contract (`core/models.py` + `core/base_connector.py`)

**What:** Built two files:
1. `models.py` — defines `NormalizedRecord` (the one shared data shape all
   connectors must output), plus supporting models for run results, errors,
   and health status.
2. `base_connector.py` — an abstract base class (`BaseConnector`) that every
   connector must inherit from. It defines 4 required methods
   (`fetch`, `get_checkpoint`, `set_checkpoint`, `health_check`) and one
   shared orchestration method (`run()`) that all connectors reuse as-is.

**Why Pydantic (not plain dicts or dataclasses):**
- Atlas's backend is FastAPI, which is built on Pydantic — using the same
  library means zero friction / no format mismatch when Atlas validates
  incoming data on its side.
- Pydantic validates required fields and types automatically. If a connector
  has a bug (e.g., forgets to set `record_id`), it fails immediately and
  loudly, inside the connector — not silently somewhere downstream in Atlas.

**Why an abstract base class (Python's ABC), not just a plain class:**
- Physically prevents a future connector from being written without
  implementing the required methods — Python raises an error at creation
  time if any required method is missing.
- Satisfies Atlas's NFR "Extensible connector framework" — this is literally
  the checklist a future engineer follows to add a 4th connector (e.g. WHO,
  CDC — both explicitly named as future sources in the Business Proposal).

**Why the `run()` method lives in the BASE class, not repeated in every connector:**
- `run()` is the same for every connector: get checkpoint → fetch (with retry)
  → send to Atlas (with retry) → save new checkpoint → return result.
- Writing this once in `base_connector.py` means PubMed/NIH/RSS connectors
  only need to implement their source-specific logic (`fetch`), not
  re-implement retry handling, checkpointing, or result formatting.
- This is what makes "Connector Contract Tests" (Task 8) possible later —
  since orchestration is identical, we can run ONE test suite against all
  three connectors and know they behave consistently.

**Key design choice — checkpoint safety:**
`run()` only saves a new checkpoint based on records that were CONFIRMED
sent to Atlas (`sent_count > 0`), not just fetched. This prevents data loss:
if Atlas's API is down and sending fails, we don't advance the checkpoint,
so next run will correctly retry the same records instead of skipping them.

**Alternative considered and rejected:** Using Python `dataclasses` instead
of Pydantic — rejected because dataclasses don't validate types/values at
runtime, which matters here since we're validating data coming from
unpredictable external APIs.

**Setup issues encountered (for future reference):**
- `ModuleNotFoundError: No module named 'pydantic'` — happened because
  `pip install pydantic` hadn't completed successfully before `pip freeze`
  was run. Fixed by re-running `pip install pydantic` with the venv active,
  confirmed with `pip show pydantic`, then re-saving `requirements.txt`.
- Lesson: always verify a package installed (`pip show <package>`) before
  assuming it's there — especially before freezing requirements.

**Status: ✅ Step 1 complete and verified working (`quick_check.py` passes).**

---

## Step 2 — Retry/Backoff Logic + Secret Management

**What:** Built four files:
1. `core/retry.py` — a reusable `with_retry()` function that any connector
   (or the shared `run()` method) can wrap around a risky call (an API
   request, a send to Atlas).
2. `core/auth.py` — a single, safe place to load API keys and secrets from
   environment variables, never hardcoded in code.
3. `.env.example` — a template showing which secrets are needed, safe to
   commit to git (contains no real values).
4. `.gitignore` — prevents the real `.env` file, the `venv/` folder, and
   cache files from ever being committed to version control.

**Why exponential backoff (increasing wait time), not fixed delay:**
- If an API is briefly overloaded, retrying instantly (or at a fixed short
  delay) can make things worse -- like knocking on a busy door faster and
  faster. Waiting longer each time gives the external service room to
  recover, which is standard practice for calling any third-party API.
- Satisfies Atlas's NFR: "Fault-tolerant workflows with retries."

**Why a max delay cap (`max_delay_seconds`):**
- Without a cap, the wait time doubles forever (1s, 2s, 4s, 8s, 16s, 32s...)
  and could eventually mean waiting several minutes for one retry. Capping
  it (default 30s) keeps retries reasonable even if `max_attempts` is
  increased later.

**Why secrets load from environment variables, not a config file with
values in it:**
- A file with real API keys inside it can accidentally get committed to
  git and leaked. Environment variables (loaded via `.env` locally, or
  set directly by Docker/Kubernetes in production) never need to be
  written into a file that gets version-controlled.
- Satisfies Atlas's NFR: "Secure role-based administration" and general
  security best practice for handling credentials.

**Why `python-dotenv` library for local development:**
- In production, Docker/Kubernetes sets real environment variables
  directly -- no extra tooling needed there.
- Locally, there's no Docker/Kubernetes running, so `python-dotenv` reads
  a `.env` file and loads those values into the environment the same way,
  meaning the connector code itself never needs to know or care whether
  it's running locally or in production -- `get_secret()` works identically
  either way.

**Why some secrets are required and some are optional:**
- `ATLAS_API_URL` and `ATLAS_API_KEY` are required -- without these, no
  connector can ever send data anywhere, so failing loudly and immediately
  is correct.
- `PUBMED_API_KEY` and `NIH_API_KEY` are optional -- these APIs still work
  without a key (just with a lower rate limit), so we don't want to block
  the whole connector from running just because a key wasn't set.

**Tools/tech chosen:** `python-dotenv` (industry-standard, lightweight
library for loading `.env` files in local development).

**Action needed from you:** Run `pip install python-dotenv` in your
activated venv, then copy `.env.example` to a real `.env` file and fill in
your actual Atlas API URL/key once you know them.

---

## Step 3 — Incremental Sync & Checkpointing (Task 6)

**What:** Built `core/checkpoint.py` — a small storage system that
remembers, per connector, how far it successfully synced last time.

**Why this exists (plain words):** Like a bookmark in a book -- instead of
re-reading a document from page 1 every time, the connector remembers where
it left off and only fetches what's new. Without this, every run would
re-download EVERYTHING from every source, every time.

**Why a local JSON file for storage (not a database) at this stage:**
- Zero extra setup needed -- works immediately during development and
  meets the Thursday deadline without needing a database running.
- The storage mechanism is fully isolated inside this one file. Every
  connector only ever calls `get_checkpoint()` / `set_checkpoint()` via
  `base_connector.py` -- none of them touch the file directly. This means
  if the team later decides to move checkpoints into PostgreSQL (which
  Atlas already uses elsewhere, per the Business Proposal's tech stack),
  only `checkpoint.py` needs to change -- zero changes needed in any
  connector or in `base_connector.py`.

**Why a `Lock()` (thread-safety):**
- If two connectors happen to save a checkpoint at the exact same instant,
  writing to the same file at the same time could corrupt it. The lock
  makes sure only one save happens at a time, safely.

**Why checkpoints are keyed by `source_name` (e.g. "pubmed") in one shared
file, rather than one file per connector:**
- Simpler to inspect/debug -- one file shows the sync status of every
  connector at a glance, which is useful for the health checks we'll build
  next (Task 7).

**What happens on first run:** `get_checkpoint()` returns `None` if a
connector has never run before -- `base_connector.py`'s `run()` method
already handles this correctly (passes `None` to `fetch()`, meaning "do a
full sync this time").

**Status: ✅ Step 3 complete and verified working.**
`quick_check.py` confirms: checkpoint starts as `None` on first run, and
correctly saves/reads back `2026-09-18T10:00:00` after `set_checkpoint()`.

**Setup issue encountered (for future reference):** Test code was
accidentally pasted into `core/checkpoint.py` instead of
`tests/quick_check.py`, causing a circular import error (the file tried to
import from itself). Fixed by re-pasting the correct content into each
file. Lesson: always check the file-name comment at the top of a code
block matches the file currently open before pasting.

---

## Step 4 — Connector Health Checks (Task 7)

**What:** Built `core/health.py` — records the outcome of every connector
run, and answers "is this connector healthy right now?" with one of three
simple states: OK, DEGRADED, or DOWN.

**Why this exists (plain words):** Without this, a connector could quietly
break -- an expired API key, a source website changing its format, a
network block -- and nobody would notice until someone realizes data
stopped updating, possibly days later. This gives an instant status check.

**Why three simple states (OK / DEGRADED / DOWN), not something more
complex:**
- Simple enough that a monitoring dashboard (Epic 6, built by someone else
  on the team) can display it as a single colored dot/badge without extra
  translation logic.
- Matches how most real monitoring systems present status (e.g. status
  pages like "operational / partial outage / major outage").

**Why "stale" also counts as DOWN, even with no explicit error:**
- A connector that silently stopped running (e.g. its scheduled job was
  removed or crashed outside of its own error handling) would otherwise
  show as fine forever, because there's no NEW error being recorded. The
  staleness check (`STALE_AFTER_HOURS`, default 26 hours) catches this
  "silence is also a problem" case.

**Why a separate file/store from `checkpoint.py`, even though both are
JSON files:**
- Checkpoints answer "where do I resume fetching from" (a sync/data
  concern). Health answers "is this thing currently working" (an
  operational/monitoring concern). Keeping them separate means a future
  change to monitoring logic (e.g. moving health data into a proper
  monitoring tool like Prometheus) doesn't risk touching sync logic at all.

**Connects to:** Atlas's NFR "Observability for pipelines" and the
project's Epic 6 (Monitoring) / Row #28 in the project tracker table.

**Status: ✅ Step 4 complete and verified working.**
`quick_check.py` confirms: a successful run reports `status=OK` with a
timestamp, and a failed run reports `status=DOWN` with the error message
preserved.

---

## Step 5 — Wiring Checkpoint + Health Into `base_connector.py`

**What:** Updated `core/base_connector.py`. Previously, `get_checkpoint`,
`set_checkpoint`, and `health_check` were "abstract" -- meaning every
connector (PubMed, NIH, RSS) would have had to implement its own version
of checkpoint saving and health tracking. Now that we've built ONE shared
system for both (`checkpoint.py` in Step 3, `health.py` in Step 4), those
three methods are no longer abstract -- `BaseConnector` provides a working
default implementation for all of them automatically.

**Why this change matters (plain words):** Every future connector
(PubMed, NIH, RSS, and any later addition) now only needs to write ONE
method: `fetch()`. Everything else -- checkpointing, health tracking,
retries, sending to Atlas -- is already built and shared. This means less
code to write per connector, and far less chance of copy-paste mistakes,
since there's simply less left to copy.

**Why `run()` now also calls `record_run_outcome()`:** Previously,
`health.py` worked correctly on its own, but nothing was actually calling
it during a real connector run. Now, every time `run()` finishes --
whether it succeeded, partially succeeded, or failed -- it automatically
records the outcome, so `health_check()` always has accurate, up-to-date
information without any extra work needed inside individual connectors.

**Small fix included:** `run()` now specifically catches
`RetryExhaustedError` (from `core/retry.py`) instead of a generic
`Exception` -- this makes it clear in the code that we're only handling
the specific "all retries failed" case, not accidentally swallowing
unrelated bugs.

**Status:** Ready for Step 6 -- building the first real connector (RSS,
the simplest one) using this simplified contract.

**Status: ✅ Step 5 complete and verified.** Re-ran `quick_check.py` after
the change -- identical output to before, confirming the rewiring inside
`base_connector.py` did not break any existing functionality.

---

## Step 6 — Atlas API Client + First Real Connector: RSS (Task 3)

**What:** Built two files:
1. `clients/atlas_client.py` — the ONLY file that knows how to call
   Atlas's ingestion API (sends a batch of records via HTTP POST).
2. `connectors/rss_connector.py` — the first real, working connector.
   Reads an RSS feed and converts each entry into a `NormalizedRecord`.

**Why `atlas_client.py` is separate from every connector:** If Atlas's API
address, request format, or authentication changes later, only this ONE
file needs updating. Every connector calls `send_records_to_atlas()`
without knowing or caring about the actual HTTP details underneath.

**Why `response.raise_for_status()` is used:** This makes `requests`
automatically raise an error for any bad response (like a 500 server error
or 401 unauthorized) from Atlas. That error is then caught by
`core/retry.py`'s `with_retry()`, so a temporary Atlas outage triggers a
normal retry instead of silently failing or crashing the whole connector.

**Why RSS was built first, before PubMed/NIH:**
- No authentication required -- simpler to get working end-to-end quickly.
- Uses a very standard format (RSS/Atom), handled by a mature, well-tested
  library (`feedparser`), so little custom parsing code is needed.
- Serves as a working template/reference when building the PubMed and NIH
  connectors next -- proves the whole chain (fetch → normalize → send →
  checkpoint → health) works before adding more source-specific complexity.

**Why `feedparser` library:** Industry-standard Python library
specifically built for reading RSS/Atom feeds -- handles many edge cases
and format quirks in real-world feeds that would be error-prone to parse
by hand.

**Why we raise an error when `parsed_feed.bozo` is True:** `feedparser`
sets this flag when a feed is malformed or fails to load properly. Raising
here (rather than silently returning an empty list) lets the shared retry
logic in `base_connector.py` retry automatically, since this is often a
temporary issue (server hiccup) rather than a permanent one.

**Why records are sorted oldest → newest before returning:** The shared
`run()` method in `base_connector.py` saves the checkpoint based on the
LAST record in the list. Sorting ensures that "last" always means "most
recently published," so the next run correctly resumes from the right
point, regardless of the order the feed happens to list items in.

**Tools/tech chosen:** `feedparser` (for RSS parsing), `requests` (for
calling Atlas's API — a standard, widely-used Python HTTP library).

**Action needed from you:** Run
`pip install feedparser requests` in your activated venv, then
`pip freeze > requirements.txt` to save them.

---

