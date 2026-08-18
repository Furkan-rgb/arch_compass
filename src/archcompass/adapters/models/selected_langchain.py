"""Lazy LangChain models selected at the application boundary."""

from __future__ import annotations

from threading import Lock

from langchain_core.language_models import BaseChatModel

from archcompass.adapters.models.langchain_boundary import (
    LangChainArchitectureJudge,
    LangChainQuestionGenerator,
    LangChainReviewAnswerer,
)
from archcompass.adapters.models.langchain_factory import build_chat_model
from archcompass.configuration import ReasoningModelConfig
from archcompass.domain.core import (
    ArchitectureCase,
    Candidate,
    CaseFacet,
    Finding,
    Question,
    Review,
    Verdict,
)
from archcompass.domain.errors import NoReasoningModelSelectedError
from archcompass.ports.model_catalog import SelectedReasoningModel
from archcompass.ports.policy_retrieval import RetrievedPolicySet
from archcompass.ports.review_conversation import (
    ConversationAnswer,
    ConversationMessage,
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


class SelectedLangChainJudge:
    def __init__(self, selected: SelectedLangChainChatModel) -> None:
        self._selected = selected

    def judge(
        self,
        candidate: Candidate,
        case: ArchitectureCase,
        policies: RetrievedPolicySet,
    ) -> Finding:
        config = self._selected.configuration()
        if config is not None and config.provider == "fake":
            hinge = None if case.goal else "the architecture goal"
            return Finding(
                candidate,
                Verdict.HELD if hinge else Verdict.CLEARED,
                (
                    "The deterministic provider holds this finding until the goal is stated."
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
