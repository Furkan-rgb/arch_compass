"""Transactional email delivery through AcmeHub's messaging endpoint."""

import json

from acme_shop.notifications.settings import RETRY_LIMIT
from acme_shop.shared import acme_client


def send_receipt(order_id: str, address: str) -> bytes:
    """Send an order receipt through AcmeHub messaging."""
    body = json.dumps({"order": order_id, "to": address}).encode()
    return acme_client.post("/messaging/email", body, retries=RETRY_LIMIT)
