from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from archcompass.domain._support import freeze_sequences, require_text
from archcompass.domain.candidate import Candidate
from archcompass.domain.policy import Policy
from archcompass.domain.values import Evidence


class Verdict(StrEnum):
    MATERIAL = "material"
    CLEARED = "cleared"
    HELD = "held"


@dataclass(frozen=True, slots=True)
class PolicyBearing:
    policy: Policy
    reasoning: str


@dataclass(frozen=True, slots=True)
class Finding:
    candidate: Candidate
    verdict: Verdict
    reasoning: str
    policies: tuple[PolicyBearing, ...]
    #: The candidate's evidence carried onto the finding, so a finding read on its own is
    #: still answerable. It is not a judged selection — no producer narrows it, and nothing
    #: records which excerpt a verdict rested on. Anything presenting it as the judgement's
    #: own pick is presenting the same list twice.
    evidence: tuple[Evidence, ...]
    hinge: str | None = None
    recommended_response: str | None = None
    reused_from_review_id: str | None = None
    model_identity: str = ""
    prompt_identity: str = ""
    retrieval_identity: str = ""
    #: The `RecordedInvestigation` on the review that checked this finding's hinge,
    #: named by its own content hash. "" where nothing looked, which is every finding
    #: that never had a hinge to check. The transcript itself is on the review: this
    #: record is cached, carried forward and compared, and it stays small enough to be.
    investigation_identity: str = ""

    def __post_init__(self) -> None:
        freeze_sequences(self, "policies", "evidence")
        require_text(self.reasoning, "finding reasoning")
        if self.hinge and self.recommended_response:
            raise ValueError("a finding with an uncertainty hinge cannot recommend a response")
        if self.verdict is not Verdict.MATERIAL and self.recommended_response:
            raise ValueError("only a material finding may recommend a response")
