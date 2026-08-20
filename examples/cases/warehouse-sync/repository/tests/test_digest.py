"""What the operator's nightly digest says.

The only test this service has. Reconciliation itself is exercised by running it against
the warehouse's sandbox account, which is why nothing here substitutes the feed.
"""

from __future__ import annotations

from reporting.digest import build


def test_a_changed_level_appears_once() -> None:
    digest = build({"sku-1": 4, "sku-2": 9})

    assert "2 stock levels changed overnight." in digest
    assert "  sku-1: now 4" in digest
    assert "  sku-2: now 9" in digest


def test_an_unchanged_night_still_produces_a_digest() -> None:
    assert build({}).startswith("0 stock levels changed overnight.")
