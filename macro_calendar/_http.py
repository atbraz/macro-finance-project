"""Shared HTTP client with retry. Polite to free APIs."""
from __future__ import annotations

import httpx
from tenacity import (
    retry, retry_if_exception_type, stop_after_attempt,
    wait_exponential, before_sleep_log,
)
import logging

from .config import HTTP_MAX_ATTEMPTS, HTTP_TIMEOUT_S, USER_AGENT

log = logging.getLogger(__name__)

_client: httpx.Client | None = None


def client() -> httpx.Client:
    global _client
    if _client is None:
        _client = httpx.Client(
            timeout=HTTP_TIMEOUT_S,
            headers={"User-Agent": USER_AGENT},
            follow_redirects=True,
        )
    return _client


_retry = retry(
    stop=stop_after_attempt(HTTP_MAX_ATTEMPTS),
    wait=wait_exponential(multiplier=1, min=1, max=20),
    retry=retry_if_exception_type((httpx.HTTPError, httpx.TimeoutException)),
    before_sleep=before_sleep_log(log, logging.WARNING),
    reraise=True,
)


@_retry
def get(url: str, **params) -> httpx.Response:
    r = client().get(url, params=params or None)
    r.raise_for_status()
    return r
