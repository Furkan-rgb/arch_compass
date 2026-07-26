"""The one implementation of each boundary.

None of these classes inherit from the protocols they satisfy. Conformance is structural,
which is ordinary Python and is what the analyzer has to resolve to see the relationship
at all.
"""

from __future__ import annotations

import sqlite3
import uuid
from datetime import UTC, datetime
from email.message import EmailMessage
from smtplib import SMTP


class SystemClock:
    """Wall-clock time from the operating system."""

    def now(self, utc: bool) -> datetime:
        return datetime.now(UTC) if utc else datetime.now()


class SqliteTaskStore:
    """Tasks in a local SQLite file."""

    def __init__(self, database_path: str) -> None:
        self._connection = sqlite3.connect(database_path)
        self._connection.execute(
            "CREATE TABLE IF NOT EXISTS tasks (task_id TEXT PRIMARY KEY, label TEXT, due TEXT)"
        )

    def save(self, task_id: str, label: str, due: datetime) -> None:
        self._connection.execute(
            "INSERT OR REPLACE INTO tasks VALUES (?, ?, ?)",
            (task_id, label, due.isoformat()),
        )
        self._connection.commit()

    def due_before(self, moment: datetime) -> list[tuple[str, str]]:
        rows = self._connection.execute(
            "SELECT task_id, label FROM tasks WHERE due < ?",
            (moment.isoformat(),),
        )
        return [(str(row[0]), str(row[1])) for row in rows]


class EmailSender:
    """Reminders over SMTP."""

    def __init__(self, host: str, port: int) -> None:
        self._host = host
        self._port = port

    def send(self, address: str, subject: str, body: str) -> None:
        message = EmailMessage()
        message["To"] = address
        message["Subject"] = subject
        message.set_content(body)
        with SMTP(self._host, self._port) as smtp:
            smtp.send_message(message)


class DefaultTaskFormatter:
    """The label format the downstream reporting system parses."""

    def label(self, name: str, due: datetime) -> str:
        return f"{name.strip()} [{due:%Y-%m-%d}]"


class UuidGenerator:
    """Task identity as a UUID4 string."""

    def next_id(self, prefix: str) -> str:
        return f"{prefix}{uuid.uuid4()}"


class YamlConfigLoader:
    """Settings from a flat YAML file of string keys and values."""

    def load(self, path: str) -> dict[str, str]:
        settings: dict[str, str] = {}
        with open(path, encoding="utf-8") as handle:
            for line in handle:
                if ":" not in line or line.lstrip().startswith("#"):
                    continue
                key, _, value = line.partition(":")
                settings[key.strip()] = value.strip()
        return settings
