"""The reasoner that resolves which model it is on every call.

A provider built once at startup answers with whatever was configured when the process
began, for as long as the process lives. That is the right shape for a command that runs
once and exits, and the wrong one for a workspace someone is sitting in front of: the
choice can change while it is running, and the point of letting it change is that the next
review honours it.

It is also what lets a workspace start with nothing chosen. Constructing a Google transport
resolves its API key and raises when there is none, so an eagerly built reasoner turns "no
model is configured yet" into a process that will not boot — and the interface that would
have let someone fix it never loads.
"""

from __future__ import annotations

from collections.abc import Callable

from archcompass.domain.atlas import FindingCandidate
from archcompass.domain.case import ArchitectureCase
from archcompass.domain.errors import NoReasoningModelSelectedError, ProviderError
from archcompass.domain.knowledge import MethodKnowledge
from archcompass.domain.policy import PolicyDocument
from archcompass.domain.review import (
    BoundaryReview,
    CandidateVerdict,
    OpenQuestion,
    ReviewedBoundary,
    ReviewEvidence,
    ReviewOverview,
)
from archcompass.domain.review_conversation import ReviewAnswer, ReviewMessage
from archcompass.ports.model_catalog import (
    ReasoningProviderFactory,
    SelectedReasoningModel,
)
from archcompass.ports.reasoning import (
    FocusedReasoningProvider,
    ReasoningTask,
    StreamingAnswerReasoner,
)

_NOTHING_SELECTED = (
    "This workspace has not chosen a reasoning model. Pick one from the model chip in the "
    "top bar — it offers only models a reachable provider actually has."
)


class SelectedModelReasoner:
    """Whichever model this workspace currently reasons with.

    Rebuilt only when the choice changes, so a review's forty judgements share one provider
    and one connection pool while a selection made between two reviews takes effect on the
    second.

    Every `ProviderError` is recorded against the selection on the way past and re-raised
    untouched. That is the half of a model's health a probe cannot see: listing a model
    proves it exists, not that a quota remains or that a key still carries it, and the only
    place that truth appears is in a call that just failed.
    """

    def __init__(
        self,
        selection: SelectedReasoningModel,
        build: ReasoningProviderFactory,
    ) -> None:
        self._selection = selection
        self._build = build
        self._cached: tuple[str, FocusedReasoningProvider] | None = None

    def _delegate(self) -> FocusedReasoningProvider:
        config = self._selection.current()
        if config is None:
            raise NoReasoningModelSelectedError(_NOTHING_SELECTED)
        identity = f"{config.provider}:{config.model}"
        if self._cached is None or self._cached[0] != identity:
            self._cached = (identity, self._build(config))
        return self._cached[1]

    def _run[Result](self, call: Callable[[FocusedReasoningProvider], Result]) -> Result:
        delegate = self._delegate()
        try:
            return call(delegate)
        except ProviderError as error:
            self._selection.record_failure(str(error))
            raise

    @property
    def model_identity(self) -> str:
        return self._delegate().model_identity

    def prompt_identity(self, task: ReasoningTask) -> str:
        return self._delegate().prompt_identity(task)

    def judge_finding_candidate(
        self,
        case: ArchitectureCase,
        candidate: FindingCandidate,
        policies: list[PolicyDocument],
    ) -> CandidateVerdict:
        return self._run(
            lambda reasoner: reasoner.judge_finding_candidate(case, candidate, policies)
        )

    def elicit_questions(
        self,
        case: ArchitectureCase,
        boundaries: list[ReviewedBoundary],
    ) -> list[OpenQuestion]:
        return self._run(lambda reasoner: reasoner.elicit_questions(case, boundaries))

    def summarise_review(
        self,
        case: ArchitectureCase,
        boundaries: list[ReviewedBoundary],
    ) -> ReviewOverview:
        return self._run(lambda reasoner: reasoner.summarise_review(case, boundaries))

    def answer_review_question(
        self,
        review: BoundaryReview,
        evidence: ReviewEvidence,
        history: list[ReviewMessage],
        question: str,
        knowledge: MethodKnowledge,
    ) -> ReviewAnswer:
        return self._run(
            lambda reasoner: reasoner.answer_review_question(
                review, evidence, history, question, knowledge
            )
        )

    def discuss_open_question(
        self,
        review: BoundaryReview,
        evidence: ReviewEvidence,
        question: OpenQuestion,
        history: list[ReviewMessage],
        asked: str,
        knowledge: MethodKnowledge,
    ) -> ReviewAnswer:
        return self._run(
            lambda reasoner: reasoner.discuss_open_question(
                review, evidence, question, history, asked, knowledge
            )
        )

    def stream_review_answer(
        self,
        review: BoundaryReview,
        evidence: ReviewEvidence,
        history: list[ReviewMessage],
        question: str,
        knowledge: MethodKnowledge,
        on_prose: Callable[[str], None],
    ) -> ReviewAnswer:
        return self._run(
            lambda reasoner: _streaming(reasoner).stream_review_answer(
                review, evidence, history, question, knowledge, on_prose
            )
        )

    def stream_open_question_discussion(
        self,
        review: BoundaryReview,
        evidence: ReviewEvidence,
        question: OpenQuestion,
        history: list[ReviewMessage],
        asked: str,
        knowledge: MethodKnowledge,
        on_prose: Callable[[str], None],
    ) -> ReviewAnswer:
        return self._run(
            lambda reasoner: _streaming(reasoner).stream_open_question_discussion(
                review, evidence, question, history, asked, knowledge, on_prose
            )
        )


def _streaming(reasoner: FocusedReasoningProvider) -> StreamingAnswerReasoner:
    """The delegate as a streaming reasoner, refusing rather than guessing if it is not one.

    Both streaming methods are declared unconditionally above, and they have to be: the
    application decides whether a reply can be previewed with `isinstance`, which compares
    method names alone, so a delegate that declared them only sometimes would silently turn
    previews off for every provider. Whether fragments actually arrive is decided later, by
    the transport check inside the underlying provider.

    This narrowing exists for the case that covers neither: a reasoner that is not
    streaming-shaped at all, which is a programming error and says so here rather than as an
    `AttributeError` from inside a lambda.
    """

    if not isinstance(reasoner, StreamingAnswerReasoner):
        raise ProviderError(
            f"The selected reasoner ({reasoner.model_identity}) cannot stream an answer"
        )
    return reasoner


#: Reached by `isinstance` in the conversation service, which compares method names and not
#: signatures. This states the shape so a drifted forwarding method is a type error here
#: rather than a silent loss of every answer preview.
_conforms: type[StreamingAnswerReasoner] = SelectedModelReasoner
