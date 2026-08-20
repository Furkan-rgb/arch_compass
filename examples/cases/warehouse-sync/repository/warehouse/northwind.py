"""Northwind, the warehouse this service has run against since it was written."""

from __future__ import annotations

from sync.ports import WarehouseFeed
from transport.http import get_json

#: Northwind pages its stock endpoint and will not return more than this in one response.
NORTHWIND_PAGE_LIMIT = 200


class NorthwindFeed(WarehouseFeed):
    """Northwind's stock API."""

    def __init__(self, endpoint: str) -> None:
        self._endpoint = endpoint

    def current_levels(self) -> dict[str, int]:
        levels: dict[str, int] = {}
        page = 0
        while True:
            body = get_json(f"{self._endpoint}/stock?page={page}")
            rows = body.get("rows", [])
            if not rows:
                return levels
            for row in rows:
                levels[str(row["sku"])] = int(row["on_hand"])
            page += 1
