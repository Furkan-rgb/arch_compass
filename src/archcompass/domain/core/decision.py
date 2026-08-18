from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from archcompass.domain.core._support import require_text
from archcompass.domain.core.candidate import CandidateId
from archcompass.domain.core.finding import Verdict


class DecisionDisposition(StrEnum):
    ACCEPT = "accept"
    WAIVE = "waive"
    PARK = "park"


@dataclass(frozen=True, slots=True)
class StandingDecision:
    id: str
    branch_id: str
    candidate_id: CandidateId
    disposition: DecisionDisposition
    author: str
    reasoning: str | None
    decided_at: datetime
    review_id: str
    finding_verdict: Verdict
    finding_model_identity: str = ""
    finding_prompt_identity: str = ""
    finding_retrieval_identity: str = ""

    def __post_init__(self) -> None:
        require_text(self.author, "decision author")
        if self.disposition is DecisionDisposition.WAIVE and not (self.reasoning or "").strip():
            raise ValueError("a waiver must include reasoning")
