"""The HTTP calls this service makes, in one place."""

from __future__ import annotations

from typing import Any

#: How many times a failed HTTP request is retried before the caller is told it failed.
RETRY_LIMIT = 3


def get_json(url: str) -> dict[str, Any]:
    """Fetch and decode one JSON document, retrying a failed request."""

    last_error = ""
    for _ in range(RETRY_LIMIT):
        response = _request(url)
        if response is not None:
            return response
        last_error = f"no response from {url}"
    raise RuntimeError(last_error)


def _request(url: str) -> dict[str, Any] | None:
    # Stands in for the real client's request.
    return {"rows": [], "url": url}
