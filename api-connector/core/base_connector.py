"""
core/base_connector.py

THE CONTRACT. Every connector (PubMed, NIH, RSS, and any future source)
MUST inherit from BaseConnector and implement ONE method: fetch().

Why only fetch() now (updated in Step 5):
Checkpointing (core/checkpoint.py) and health tracking (core/health.py)
are now SHARED services used automatically by every connector -- there's
no reason to make each connector re-implement them. This keeps each real
connector file (PubMed, NIH, RSS) short and focused only on what's unique
to that source: how to call its API and how to shape its data.

Why an abstract base class (ABC):
- Python's ABC module physically prevents anyone from creating a connector
  that "forgets" to implement fetch() -- it fails immediately at import
  time, not silently in production.
- Satisfies Atlas's NFR: "Extensible connector framework" -- a future
  engineer adding a WHO or CDC connector has exactly one method to write.

This file has ZERO healthcare-specific logic -- satisfies the
"domain-independent architecture" NFR from the Business Proposal.
"""

from abc import ABC, abstractmethod
from datetime import datetime
from core.models import NormalizedRecord, ConnectorRunResult, ConnectorHealth


class BaseConnector(ABC):
    """
    Abstract base class defining the required interface for all connectors.
    Subclasses only need to set `source_name` and implement `fetch()`.
    """

    source_name: str  # e.g. "pubmed", "nih", "rss" -- set by each subclass

    @abstractmethod
    def fetch(self, since_checkpoint: str | None) -> list[NormalizedRecord]:
        """
        Pull data from the external source and return it as a list of
        NormalizedRecord objects.

        `since_checkpoint`: the last saved checkpoint marker (e.g. a timestamp
        or an ID). If None, this is a full sync (first run).

        Each connector implements this differently (PubMed = API call + XML
        parsing, RSS = feed parsing) but the OUTPUT shape is always the same.
        """
        raise NotImplementedError

    def get_checkpoint(self) -> str | None:
        """Read the last successfully saved checkpoint for this connector.
        Shared implementation -- backed by core/checkpoint.py. Subclasses
        do not need to override this."""
        from core.checkpoint import get_checkpoint
        return get_checkpoint(self.source_name)

    def set_checkpoint(self, marker: str) -> None:
        """Persist a new checkpoint after a successful run.
        Shared implementation -- backed by core/checkpoint.py."""
        from core.checkpoint import set_checkpoint
        set_checkpoint(self.source_name, marker)

    def health_check(self) -> ConnectorHealth:
        """Return current health status of this connector.
        Shared implementation -- backed by core/health.py."""
        from core.health import check_health
        return check_health(self.source_name)

    def run(self) -> ConnectorRunResult:
        """
        The standard orchestration flow used by ALL connectors.
        Subclasses do NOT override this -- they only implement fetch().

        This method is what actually gets called by a scheduler (cron,
        Temporal, etc.) -- it's the single, consistent entry point.
        """
        from core.retry import with_retry, RetryExhaustedError
        from core.health import record_run_outcome
        from clients.atlas_client import send_records_to_atlas
        from core.models import ConnectorRunStatus, ConnectorError

        started_at = datetime.utcnow()
        errors: list[ConnectorError] = []
        records: list[NormalizedRecord] = []

        checkpoint = self.get_checkpoint()

        try:
            records = with_retry(lambda: self.fetch(checkpoint))
        except RetryExhaustedError as e:
            errors.append(ConnectorError(error_type="fetch_failed", message=str(e)))
            record_run_outcome(self.source_name, "failed", error_message=str(e))
            return ConnectorRunResult(
                source=self.source_name,
                status=ConnectorRunStatus.FAILED,
                records_fetched=0,
                records_sent_to_atlas=0,
                errors=errors,
                next_checkpoint=checkpoint,
                started_at=started_at,
                finished_at=datetime.utcnow(),
            )

        sent_count = 0
        for record in records:
            try:
                with_retry(lambda: send_records_to_atlas([record]))
                sent_count += 1
            except RetryExhaustedError as e:
                errors.append(ConnectorError(error_type="send_failed", message=str(e)))

        # Save checkpoint only up to what we actually confirmed was sent
        new_checkpoint = records[-1].checkpoint_marker if records else checkpoint
        if sent_count > 0:
            self.set_checkpoint(new_checkpoint)

        status = ConnectorRunStatus.SUCCESS
        if errors and sent_count == 0:
            status = ConnectorRunStatus.FAILED
        elif errors:
            status = ConnectorRunStatus.PARTIAL

        record_run_outcome(
            self.source_name,
            status.value,
            error_message=(errors[-1].message if errors else None),
        )

        return ConnectorRunResult(
            source=self.source_name,
            status=status,
            records_fetched=len(records),
            records_sent_to_atlas=sent_count,
            errors=errors,
            next_checkpoint=new_checkpoint,
            started_at=started_at,
            finished_at=datetime.utcnow(),
        )
