"""The reasoning boundary: the two stages a review needs a model for."""

from __future__ import annotations

from enum import StrEnum
from typing import Protocol

from archcompass.domain.atlas import FindingCandidate
from archcompass.domain.case import ArchitectureCase
from archcompass.domain.policy import PolicyDocument
from archcompass.domain.review import BoundaryReview, CandidateVerdict
from archcompass.domain.review_conversation import ReviewAnswer, ReviewMessage


class ReasoningTask(StrEnum):
    """Every reasoning stage that carries its own versioned prompt contract.

    Stage names were previously repeated as bare strings in the prompt registry, the
    workflow call sites, and the conversation service, so a typo surfaced only as a
    runtime KeyError. Naming them once makes the set checkable.
    """

    JUDGE_FINDING_CANDIDATE = "judge_finding_candidate"
    ANSWER_REVIEW_QUESTION = "answer_review_question"


class FocusedReasoningProvider(Protocol):
    """Judgement and answering, plus the identities a review records for both.

    One protocol rather than two: the identity half was split out for a consultation-era
    caller that no longer exists, leaving an abstraction with a single extender and no
    separate consumer — the shape this advisor exists to report.
    """

    @property
    def model_identity(self) -> str: ...

    def prompt_identity(self, task: ReasoningTask) -> str: ...

    def judge_finding_candidate(
        self,
        case: ArchitectureCase,
        candidate: FindingCandidate,
        policies: list[PolicyDocument],
    ) -> CandidateVerdict:
        """Decide whether one detected pattern matters in this case.

        The policies are presented in the order given and the response binds to them by
        position, so the list must not be reordered between the call and the result.
        """
        ...

    def answer_review_question(
        self,
        review: BoundaryReview,
        history: list[ReviewMessage],
        question: str,
    ) -> ReviewAnswer:
        """Answer one question about a review the model is shown in full.

        The reply marks supporting boundaries by position in `review.report.reviewed`, so
        the order must not change between the call and the result.
        """
        ...
