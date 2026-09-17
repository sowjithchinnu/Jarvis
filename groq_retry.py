"""Shared bounded retry behavior for Groq API requests."""

from __future__ import annotations

import time
from collections.abc import Callable
from logging import Logger
from typing import TypeVar


MAX_API_ATTEMPTS = 3
RETRY_DELAYS = (1, 2)
MAX_RATE_LIMIT_ATTEMPTS = 2
RATE_LIMIT_RETRY_DELAYS = (1,)
RATE_LIMIT_MESSAGE = (
    "Groq rate limit or quota reached - please wait a moment or check your usage."
)
T = TypeVar("T")


def is_rate_limit_error(error: Exception) -> bool:
    """Return whether an API exception represents throttling or exhausted quota."""
    status_code = getattr(error, "status_code", None)
    if status_code == 429:
        return True

    error_body = getattr(error, "body", None) or getattr(error, "response", None)
    values = [str(error)]
    if error_body is not None:
        values.append(str(error_body))
        if isinstance(error_body, dict):
            values.extend(str(error_body.get(key, "")) for key in ("code", "type", "message"))
        else:
            values.extend(
                str(getattr(error_body, key, ""))
                for key in ("code", "type", "message")
            )
    normalized = " ".join(values).lower().replace("_", "-")
    return "quota" in normalized and any(
        marker in normalized
        for marker in ("exceeded", "insufficient", "reached", "limit")
    )


def retry_after_seconds(error: Exception) -> str | None:
    """Read a provider Retry-After header without assuming a specific SDK error type."""
    response = getattr(error, "response", None)
    headers = getattr(response, "headers", None)
    if headers is None and isinstance(response, dict):
        headers = response.get("headers")
    if not headers:
        return None
    value = headers.get("retry-after") or headers.get("Retry-After")
    return str(value).strip() if value is not None and str(value).strip() else None


def rate_limit_message(error: Exception) -> str:
    retry_after = retry_after_seconds(error)
    if retry_after:
        return f"{RATE_LIMIT_MESSAGE} Retry after {retry_after} seconds."
    return RATE_LIMIT_MESSAGE


def request_with_retry(
    request: Callable[[], T],
    *,
    logger: Logger,
    operation: str,
    before_attempt: Callable[[], None] | None = None,
    on_rate_limit: Callable[[str], None] | None = None,
    log_error_details: bool = True,
) -> T:
    """Run a Groq request with Jarvis's standard retry policy.

    Generic transient failures use the standard three-attempt policy. Rate
    limits and quota errors use a smaller, separately logged two-attempt
    policy. The final exception is intentionally re-raised for the caller.
    """
    attempt = 0
    while attempt < MAX_API_ATTEMPTS:
        if before_attempt:
            before_attempt()
        try:
            return request()
        except Exception as error:
            if before_attempt:
                before_attempt()
            rate_limited = is_rate_limit_error(error)
            status_code = getattr(error, "status_code", None)
            retryable = status_code is None or status_code >= 500
            max_attempts = MAX_RATE_LIMIT_ATTEMPTS if rate_limited else MAX_API_ATTEMPTS
            if rate_limited:
                message = rate_limit_message(error)
                if on_rate_limit:
                    on_rate_limit(message)
                if attempt == max_attempts - 1:
                    logger.error(
                        "%s rate limit/quota failure after %d attempt(s): %s",
                        operation,
                        attempt + 1,
                        message,
                    )
                    raise
            elif not retryable or attempt == max_attempts - 1:
                if log_error_details:
                    logger.exception(
                        "%s failed after %d attempt(s)", operation, attempt + 1
                    )
                else:
                    logger.error(
                        "%s failed after %d attempt(s).", operation, attempt + 1
                    )
                raise
            delays = RATE_LIMIT_RETRY_DELAYS if rate_limited else RETRY_DELAYS
            delay = delays[attempt]
            if rate_limited:
                logger.warning(
                    "%s rate limit/quota response; retrying in %ss: %s",
                    operation,
                    delay,
                    rate_limit_message(error),
                )
            elif log_error_details:
                logger.warning(
                    "%s failed; retrying in %ss: %s", operation, delay, error
                )
            else:
                logger.warning("%s failed; retrying in %ss.", operation, delay)
            time.sleep(delay)
            attempt += 1
