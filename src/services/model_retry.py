"""Model-call failure classification and retry backoff.

Distinguishes retryable transport/latency/rate-limit failures from permanent
configuration failures (auth, invalid model) and transient-but-unproductive
failures (malformed model JSON), so retry and fallback-model policy can react
appropriately instead of blindly retrying every error.
"""

from __future__ import annotations

import random
import time

import httpx

# Failure kinds
TIMEOUT = "timeout"
CONNECTIVITY = "connectivity"
RATE_LIMIT = "rate_limit"
SERVER_ERROR = "server_error"
AUTH = "auth"
BAD_REQUEST = "bad_request"
INVALID_MODEL = "invalid_model"
MALFORMED_JSON = "malformed_json"
TOO_LARGE = "too_large"
UNKNOWN = "unknown"

# Kinds where retrying the same model is productive.
_RETRYABLE = {TIMEOUT, CONNECTIVITY, RATE_LIMIT, SERVER_ERROR, MALFORMED_JSON}
# Kinds that indicate a configuration problem; no model change or retry helps.
_PERMANENT = {AUTH, INVALID_MODEL}

BACKOFF_BASE_SECONDS = 0.5
BACKOFF_CAP_SECONDS = 8.0
BACKOFF_JITTER = 0.25


class ModelCallError(Exception):
    """Raised when a model call fails after retries, with a classifier kind."""

    def __init__(
        self,
        kind: str,
        *,
        model: str | None = None,
        status: int | None = None,
        message: str | None = None,
    ):
        super().__init__(message or kind)
        self.kind = kind
        self.model = model
        self.status = status


def classify_status(status_code: int | None) -> str:
    if status_code is None:
        return UNKNOWN
    if status_code in (401, 403):
        return AUTH
    if status_code in (408, 429):
        return RATE_LIMIT if status_code == 429 else TIMEOUT
    if 500 <= status_code < 600:
        return SERVER_ERROR
    if status_code in (400, 422):
        return BAD_REQUEST
    if status_code == 404:
        return INVALID_MODEL
    return UNKNOWN


def classify_exception(exc: Exception, status: int | None = None) -> str:
    if status is not None:
        return classify_status(status)
    if isinstance(exc, httpx.TimeoutException):
        return TIMEOUT
    if isinstance(exc, httpx.ConnectError) or isinstance(exc, httpx.ConnectTimeout):
        return CONNECTIVITY
    if isinstance(exc, httpx.TooManyRedirects):
        return CONNECTIVITY
    if isinstance(exc, httpx.HTTPStatusError):
        return classify_status(exc.response.status_code)
    return UNKNOWN


def is_retryable(kind: str) -> bool:
    return kind in _RETRYABLE


def is_permanent(kind: str) -> bool:
    return kind in _PERMANENT


def backoff_seconds(attempt: int, *, base: float = BACKOFF_BASE_SECONDS,
                    cap: float = BACKOFF_CAP_SECONDS, jitter: float = BACKOFF_JITTER) -> float:
    """Exponential backoff with jitter, capped. `attempt` is 0-based."""
    delay = min(cap, base * (2 ** max(0, attempt)))
    if jitter > 0:
        delay *= 1 + random.uniform(0, jitter)
    return round(delay, 2)


def sleep_backoff(attempt: int) -> float:
    delay = backoff_seconds(attempt)
    time.sleep(delay)
    return delay