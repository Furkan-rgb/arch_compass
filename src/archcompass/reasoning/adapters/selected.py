"""Lazy LangChain models selected at the application boundary."""

from __future__ import annotations

import logging
from collections.abc import Generator
from contextlib import contextmanager
from threading import BoundedSemaphore, Lock

from langchain_core.language_models import BaseChatModel

from archcompass.configuration import ReasoningModelConfig
from archcompass.domain import (
    ArchitectureCase,
    Candidate,
    Finding,
    Question,
    RecordedInvestigation,
    Review,
    ReviewDelta,
)
from archcompass.domain.errors import NoReasoningModelSelectedError
from archcompass.ports.capabilities import (
    ReviewedSubject,
    ReviewSynopsis,
)
from archcompass.ports.policy_retrieval import RetrievedPolicySet
from archcompass.reasoning.adapters.deep_judge import DeepArchitectureJudge
from archcompass.reasoning.adapters.deterministic import (
    DeterministicAnswerer,
    DeterministicJudge,
    DeterministicQuestionGenerator,
    DeterministicSynopsist,
)
from archcompass.reasoning.adapters.factory import build_chat_model
from archcompass.reasoning.adapters.judge_tools import JudgeToolbox
from archcompass.reasoning.adapters.langchain import (
    LangChainArchitectureJudge,
    LangChainQuestionGenerator,
    LangChainReviewAnswerer,
    LangChainReviewSynopsist,
)
from archcompass.reasoning.ports import (
    ConversationAnswer,
    ConversationMessage,
    InvestigatorSource,
    SelectedReasoningModel,
)
from archcompass.reasoning.records import (
    model_identity,
)


class SelectedLangChainChatModel:
    """The transport for the model in force, and one of its slots while a caller uses it.

    Two things rather than one because a review asks for judgements faster than any provider
    answers them. Every selected candidate is dispatched at once — the graph fans out one
    branch per candidate and forty-six of them is an ordinary number for a real repository —
    so without a bound here the fan-out is the request count, and the provider is handed the
    whole review in one breath.

    What that costs depends on who is listening. A hosted API answers in parallel and the
    only risk is a rate limit. A local runner has one slot: it answers the first request and
    queues the other forty-five, each of them spending the deadline it was given while it
    waits its turn. Past a queue of about ten the tail cannot be reached in time, and the
    review stops with nine judgements, thirty-six pending timeouts, and a progress line that
    has not moved in five minutes. `ProviderDefaults.max_parallel_requests` is the number
    that ends that, and this is where it is spent.

    The gate is held for a whole conversation, not for one request: a hinge investigation is
    a tool loop of a dozen calls and it holds one slot from its first to its last, because
    what it is doing is using the model, and something else using it at the same time is the
    thing being bounded.
    """

    def __init__(self, selections: SelectedReasoningModel) -> None:
        self._selections = selections
        self._cached: tuple[str, BaseChatModel, BoundedSemaphore] | None = None
        self._lock = Lock()

    def configuration(self) -> ReasoningModelConfig | None:
        return self._selections.current()

    @contextmanager
    def in_use(self) -> Generator[tuple[BaseChatModel, str]]:
        """The transport, held for as long as the caller is talking to it.

        A context manager rather than a getter so that holding a slot and using the model
        cannot come apart: there is no way to obtain the one without the other, which is
        what a `current()` beside a separate `gate()` would have allowed on the call that
        forgot.
        """

        model, identity, gate = self._resolve()
        with gate:
            yield model, identity

    def _resolve(self) -> tuple[BaseChatModel, str, BoundedSemaphore]:
        config = self._selections.current()
        if config is None:
            raise NoReasoningModelSelectedError(
                "This workspace has not selected a reasoning model."
            )
        identity = model_identity(config)
        if config.provider == "fake":
            # Unreachable through the composition root, which selects the deterministic
            # chain rather than building a transport for it. Kept because the workspace's
            # model selection is a stored string and a stale one naming `fake` would
            # otherwise reach `build_chat_model`, which has no branch for it.
            raise ValueError(
                "the deterministic provider has no LangChain chat transport"
            )
        with self._lock:
            if self._cached is None or self._cached[0] != identity:
                # The gate is rebuilt with the transport and for the same reason it is
                # cached with it: how many requests may be in flight is a property of the
                # provider being talked to, so a workspace that switches from Ollama to a
                # hosted model mid-process must not keep the local model's single slot.
                #
                # Callers already inside the old gate are unaffected — they hold that
                # object, and it goes away when the last of them lets go of it.
                self._cached = (
                    identity,
                    build_chat_model(config),
                    BoundedSemaphore(config.max_parallel_requests),
                )
            return self._cached[1], identity, self._cached[2]


