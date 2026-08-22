"""Lazy LangChain models selected at the application boundary."""

from __future__ import annotations

import logging
import os
from collections.abc import Callable, Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from threading import Lock

from langchain_core.language_models import BaseChatModel

from archcompass.configuration import ReasoningModelConfig, resolve_api_key
from archcompass.domain import (
    ArchitectureCase,
    Candidate,
    CaseFacet,
    Finding,
    Question,
    RepositoryAtlas,
    RepositoryRef,
    Review,
    ReviewDelta,
    Verdict,
)
from archcompass.domain.errors import NoReasoningModelSelectedError, ProviderError
from archcompass.ports.batch_refusals import (
    BatchRefusalStore,
    InMemoryBatchRefusals,
)
from archcompass.ports.capabilities import (
    BatchOutcome,
    InvestigatedFinding,
    JudgementRequest,
    ReviewSynopsis,
)
from archcompass.ports.investigation import InvestigatorSource
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
from archcompass.reasoning.adapters.investigation import (
    LangChainHingeInvestigator,
    recorded_investigation,
)
from archcompass.reasoning.adapters.langchain import (
    LangChainArchitectureJudge,
    LangChainQuestionGenerator,
    LangChainReviewAnswerer,
    LangChainReviewSynopsist,
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
            raise ValueError(
                "the deterministic provider has no LangChain chat transport"
            )
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
        config = self._selected.configuration()
        if config is not None and config.provider == "fake":
            # This provider does not judge; it stands in for one. It holds while nobody has
            # answered anything, so that the clarification path is exercised rather than
            # skipped, and clears once the case records an answer. Answers are the only
            # thing left to hold on: the goal went first, then the hand-authored
            # constraints and decisions, and what remains is the channel a review fills.
            hinge = (
                None
                if case.answers
                else "whether these boundaries are deliberate or speculative"
            )
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
        config = self._selected.configuration()
        if config is not None and config.provider == "fake":
            held = tuple(item for item in findings if item.hinge)
            if not held:
                return ()
            # Proposed answers, because a question without them is a blank box and a blank
            # box is not what this round looks like. The deterministic provider is how the
            # clarification is seen during development and in the browser suite, and one
            # that showed a textarea where the product shows a menu was teaching the wrong
            # shape. Asked about the boundaries in front of it rather than about a "goal",
            # which is the facet the case retired.
            question = Question.create(
                text=(
                    "These boundaries each have exactly one implementation today. Is that "
                    "deliberate?"
                ),
                facet=CaseFacet.DECISION,
                candidate_ids=tuple(str(item.candidate.id) for item in held),
                round=round,
                options=(
                    "The boundaries are deliberate: a second implementation is expected "
                    "and the seam is being held open for it.",
                    "The boundaries are there to keep the domain testable, and a second "
                    "implementation is not expected.",
                    "The boundaries were speculative and we would collapse them if a "
                    "review said so.",
                ),
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
        config = self._selected.configuration()
        if config is not None and config.provider == "fake":
            material = tuple(
                item for item in findings if item.verdict is Verdict.MATERIAL
            )
            held = tuple(item for item in findings if item.hinge)
            said = (
                "none are material"
                if not material
                else "the material ones are "
                + ", ".join(
                    f"`{item.candidate.participants[0].qualified_name}`"
                    for item in material
                )
            )
            waits = (
                ""
                if not held
                else f" {len(held)} of them "
                + ("is" if len(held) == 1 else "are")
                + " waiting on an answer from a person."
            )
            return ReviewSynopsis(
                f"This summary was composed deterministically rather than written by a "
                f"model. Of {len(findings)} candidates judged, {said}.{waits}",
                f"fake:{config.model}",
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
        config = self._selected.configuration()
        if config is not None and config.provider == "fake":
            supporting = tuple(str(item.candidate.id) for item in review.findings[:1])
            # Real lookups behind a stood-in answer, for the reason the hinge pass does the
            # same: this is the provider every offline test and local run uses, and a
            # transcript nothing renders is a transcript nothing checks.
            offered = (
                None
                if self._investigators is None
                else self._investigators.for_review(review.repository, review.atlas)
            )
            investigator = None if offered is None else offered.investigator
            if investigator is not None:
                investigator.call("flagged_signals", {})
                investigator.conclude("The stored review already answers this.", "")
            return ConversationAnswer(
                "The stored review is the source of this deterministic answer.",
                supporting,
                recorded_investigation(
                    investigator,
                    candidate_id="",
                    withheld="" if offered is None else offered.withheld,
                    atlas_fingerprint=review.repository.content_id,
                    model_identity=f"fake:{config.model}",
                ),
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

        config = self._selected.configuration()
        if config is None:
            return False
        if config.provider == "fake":
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
        config = self._selected.configuration()
        if config is not None and config.provider == "fake":
            return self._deterministic(finding, case, repository, atlas, config)
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
            self._tools_refused = isinstance(error, NotImplementedError)
            return InvestigatedFinding(finding)

    def _deterministic(
        self,
        finding: Finding,
        case: ArchitectureCase,
        repository: RepositoryRef,
        atlas: RepositoryAtlas,
        config: ReasoningModelConfig,
    ) -> InvestigatedFinding:
        """Real lookups, a fixed conclusion.

        The lookups are genuine — the same toolbox over the same atlas — because a
        transcript nothing renders is a transcript nothing checks, and this is the provider
        every offline test, browser run and local `make web` uses. What is stood in for is
        only the judgement about them, which follows the deterministic judge's own rule:
        held while the case says nothing, settled once somebody has answered.
        """

        offered = self._investigators.for_review(repository, atlas)
        investigator = offered.investigator
        if investigator is not None:
            names = [item.qualified_name for item in finding.candidate.participants]
            if names:
                investigator.call("find_code", {"name": names[0].rsplit(".", 1)[-1]})
            investigator.conclude(
                "The deterministic provider looked, and reports what it was shown.", ""
            )
        resolved = bool(case.answers)
        record = recorded_investigation(
            investigator,
            candidate_id=str(finding.candidate.id),
            withheld=offered.withheld,
            resolved=resolved,
            atlas_fingerprint=repository.content_id,
            model_identity=f"fake:{config.model}",
        )
        identity = "" if record is None else record.identity
        if not resolved:
            return InvestigatedFinding(
                replace(finding, investigation_identity=identity), record
            )
        return InvestigatedFinding(
            replace(
                finding,
                verdict=Verdict.CLEARED,
                reasoning=(
                    "The deterministic provider checked the repository and found nothing "
                    "the case does not already settle."
                ),
                hinge=None,
                investigation_identity=identity,
            ),
            record,
        )
