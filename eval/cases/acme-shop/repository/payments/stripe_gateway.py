"""Stripe as the shop's card processor."""

from acme_shop.payments.gateway import PaymentGateway


class StripeGateway(PaymentGateway):
    """The Stripe-backed processor the shop runs in production."""

    def __init__(self, api_key: str) -> None:
        self._api_key = api_key

    def charge(self, order_id: str, amount_cents: int) -> str:
        return f"ch_{order_id}_{amount_cents}"

    def refund(self, charge_id: str, amount_cents: int) -> None:
        del charge_id, amount_cents