_log = logging.getLogger("archcompass.reasoning")


def _is_deterministic(selected: SelectedLangChainChatModel) -> bool:
    """Whether the model chosen *right now* is the stand-in rather than a real one.

    Asked per call, not once at build, for the same reason `supports_tools` is: a workspace
    changes its model through `PUT /api/models/selection` while the process runs, and a
    chain chosen when the graph was built would keep answering deterministically for a
    reviewer who had just picked Gemini.

    This is the whole of the dispatch. What each capability then does lives in
    `deterministic.py`; here it is one line, so that the module about which model is
    selected is not also the module about what to do when none is.
    """

    config = selected.configuration()
    return config is not None and config.provider == "fake"


class SelectedLangChainJudge:
    """The judge in force, and whether it is one that can read the repository.

    `toolbox` is what decides. With one, and with a subject to read, the judgement is a
    bounded conversation that may look things up; without either it is the single structured
    call it has always been. Both reach the same `FindingOutput`.

    The model is resolved through `in_use` and held for the whole judgement rather than for
    each request inside it. That matters more here than it did: a judgement that looks things
    up is a dozen requests, and a local runner with one slot would otherwise interleave them
    with another candidate's.
    """

    def __init__(
        self,
        selected: SelectedLangChainChatModel,
        toolbox: JudgeToolbox | None = None,
    ) -> None:
        self._selected = selected
        self._toolbox = toolbox

    def judge(
        self,
        candidate: Candidate,
        case: ArchitectureCase,
        policies: RetrievedPolicySet,
        investigation: RecordedInvestigation | None = None,
        *,
        subject: ReviewedSubject | None = None,
    ) -> Finding:
        if _is_deterministic(self._selected):
            return DeterministicJudge().judge(
                candidate, case, policies, investigation, subject=subject
            )
        with self._selected.in_use() as (model, identity):
            if self._toolbox is None or subject is None:
                return LangChainArchitectureJudge(model, model_identity=identity).judge(
                    candidate, case, policies, investigation
                )
            return DeepArchitectureJudge(
                model, self._toolbox, model_identity=identity
            ).judge(candidate, case, policies, subject=subject)


class SelectedLangChainQuestionGenerator:
    def __init__(self, selected: SelectedLangChainChatModel) -> None:
        self._selected = selected

    def generate(
        self,
        case: ArchitectureCase,
        findings: tuple[Finding, ...],
        *,
        round: int,
        excluded_equivalence_keys: frozenset[str],
    ) -> tuple[Question, ...]:
        if _is_deterministic(self._selected):
            return DeterministicQuestionGenerator().generate(
                case,
                findings,
                round=round,
                excluded_equivalence_keys=excluded_equivalence_keys,
            )
        with self._selected.in_use() as (model, _):
            return LangChainQuestionGenerator(model).generate(
                case,
                findings,
                round=round,
                excluded_equivalence_keys=excluded_equivalence_keys,
            )


class SelectedLangChainReviewSynopsist:
    """The summary, written by whichever model is selected when the review is composed.

    The deterministic provider gets a deterministic paragraph rather than none. A stand-in
    that says what it is keeps the shape of the document the same in the mode the browser
    suite runs in — a report whose opening paragraph exists only against a hosted model is a
    paragraph nothing checks.
    """

    def __init__(self, selected: SelectedLangChainChatModel) -> None:
        self._selected = selected

    def write(
        self,
        case: ArchitectureCase,
        findings: tuple[Finding, ...],
        *,
        questions: tuple[Question, ...],
        delta: ReviewDelta,
        previous: Review | None,
        waiting: bool,
    ) -> ReviewSynopsis | None:
        if not findings:
            return None
        if _is_deterministic(self._selected):
            return DeterministicSynopsist().write(
                case,
                findings,
                questions=questions,
                delta=delta,
                previous=previous,
                waiting=waiting,
            )
        with self._selected.in_use() as (model, identity):
            return LangChainReviewSynopsist(model, model_identity=identity).write(
                case,
                findings,
                questions=questions,
                delta=delta,
                previous=previous,
                waiting=waiting,
            )


class SelectedLangChainReviewAnswerer:
    def __init__(
        self,
        selected: SelectedLangChainChatModel,
        investigators: InvestigatorSource | None = None,
    ) -> None:
        self._selected = selected
        self._investigators = investigators

    def answer(
        self,
        review: Review,
        history: tuple[ConversationMessage, ...],
        question: str,
    ) -> ConversationAnswer:
        if _is_deterministic(self._selected):
            return DeterministicAnswerer(self._investigators).answer(
                review, history, question
            )
        with self._selected.in_use() as (model, _):
            return LangChainReviewAnswerer(model, self._investigators).answer(
                review, history, question
            )
