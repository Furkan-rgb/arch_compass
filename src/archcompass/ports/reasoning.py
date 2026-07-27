"""The reasoning boundary: the two stages a review needs a model for."""

from __future__ import annotations

from collections.abc import Callable
from enum import StrEnum
from typing import Protocol, runtime_checkable

from archcompass.domain.atlas import FindingCandidate
from archcompass.domain.case import ArchitectureCase
from archcompass.domain.knowledge import MethodKnowledge
from archcompass.domain.policy import PolicyDocument
from archcompass.domain.review import (
    BoundaryReview,
    CandidateVerdict,
    ReviewedBoundary,
    ReviewOverview,
)
from archcompass.domain.review_conversation import ReviewAnswer, ReviewMessage


class ReasoningTask(StrEnum):
    """Every reasoning stage that carries its own versioned prompt contract.

    Stage names were previously repeated as bare strings in the prompt registry, the
    workflow call sites, and the conversation service, so a typo surfaced only as a
    runtime KeyError. Naming them once makes the set checkable.
    """

    JUDGE_FINDING_CANDIDATE = "judge_finding_candidate"
    SUMMARISE_REVIEW = "summarise_review"
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

    def summarise_review(
        self,
        case: ArchitectureCase,
        boundaries: list[ReviewedBoundary],
    ) -> ReviewOverview:
        """Say what the verdicts amount to, once, across all of them.

        The boundaries arrive already composed and numbered, and are presented by position:
        the reply marks which of them each statement rests on, and their references are
        attached from those positions. The order must not change between the call and the
        result. Nothing here may revise a verdict — the shape returned has no field for one.
        """
        ...

    def answer_review_question(
        self,
        review: BoundaryReview,
        history: list[ReviewMessage],
        question: str,
        knowledge: MethodKnowledge,
    ) -> ReviewAnswer:
        """Answer one question about a review the model is shown in full.

        The reply marks supporting boundaries by position in `review.report.reviewed`, so
        the order must not change between the call and the result.

        `knowledge` is background about the method — the primer and the whole policy corpus,
        presented entire rather than ranked. It explains the review's vocabulary; it is
        never evidence about the repository, and an answer never cites it as grounding. Only
        boundaries ground an answer, so nothing here binds by position and nothing here is
        read back.
        """
        ...


@runtime_checkable
class StreamingAnswerReasoner(Protocol):
    """A reasoner that can also report an answer's prose while it is being written.

    Its own protocol, tested with `isinstance`, because whether a reply can be streamed is a
    property of the vendor behind the reasoner rather than of the stage. A reasoner that
    cannot omits the method; the application asks, and answers the question without a preview
    when the answer is no. Folding this into `FocusedReasoningProvider` would instead make
    every reasoner declare a capability it might not have.

    That check is by name only. `runtime_checkable` compares which methods exist and nothing
    about their signatures, so a `stream_review_answer` taking different arguments passes
    `isinstance` and then fails on the call — and no type checker sees it either, because a
    reasoner is built and passed around as `FocusedReasoningProvider`, which says nothing
    about streaming. Every implementation therefore states its conformance to this protocol
    where it is defined, so the signature is checked at the one place that knows it.

    What is streamed is a preview and nothing more. `stream_review_answer` returns the same
    validated `ReviewAnswer` the non-streaming call returns, from the same validation, and
    the answer that gets stored is that one — never the accumulated fragments. Grounding is
    still derived from positional flags that only exist once the whole reply has arrived, so
    a preview can never carry a citation.
    """

    def stream_review_answer(
        self,
        review: BoundaryReview,
        history: list[ReviewMessage],
        question: str,
        knowledge: MethodKnowledge,
        on_prose: Callable[[str], None],
    ) -> ReviewAnswer:
        """Answer as `answer_review_question` does, calling `on_prose` with each fragment.

        Each call receives only text not yet passed, in order, so a caller may append.
        Fragments may stop arriving before the answer does — a reply needing the one
        sanctioned repair round is rewritten unstreamed — so a caller must treat the returned
        answer as the text, and whatever it showed meanwhile as provisional.
        """
        ...
