"""
clients/atlas_client.py

This is the ONLY file that knows how to talk to Atlas's ingestion API.
Every connector sends its data through here -- no connector calls Atlas
directly on its own.

Why this matters (plain words):
If Atlas's API address, request format, or authentication method ever
changes, only this ONE file needs to be updated. No connector code
(PubMed, NIH, RSS) needs to change at all.
"""

import logging
import requests

from core.auth import get_atlas_api_url, get_atlas_api_key
from core.models import NormalizedRecord

logger = logging.getLogger("atlas_connectors.atlas_client")

# How long to wait for Atlas to respond before treating the call as failed
# (this failure then gets caught by core/retry.py's with_retry wrapper).
REQUEST_TIMEOUT_SECONDS = 15


def send_records_to_atlas(records: list[NormalizedRecord]) -> dict:
    """
    Sends a batch of normalized records to Atlas's ingestion API.

    Args:
        records: one or more NormalizedRecord objects, already validated
                  by Pydantic (see core/models.py).

    Returns:
        The parsed JSON response from Atlas on success.

    Raises:
        requests.RequestException: on any network/HTTP failure -- this is
        caught by core/retry.py's with_retry(), which will retry automatically.
    """
    url = get_atlas_api_url()
    api_key = get_atlas_api_key()

    payload = {
        "records": [record.model_dump(mode="json") for record in records]
    }

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
    }

    logger.info(f"Sending {len(records)} record(s) to Atlas at {url}")

    response = requests.post(
        url,
        json=payload,
        headers=headers,
        timeout=REQUEST_TIMEOUT_SECONDS,
    )

    # Raises requests.HTTPError for 4xx/5xx responses -- caught by with_retry
    # upstream, so a temporary 503 from Atlas triggers a normal retry.
    response.raise_for_status()

    logger.info(f"Successfully sent {len(records)} record(s) to Atlas")
    return response.json()
