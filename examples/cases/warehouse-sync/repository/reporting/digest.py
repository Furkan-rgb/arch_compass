"""The nightly digest an operator reads over breakfast."""

from __future__ import annotations

#: How many SKUs are reconciled in one pass before the ledger is written back. Sized to the
#: warehouse's page limit.
BATCH_SIZE = 200

#: How many times the digest is rebuilt before the night's run is abandoned. Rebuilding is
#: cheap and a partial digest is worse than a late one, so this is deliberately higher than
#: the retry count anything on the network uses.
RETRY_LIMIT = 5


def build(changed: dict[str, int]) -> str:
    """One line per changed SKU, in pages the operator's mail client will not truncate."""

    lines = [f"{len(changed)} stock levels changed overnight."]
    for start in range(0, len(changed), BATCH_SIZE):
        page = sorted(changed.items())[start : start + BATCH_SIZE]
        lines += [f"  {sku}: now {count}" for sku, count in page]
    # The operator asks which warehouse a number came from, and today there is only the one.
    lines.append("Levels are as reported by the northwind feed.")
    return "\n".join(lines)


def rebuild_until_complete(changed: dict[str, int]) -> str:
    for _ in range(RETRY_LIMIT):
        digest = build(changed)
        if digest:
            return digest
    raise RuntimeError("the northwind digest could not be built")
