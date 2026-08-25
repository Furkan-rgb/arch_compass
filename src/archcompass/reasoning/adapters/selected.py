"""Lazy LangChain models selected at the application boundary."""

from __future__ import annotations

import logging
import os
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
    RepositoryAtlas,
    RepositoryRef,
    Review,
    ReviewDelta,
)
from archcompass.domain.errors import NoReasoningModelSelectedError, ProviderError
from archcompass.ports.capabilities import (
    ReviewSynopsis,
)
from archcompass.ports.policy_retrieval import RetrievedPolicySet
from archcompass.reasoning.adapters.deterministic import (
    DeterministicAnswerer,
    DeterministicHingeInvestigator,
    DeterministicJudge,
    DeterministicQuestionGenerator,
    DeterministicSynopsist,
)
from archcompass.reasoning.adapters.factory import build_chat_model
from archcompass.reasoning.adapters.investigation import (
    LangChainHingeInvestigator,
)
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


def _investigation_enabled() -> bool:
    """Hinge investigation is on by default and can be turned off without changing the model.

    The graph already treats it as optional — `ReviewWorkflowCapabilities.investigator`
    defaults to `NoHingeInvestigation`, and a workspace on a model that cannot call tools
    asks its questions the way it always asked them — so this switch selects between two
    configurations the product already supports rather than introducing a third.

    It exists because the pass is not free and its value is not uniform. Up to eight held
    findings, up to twelve lookups over twelve model calls each, and one further judgement
    per finding that found something: on a hosted tier that is a rounding error, and on one
    local GPU it is minutes added to a review before anybody is asked anything. An operator
    who would rather be asked the question than have it checked first can say so without
    moving off their model.
    """

    return os.environ.get("ARCHCOMPASS_HINGE_INVESTIGATION", "1").strip().lower() not in {
        "0",
        "false",
        "no",
        "off",
    }


class SelectedLangChainJudge:
    def __init__(self, selected: SelectedLangChainChatModel) -> None:
        self._selected = selected

    def judge(
        self,
        candidate: Candidate,
        case: ArchitectureCase,
        policies: RetrievedPolicySet,
        investigation: RecordedInvestigation | None = None,
    ) -> Finding:
        if _is_deterministic(self._selected):
            return DeterministicJudge().judge(candidate, case, policies, investigation)
        with self._selected.in_use() as (model, identity):
            return LangChainArchitectureJudge(model, model_identity=identity).judge(
                candidate, case, policies, investigation
            )


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


class SelectedLangChainHingeInvestigator:
    """The hinge pass, against whichever model is selected right now.

    Follows the judge: the deterministic provider is answered first and never reaches a
    transport, a provider that turns out not to offer tools is not asked again for the life
    of the process, and a failure degrades to the finding unchanged. Losing an investigation
    must never cost the review the hinge belongs to.
    """

    def __init__(
        self, selected: SelectedLangChainChatModel, investigators: InvestigatorSource
    ) -> None:
        self._selected = selected
        self._investigators = investigators
        self._tools_refused = False

    def supports_tools(self) -> bool:
        """Whether anything could look, asked per dispatch.

        The deterministic provider can: it has a real toolbox over a real atlas, and it is
        the only configuration `make check` ever runs. What it has no use for is a
        transport.
        """

        if not _investigation_enabled():
            return False
        config = self._selected.configuration()
        if config is None:
            return False
        if _is_deterministic(self._selected):
            # It has a real toolbox over a real atlas. What it has no use for is a transport.
            return True
        return not self._tools_refused

    def investigate(
        self,
        finding: Finding,
        case: ArchitectureCase,
        *,
        repository: RepositoryRef,
        atlas: RepositoryAtlas,
    ) -> RecordedInvestigation | None:
        if _is_deterministic(self._selected):
            return DeterministicHingeInvestigator(self._investigators).investigate(
                finding, case, repository=repository, atlas=atlas
            )
        try:
            with self._selected.in_use() as (model, identity):
                return LangChainHingeInvestigator(
                    model, self._investigators, model_identity=identity
                ).investigate(finding, case, repository=repository, atlas=atlas)
        except (NotImplementedError, ProviderError) as error:
            # A hinge that could not be checked is the hinge this product produced
            # yesterday. It goes to a person, and the record says why nothing settled it.
            _log.warning(
                "The hinge on %s was not investigated: %s", finding.candidate.id, error
            )
                # `or`, not `=`. Assigning cleared the latch the moment a *different* failure
            # followed a refusal — a provider that had already said it cannot bind tools was
            # asked again for the rest of the process, which is the opposite of what the
            # class docstring promises.
            self._tools_refused = self._tools_refused or isinstance(
                error, NotImplementedError
            )
            # No record: nothing was looked up and nothing could be. The hinge stands, and
            # the judge is not called again for a candidate whose facts have not moved.
            return None

