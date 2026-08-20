"""Task scheduling, written against the boundaries rather than the implementations."""

from __future__ import annotations

from datetime import datetime, timedelta

from ports import (
    Clock,
    IdGenerator,
    NotificationSender,
    TaskFormatter,
    TaskStore,
)


class Scheduler:
    def __init__(
        self,
        clock: Clock,
        store: TaskStore,
        sender: NotificationSender,
        formatter: TaskFormatter,
        identifiers: IdGenerator,
    ) -> None:
        self._clock = clock
        self._store = store
        self._sender = sender
        self._formatter = formatter
        self._identifiers = identifiers

    def schedule(self, name: str, in_days: int) -> str:
        due = self._clock.now(utc=True) + timedelta(days=in_days)
        task_id = self._identifiers.next_id("task-")
        self._store.save(task_id, self._formatter.label(name, due), due)
        return task_id

    def remind(self, address: str) -> int:
        moment: datetime = self._clock.now(utc=True)
        overdue = self._store.due_before(moment)
        for _, label in overdue:
            self._sender.send(address, "Task due", label)
        return len(overdue)
