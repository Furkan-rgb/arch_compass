"""Lazy LangChain models selected at the application boundary."""

from __future__ import annotations

import logging
import os
from collections.abc import Sequence
from concurrent.futures import ThreadPoolExecutor
from threading import Lock

from langchain_core.language_models import BaseChatModel

from archcompass.configuration import ReasoningModelConfig, resolve_api_key
from archcompass.domain import (
    ArchitectureCase,
    Candidate,
    CaseFacet,
    Finding,
    Question,
    Review,
    Verdict,
)
from archcompass.domain.errors import NoReasoningModelSelectedError
from archcompass.ports.capabilities import JudgementRequest
from archcompass.ports.model_catalog import SelectedReasoningModel
from archcompass.ports.policy_retrieval import RetrievedPolicySet
from archcompass.ports.review_conversation import (
    ConversationAnswer,
    ConversationMessage,
)
from archcompass.reasoning.adapters.factory import build_chat_model
from archcompass.reasoning.adapters.google_batch import (
    BatchUnavailableError,
    GoogleBatchJudge,
)
from archcompass.reasoning.adapters.langchain import (
    LangChainArchitectureJudge,
    LangChainQuestionGenerator,
    LangChainReviewAnswerer,
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
        identity = f"{config.provider}:{config.model}:thinking={config.thinking}"
        if config.provider == "fake":
            raise ValueError("the deterministic provider has no LangChain chat transport")
        with self._lock:
            if self._cached is None or self._cached[0] != identity:
                self._cached = (identity, build_chat_model(config))
            return self._cached[1], identity


_log = logging.getLogger("archcompass.batch")


def _batching_enabled() -> bool:
    """Batching is on by default and can be turned off without changing the model."""

    return os.environ.get("ARCHCOMPASS_GOOGLE_BATCH", "1").strip().lower() not in {
        "0",
        "false",
        "no",
        "off",
    }


class SelectedLangChainJudge:
    def __init__(self, selected: SelectedLangChainChatModel) -> None:
        self._selected = selected
        self._batch_refused = False

    def judge(
        self,
        candidate: Candidate,
        case: ArchitectureCase,
        policies: RetrievedPolicySet,
    ) -> Finding:
        config = self._selected.configuration()
        if config is not None and config.provider == "fake":
            # This provider does not judge; it stands in for one. It holds while the case
            # says nothing at all about intent, so that the clarification path is
            # exercised rather than skipped, and clears once anything has been recorded.
            # It used to hold on the architecture goal, which no longer exists — intent
            # now arrives as constraints, decisions and answered questions.
            stated = case.constraints or case.decisions or case.answers
            hinge = None if stated else "the constraints this architecture has to respect"
            return Finding(
                candidate,
                Verdict.HELD if hinge else Verdict.CLEARED,
                (
                    "The deterministic provider holds this finding until the case says "
                    "something about intent."
                    if hinge
                    else "The deterministic provider found no material conflict in the case."
                ),
                (),
                candidate.evidence,
                hinge=hinge,
                model_identity=f"fake:{config.model}",
                prompt_identity="judge:deterministic-v1",
                retrieval_identity=policies.provenance.identity,
            )
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
        # A key the API has already turned away is not asked again for the life of this
        # process: the refusal is about the project, not about this batch, and retrying it
        # once per review would cost a pointless round trip before every judgement.
        if self._batch_refused:
            return False
        return _batching_enabled()

    def judge_all(self, requests: Sequence[JudgementRequest]) -> tuple[Finding, ...]:
        """Every candidate at once, batched where that means something.

        The fallback is not a lesser path: for Ollama and the deterministic provider a
        loop is exactly what a batch would be, and running it here keeps the graph's
        dispatch decision in one place instead of two.
        """

        if not requests:
            return ()
        config = self._selected.configuration()
        if config is None or config.provider != "google":
            return self._judge_each(requests, config)

        _, identity = self._selected.current()
        judge = GoogleBatchJudge(
            api_key=resolve_api_key(config.api_key_env, provider="google"),
            model=config.model,
        )
        try:
            return judge.judge_all(requests, model_identity=identity)
        except BatchUnavailableError as refusal:
            # A batch is an optimisation, not a requirement. Losing a review that the
            # interactive path could have produced is a worse outcome than judging it the
            # slow way, so this degrades and says so rather than failing.
            _log.warning("%s", refusal)
            self._batch_refused = True
            return self._judge_each(requests, config)

    def _judge_each(
        self, requests: Sequence[JudgementRequest], config: ReasoningModelConfig | None
    ) -> tuple[Finding, ...]:
        workers = max(1, config.concurrent_requests if config is not None else 1)
        if workers == 1:
            return tuple(
                self.judge(item.candidate, item.case, item.policies) for item in requests
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
        config = self._selected.configuration()
        if config is not None and config.provider == "fake":
            held = tuple(item for item in findings if item.hinge)
            if not held:
                return ()
            question = Question.create(
                text="What outcome should this architecture optimize for?",
                facet=CaseFacet.GOAL,
                candidate_ids=tuple(str(item.candidate.id) for item in held),
                round=round,
            )
            return (
                ()
                if question.equivalence_key in excluded_equivalence_keys
                else (question,)
            )
        model, _ = self._selected.current()
        return LangChainQuestionGenerator(model).generate(
            case,
            findings,
            round=round,
            excluded_equivalence_keys=excluded_equivalence_keys,
        )


class SelectedLangChainReviewAnswerer:
    def __init__(self, selected: SelectedLangChainChatModel) -> None:
        self._selected = selected

    def answer(
        self,
        review: Review,
        history: tuple[ConversationMessage, ...],
        question: str,
    ) -> ConversationAnswer:
        config = self._selected.configuration()
        if config is not None and config.provider == "fake":
            supporting = tuple(str(item.candidate.id) for item in review.findings[:1])
            return ConversationAnswer(
                "The stored review is the source of this deterministic answer.", supporting
            )
        model, _ = self._selected.current()
        return LangChainReviewAnswerer(model).answer(review, history, question)
