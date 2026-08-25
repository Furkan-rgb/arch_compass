"""The published contract this package offers to whoever is integrating with it."""

from typing import Protocol


class SettlementFeed(Protocol):
    """The shape a settlement feed has to have.

    Published in the integration guide, so somebody outside this repository may already be
    writing against it. Whether anybody is, is not written down anywhere here.
    """

    def next_batch(self) -> list[str]: ...

    def acknowledge(self, batch: str) -> None: ...
