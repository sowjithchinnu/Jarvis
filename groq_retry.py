"""Shared bounded retry behavior for Groq API requests."""

from __future__ import annotations

import time
from collections.abc import Callable
from logging import Logger
from typing import TypeVar


MAX_API_ATTEMPTS = 3
RETRY_DELAYS = (1, 2)
T = TypeVar("T")


def request_with_retry(
    request: Callable[[], T],
    *,
    logger: Logger,
    operation: str,
    before_attempt: Callable[[], None] | None = None,
    log_error_details: bool = True,
) -> T:
    """Run a Groq request with Jarvis's standard retry policy.

    Requests retry when the status is unknown, rate-limited, or server-side
    (HTTP 429 or 5xx). The final exception is intentionally re-raised so the
    caller can return an operation-specific, safe error string.
    """
    for attempt in range(MAX_API_ATTEMPTS):
        if before_attempt:
            before_attempt()
        try:
            return request()
        except Exception as error:
            if before_attempt:
                before_attempt()
            status_code = getattr(error, "status_code", None)
            retryable = (
                status_code is None or status_code == 429 or status_code >= 500
            )
            if not retryable or attempt == MAX_API_ATTEMPTS - 1:
                if log_error_details:
                    logger.exception(
                        "%s failed after %d attempt(s)", operation, attempt + 1
                    )
                else:
                    logger.error(
                        "%s failed after %d attempt(s).", operation, attempt + 1
                    )
                raise
            delay = RETRY_DELAYS[attempt]
            if log_error_details:
                logger.warning(
                    "%s failed; retrying in %ss: %s", operation, delay, error
                )
            else:
                logger.warning("%s failed; retrying in %ss.", operation, delay)
            time.sleep(delay)
