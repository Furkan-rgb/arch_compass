from domain import CompletedRun, ReportAnswer
from ports import ReportQuestionReasoner


class ReportQuestionService:
    def __init__(self, reasoner: ReportQuestionReasoner) -> None:
        self._reasoner = reasoner

    def ask(self, run: CompletedRun, question: str) -> ReportAnswer:
        return self._reasoner.answer_report_question(run, question)
