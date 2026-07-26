"""Composition root: the only module that names a concrete implementation."""

from __future__ import annotations

from adapters import (
    DefaultTaskFormatter,
    EmailSender,
    SqliteTaskStore,
    SystemClock,
    UuidGenerator,
    YamlConfigLoader,
)
from scheduler import Scheduler


def build(config_path: str) -> Scheduler:
    settings = YamlConfigLoader().load(config_path)
    return Scheduler(
        clock=SystemClock(),
        store=SqliteTaskStore(settings["database"]),
        sender=EmailSender(settings["smtp_host"], int(settings["smtp_port"])),
        formatter=DefaultTaskFormatter(),
        identifiers=UuidGenerator(),
    )


def main() -> None:
    scheduler = build("settings.yaml")
    scheduler.schedule("Renew the domain", in_days=30)
    scheduler.remind("owner@example.com")
