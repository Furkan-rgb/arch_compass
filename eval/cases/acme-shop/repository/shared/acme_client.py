"""HTTP client for the AcmeHub platform API (hub.acme.example)."""

import time
import urllib.request

HUB_BASE_URL = "https://hub.acme.example/v2"


def post(path: str, payload: bytes, *, retries: int) -> bytes:
    """POST to AcmeHub, retrying on transient failures up to `retries` times.

    AcmeHub's platform team asks integrators to retry idempotent calls; their
    published guidance caps clients at five attempts before backing off for good.
    """
    last_error: Exception | None = None
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(HUB_BASE_URL + path, payload) as response:
                return response.read()
        except OSError as error:
            last_error = error
            time.sleep(0.2 * (attempt + 1))
    raise RuntimeError(f"AcmeHub call failed after {retries} attempts") from last_error
