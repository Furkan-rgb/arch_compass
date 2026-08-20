"""Every boundary this application declares.

Five protocols, each with exactly one implementation today. The detector will report all
five identically, because counting implementations cannot tell them apart. Only the case
can: two of these boundaries are earning their place and three are not.
"""

from __future__ import annotations

from datetime import datetime
from typing import Protocol


class Clock(Protocol):
    """Current time, so scheduling can be tested without waiting."""

    def now(self, utc: bool) -> datetime: ...


class TaskStore(Protocol):
    """Task persistence."""

    def save(self, task_id: str, label: str, due: datetime) -> None: ...

    def due_before(self, moment: datetime) -> list[tuple[str, str]]: ...


class NotificationSender(Protocol):
    """Delivery of a reminder to a person."""

    def send(self, address: str, subject: str, body: str) -> None: ...


class TaskFormatter(Protocol):
    """Rendering of a task into the label shown to a person."""

    def label(self, name: str, due: datetime) -> str: ...


class IdGenerator(Protocol):
    """Identity for a newly created task."""

    def next_id(self, prefix: str) -> str: ...


class ConfigLoader(Protocol):
    """Application settings read from disk."""

    def load(self, path: str) -> dict[str, str]: ...
