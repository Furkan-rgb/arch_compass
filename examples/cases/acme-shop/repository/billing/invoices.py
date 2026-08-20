"""Invoice synchronisation against AcmeHub."""

import json

from acme_shop.billing.settings import PAGE_SIZE, RETRY_LIMIT
from acme_shop.shared import acme_client


def sync_invoice(invoice: dict) -> bytes:
    """Push one invoice to AcmeHub's billing endpoint."""
    body = json.dumps(invoice).encode()
    return acme_client.post("/billing/invoices", body, retries=RETRY_LIMIT)


def paginate(invoices: list[dict]) -> list[list[dict]]:
    """Slice the back-office invoice listing into pages."""
    return [invoices[i : i + PAGE_SIZE] for i in range(0, len(invoices), PAGE_SIZE)]
