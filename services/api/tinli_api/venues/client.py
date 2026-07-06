"""Shared HTTP layer for venue adapters.

Every outbound request carries an identifiable User-Agent and retries with
exponential backoff + jitter. Kalshi 429s carry no Retry-After header
(docs/VENUES.md), so blind backoff is the only correct strategy.
"""

import os
import random
import time

import httpx

DEFAULT_UA = "tinli/0.1 (+https://tinli.dev)"
MAX_TRIES = 4
BASE_DELAY_S = 0.5

_client: httpx.Client | None = None


class VenueHTTPError(Exception):
    """A venue request failed after all retries."""


def _get_client() -> httpx.Client:
    global _client
    if _client is None:
        _client = httpx.Client(
            headers={
                "User-Agent": os.environ.get("TINLI_USER_AGENT", DEFAULT_UA),
                "Accept": "application/json",
            },
            timeout=15.0,
        )
    return _client


def get_json(url: str, params: dict | None = None):
    delay = BASE_DELAY_S
    last_error: Exception | None = None
    for attempt in range(MAX_TRIES):
        try:
            resp = _get_client().get(url, params=params)
            if resp.status_code == 429 or resp.status_code >= 500:
                last_error = VenueHTTPError(f"HTTP {resp.status_code} from {url}")
            else:
                resp.raise_for_status()
                return resp.json()
        except httpx.TransportError as exc:
            last_error = exc
        if attempt < MAX_TRIES - 1:
            time.sleep(delay + random.uniform(0, delay))
            delay *= 2
    raise VenueHTTPError(f"giving up on {url} after {MAX_TRIES} tries") from last_error
