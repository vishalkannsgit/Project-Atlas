from core.models import NormalizedRecord, SourceType
from core.auth import get_atlas_api_url
from core.retry import with_retry
from core.checkpoint import get_checkpoint, set_checkpoint
from core.health import record_run_outcome, check_health
from connectors.rss_connector import RSSConnector

record = NormalizedRecord(
    source=SourceType.PUBMED,
    record_id="TEST123",
    payload={"note": "hello world"},
    checkpoint_marker="2026-09-17"
)
print(record)

print("Atlas URL loaded:", get_atlas_api_url())

attempt_counter = {"count": 0}
def flaky():
    attempt_counter["count"] += 1
    if attempt_counter["count"] < 3:
        raise Exception("Simulated failure")
    return "Success on attempt " + str(attempt_counter["count"])

print(with_retry(flaky))

print("Checkpoint before:", get_checkpoint("pubmed"))
set_checkpoint("pubmed", "2026-09-18T10:00:00")
print("Checkpoint after:", get_checkpoint("pubmed"))

record_run_outcome("pubmed", "success")
print("Health after success:", check_health("pubmed"))

record_run_outcome("nih", "failed", error_message="Connection timed out")
print("Health after failure:", check_health("nih"))

rss = RSSConnector(feed_url="https://www.nasa.gov/feed/")
test_records = rss.fetch(since_checkpoint=None)
print(f"RSS fetched {len(test_records)} records")
if test_records:
    print("First record title:", test_records[0].title)
