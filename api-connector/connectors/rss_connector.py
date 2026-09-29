"""
connectors/rss_connector.py

Fetches new items from an RSS feed (e.g. government health advisories,
per the Business Proposal Section 3) and converts them into
NormalizedRecord objects.

Why RSS is the simplest connector to build first:
- No authentication needed (most public RSS feeds are open).
- Well-known, standard format -- the `feedparser` library handles all the
  messy XML parsing for us.
- Good template to copy from when building PubMed/NIH next.
"""

from datetime import datetime, timezone
import feedparser

from core.base_connector import BaseConnector
from core.models import NormalizedRecord, SourceType


class RSSConnector(BaseConnector):
    source_name = SourceType.RSS.value

    def __init__(self, feed_url: str):
        """
        Args:
            feed_url: the RSS feed's URL, e.g. a government advisory feed.
        """
        self.feed_url = feed_url

    def fetch(self, since_checkpoint: str | None) -> list[NormalizedRecord]:
        """
        Reads the RSS feed and returns only items published AFTER the
        last checkpoint (or everything, if this is the first run).
        """
        parsed_feed = feedparser.parse(self.feed_url)

        if parsed_feed.bozo:
            # feedparser sets `bozo=True` when the feed is malformed --
            # we raise so with_retry() in base_connector.py can retry,
            # since this is often a temporary network/server glitch.
            raise ValueError(f"Failed to parse RSS feed: {parsed_feed.bozo_exception}")

        since_dt = self._parse_checkpoint(since_checkpoint)

        records: list[NormalizedRecord] = []
        for entry in parsed_feed.entries:
            published_dt = self._get_entry_published_date(entry)

            # Skip items we've already synced before.
            if since_dt and published_dt and published_dt <= since_dt:
                continue

            record = NormalizedRecord(
                source=SourceType.RSS,
                record_id=entry.get("id", entry.get("link", entry.get("title", ""))),
                title=entry.get("title"),
                url=entry.get("link"),
                published_at=published_dt,
                payload={
                    "summary": entry.get("summary", ""),
                    "raw_entry": {k: str(v) for k, v in entry.items()},
                },
                checkpoint_marker=(published_dt or datetime.now(timezone.utc)).isoformat(),
            )
            records.append(record)

        # Sort oldest -> newest so the LAST record's checkpoint_marker
        # (used by base_connector.py) reflects the most recent item.
        records.sort(key=lambda r: r.published_at or datetime.min.replace(tzinfo=timezone.utc))
        return records

    @staticmethod
    def _parse_checkpoint(checkpoint: str | None) -> datetime | None:
        if not checkpoint:
            return None
        try:
            return datetime.fromisoformat(checkpoint)
        except ValueError:
            return None

    @staticmethod
    def _get_entry_published_date(entry) -> datetime | None:
        # feedparser gives a "published_parsed" time struct when available.
        if getattr(entry, "published_parsed", None):
            return datetime(*entry.published_parsed[:6], tzinfo=timezone.utc)
        return None
