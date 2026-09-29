"""
core/retry.py

Shared retry logic used by EVERY connector when calling external APIs
(PubMed, NIH, RSS feeds) or Atlas's ingestion API.

Why this exists:
External APIs sometimes fail temporarily -- a slow network, a server that's
briefly overloaded, or a rate limit. Instead of giving up immediately (or
hammering the API repeatedly with no delay), we retry a few times with an
increasing wait between attempts. This is called "exponential backoff."

Example: attempt 1 fails -> wait 1s -> attempt 2 fails -> wait 2s ->
attempt 3 fails -> wait 4s -> attempt 4 fails -> give up, raise the error.
"""

import time
import logging
from typing import Callable, TypeVar

logger = logging.getLogger("atlas_connectors.retry")

T = TypeVar("T")


class RetryExhaustedError(Exception):
    """Raised when all retry attempts have failed."""
    def __init__(self, last_exception: Exception, attempts: int):
        self.last_exception = last_exception
        self.attempts = attempts
        super().__init__(
            f"All {attempts} attempts failed. Last error: {last_exception}"
        )


def with_retry(
    func: Callable[[], T],
    max_attempts: int = 4,
    base_delay_seconds: float = 1.0,
    max_delay_seconds: float = 30.0,
) -> T:
    """
    Runs `func` and retries it on failure using exponential backoff.

    Args:
        func: a zero-argument function to call (use a lambda to pass args)
        max_attempts: how many total tries before giving up (default 4)
        base_delay_seconds: how long to wait after the FIRST failure
        max_delay_seconds: the wait time will never exceed this, even if
                            the doubling would go higher

    Returns:
        Whatever `func()` returns, on the first successful attempt.

    Raises:
        RetryExhaustedError: if every attempt fails.
    """
    last_exception: Exception | None = None

    for attempt in range(1, max_attempts + 1):
        try:
            return func()
        except Exception as e:
            last_exception = e
            if attempt == max_attempts:
                logger.error(
                    f"Retry exhausted after {attempt} attempts. Error: {e}"
                )
                break

            delay = min(base_delay_seconds * (2 ** (attempt - 1)), max_delay_seconds)
            logger.warning(
                f"Attempt {attempt}/{max_attempts} failed with: {e}. "
                f"Retrying in {delay:.1f}s..."
            )
            time.sleep(delay)

    raise RetryExhaustedError(last_exception, max_attempts)
