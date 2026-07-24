from domain import CompletedRun, ReportAnswer


class OllamaReasoner:
    def answer_report_question(
        self,
        run: CompletedRun,
        question: str,
    ) -> ReportAnswer:
        claims = [*run.report.findings, *run.report.policies]
        request_context = {
            "question": question,
            "decision": run.report.summary,
            "claims": claims,
        }
        return self._request(request_context)

    def _request(self, context: dict[str, object]) -> ReportAnswer:
        return ReportAnswer(text=str(context))
