"""Scheduling tests.

`FixedClock` is a second implementation of `Clock`, so the detector should not report
`Clock` as an abstraction with one implementation. That is deliberate: the fixture proves
the detector can already tell a boundary with real variation from one without, before any
model is asked anything.
"""

from __future__ import annotations

from datetime import datetime

from scheduler import Scheduler


class FixedClock:
    """A clock that does not move, so a due date is exact in a test."""

    def __init__(self, moment: datetime) -> None:
        self._moment = moment

    def now(self, utc: bool) -> datetime:
        return self._moment


class RecordingStore:
    def __init__(self) -> None:
        self.saved: list[tuple[str, str, datetime]] = []

    def save(self, task_id: str, label: str, due: datetime) -> None:
        self.saved.append((task_id, label, due))

    def due_before(self, moment: datetime) -> list[tuple[str, str]]:
        return [(item[0], item[1]) for item in self.saved if item[2] < moment]


class RecordingSender:
    def __init__(self) -> None:
        self.sent: list[str] = []

    def send(self, address: str, subject: str, body: str) -> None:
        self.sent.append(body)


def _scheduler(clock: FixedClock) -> tuple[Scheduler, RecordingStore, RecordingSender]:
    from adapters import DefaultTaskFormatter, UuidGenerator

    store = RecordingStore()
    sender = RecordingSender()
    scheduler = Scheduler(
        clock=clock,
        store=store,
        sender=sender,
        formatter=DefaultTaskFormatter(),
        identifiers=UuidGenerator(),
    )
    return scheduler, store, sender


def test_a_scheduled_task_is_due_the_requested_number_of_days_later() -> None:
    scheduler, store, _ = _scheduler(FixedClock(datetime(2026, 1, 1)))

    scheduler.schedule("Renew the domain", in_days=30)

    assert store.saved[0][2] == datetime(2026, 1, 31)


def test_only_overdue_tasks_produce_a_reminder() -> None:
    scheduler, _, sender = _scheduler(FixedClock(datetime(2026, 1, 1)))
    scheduler.schedule("Already late", in_days=-1)
    scheduler.schedule("Not yet", in_days=10)

    assert scheduler.remind("owner@example.com") == 1
    assert "Already late" in sender.sent[0]
