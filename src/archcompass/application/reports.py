"""Application service for writing completed recommendation reports."""

from __future__ import annotations

from archcompass.domain.consultation import ConsultationRun, ConsultationStatus
from archcompass.domain.errors import PersistenceError
from archcompass.ports.reporting import ReportWriter


class ReportService:
    def __init__(self, writer: ReportWriter) -> None:
        self._writer = writer

    def write(self, run: ConsultationRun) -> None:
        if (
            run.status != ConsultationStatus.SUCCEEDED
            or run.report is None
            or run.markdown_report is None
        ):
            raise PersistenceError("Only a completed successful run can be written as a report")
        self._writer.write(
            report_id=run.run_id,
            structured_json=run.report.model_dump_json(indent=2),
            markdown=run.markdown_report,
        )
