"""Lazy LangChain models selected at the application boundary."""

from __future__ import annotations

import logging
import os
from collections.abc import Callable, Sequence
from concurrent.futures import ThreadPoolExecutor
from threading import Lock

from langchain_core.language_models import BaseChatModel

from archcompass.configuration import ReasoningModelConfig, resolve_api_key
from archcompass.domain import (
    ArchitectureCase,
    Candidate,
    Finding,
    Question,
    RepositoryAtlas,
    RepositoryRef,
    Review,
    ReviewDelta,
)
from archcompass.domain.errors import NoReasoningModelSelectedError, ProviderError
from archcompass.ports.capabilities import (
    BatchOutcome,
    InvestigatedFinding,
    JudgementRequest,
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
from archcompass.reasoning.adapters.google_batch import (
    BatchUnavailableError,
    GoogleBatchJudge,
)
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
from archcompass.reasoning.refusals import (
    BatchRefusalStore,
    InMemoryBatchRefusals,
)


class SelectedLangChainChatModel:
    def __init__(self, selections: SelectedReasoningModel) -> None:
        self._selections = selections
        self._cached: tuple[str, BaseChatModel] | None = None
        self._lock = Lock()

    def configuration(self) -> ReasoningModelConfig | None:
        return self._selections.current()

    def current(self) -> tuple[BaseChatModel, str]:
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
                self._cached = (identity, build_chat_model(config))
            return self._cached[1], identity


_log = logging.getLogger("archcompass.batch")


def _is_deterministic(selected: SelectedLangChainChatModel) -> bool:
    """Whether the model chosen *right now* is the stand-in rather than a real one.

    Asked per call, not once at build, for the same reason `supports_batch` is: a workspace
    changes its model through `PUT /api/models/selection` while the process runs, and a
    chain chosen when the graph was built would keep answering deterministically for a
    reviewer who had just picked Gemini.

    This is the whole of the dispatch. What each capability then does lives in
    `deterministic.py`; here it is one line, so that the module about which model is
    selected is not also the module about what to do when none is.
    """

    config = selected.configuration()
    return config is not None and config.provider == "fake"


def _batching_enabled() -> bool:
    """Batching is on by default and can be turned off without changing the model."""

    return os.environ.get("ARCHCOMPASS_GOOGLE_BATCH", "1").strip().lower() not in {
        "0",
        "false",
        "no",
        "off",
    }


def _investigation_enabled() -> bool:
    """Hinge investigation is on by default and can be turned off without changing the model.

    The graph already treats it as optional — `ReviewWorkflowCapabilities.investigator`
    defaults to `NoHingeInvestigation`, and a workspace on a model that cannot call tools
    asks its questions the way it always asked them — so this switch selects between two
    configurations the product already supports rather than introducing a third.

    It exists because the pass is not free and its value is not uniform. Up to eight held
    findings, six tool turns each, and a structured call to close every one of them: on a
    hosted tier that is a rounding error, and on one local GPU it is minutes added to a
    review before anybody is asked anything. An operator who would rather be asked the
    question than have it checked first can say so without moving off their model.
    """

    return os.environ.get("ARCHCOMPASS_HINGE_INVESTIGATION", "1").strip().lower() not in {
        "0",
        "false",
        "no",
        "off",
    }


class SelectedLangChainJudge:
    def __init__(
        self,
        selected: SelectedLangChainChatModel,
        refusals: BatchRefusalStore | None = None,
    ) -> None:
        self._selected = selected
        self._refusals = refusals or InMemoryBatchRefusals()
        self._batch_refused = False

    def judge(
        self,
        candidate: Candidate,
        case: ArchitectureCase,
        policies: RetrievedPolicySet,
    ) -> Finding:
        if _is_deterministic(self._selected):
            return DeterministicJudge().judge(candidate, case, policies)
        model, identity = self._selected.current()
        return LangChainArchitectureJudge(model, model_identity=identity).judge(
            candidate, case, policies
        )

    def supports_batch(self) -> bool:
        """Only where the selected provider actually meters a batch separately.

        Asked per call rather than answered once, because the model is chosen while the
        workspace is running: the same graph judges through a batch this afternoon and
        through Ollama this evening.
        """

        config = self._selected.configuration()
        if config is None or config.provider != "google":
            return False
        if not _batching_enabled():
            return False
        # A key the API has already turned away is not asked again. The refusal is about
        # the project behind the key and not about this batch, so it does not expire when
        # the process does — remembering it only in memory meant every restart paid another
        # rejected submission, and showed another reader a review that said it had queued a
        # batch and had not. A different key gets a fresh answer, because a different key
        # may be on a project that is eligible.
        if self._batch_refused:
            return False
        try:
            api_key = resolve_api_key(config.api_key_env, provider="google")
        except Exception:
            # Not this method's refusal to make. A missing key fails loudly further in,
            # with a message that names the variable to set.
            return True
        return not self._refusals.refused(api_key)

    def judge_all(
        self,
        requests: Sequence[JudgementRequest],
        *,
        observe: Callable[[BatchOutcome], None] | None = None,
    ) -> tuple[Finding, ...]:
        """Every candidate at once, batched where that means something.

        The fallback is not a lesser path: for Ollama and the deterministic provider a
        loop is exactly what a batch would be, and running it here keeps the graph's
        dispatch decision in one place instead of two.

        `observe` is told what the provider did, and only ever after it has done it. A
        review can be routed here and still be judged one candidate at a time, so anything
        that reports a batch to a person has to hear it from the submission rather than
        from the routing.
        """

        if not requests:
            return ()
        config = self._selected.configuration()
        if config is None or config.provider != "google":
            if observe is not None:
                observe("unavailable")
            return self._judge_each(requests, config)

        _, identity = self._selected.current()
        api_key = resolve_api_key(config.api_key_env, provider="google")
        judge = GoogleBatchJudge(
            api_key=api_key,
            model=config.model,
            thinking=config.thinking,
        )
        try:
            return judge.judge_all(requests, model_identity=identity, observe=observe)
        except BatchUnavailableError as refusal:
            # A batch is an optimisation, not a requirement. Losing a review that the
            # interactive path could have produced is a worse outcome than judging it the
            # slow way, so this degrades and says so rather than failing.
            _log.warning("%s", refusal)
            self._refusals.record(api_key)
            self._batch_refused = True
            if observe is not None:
                observe("unavailable")
            return self._judge_each(requests, config)

    def _judge_each(
        self, requests: Sequence[JudgementRequest], config: ReasoningModelConfig | None
    ) -> tuple[Finding, ...]:
        workers = max(1, config.concurrent_requests if config is not None else 1)
        if workers == 1:
            return tuple(
                self.judge(item.candidate, item.case, item.policies)
                for item in requests
            )

        def judge_one(item: JudgementRequest) -> Finding:
            return self.judge(item.candidate, item.case, item.policies)

        with ThreadPoolExecutor(max_workers=workers) as pool:
            return tuple(pool.map(judge_one, requests))


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
        model, _ = self._selected.current()
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
        model, identity = self._selected.current()
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
        model, _ = self._selected.current()
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
    ) -> InvestigatedFinding:
        if _is_deterministic(self._selected):
            return DeterministicHingeInvestigator(self._investigators).investigate(
                finding, case, repository=repository, atlas=atlas
            )
        try:
            model, identity = self._selected.current()
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
            return InvestigatedFinding(finding)

