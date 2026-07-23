"""Ports for durable report output."""

from __future__ import annotations

from typing import Protocol


class ReportWriter(Protocol):
    def write(
        self,
        *,
        report_id: str,
        structured_json: str,
        markdown: str,
    ) -> None: ...
