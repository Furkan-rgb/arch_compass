from typing import Protocol

from domain import CompletedRun, ReportAnswer


class ReportQuestionReasoner(Protocol):
    def answer_report_question(
        self,
        run: CompletedRun,
        question: str,
    ) -> ReportAnswer: ...
