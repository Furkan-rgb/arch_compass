"""The payment boundary: what the shop needs from any card processor."""

from abc import ABC, abstractmethod


class PaymentGateway(ABC):
    """Charge and refund cards on behalf of the shop."""

    @abstractmethod
    def charge(self, order_id: str, amount_cents: int) -> str:
        """Charge the order's card and return the processor's charge id."""

    @abstractmethod
    def refund(self, charge_id: str, amount_cents: int) -> None:
        """Refund part or all of a prior charge."""
