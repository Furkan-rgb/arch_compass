"""Lazy LangChain models selected at the application boundary."""

from __future__ import annotations

import logging
from collections.abc import Callable, Generator
from contextlib import contextmanager
from dataclasses import dataclass, replace
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
from archcompass.reasoning.adapters.langchain import (
    LangChainArchitectureJudge,
    LangChainQuestionGenerator,
    LangChainReviewAnswerer,
    LangChainReviewSynopsist,
)
from archcompass.reasoning.adapters.openrouter import observed_route
from archcompass.reasoning.adapters.providers import DETERMINISTIC_DESCRIPTOR
from archcompass.reasoning.adapters.review_tools import ReviewToolbox
from archcompass.reasoning.ports import (
    ConversationAnswer,
    ConversationMessage,
    SelectedReasoningModel,
)
from archcompass.reasoning.records import model_identity


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
        # No branch for the stand-in here, deliberately. Every caller of `in_use` has already
        # asked `in_force().deterministic` and gone the other way if it was true, so a second
        # test of the provider on this path could only ever disagree with that one — and a
        # stored selection naming a provider `build_chat_model` cannot build still refuses,
        # by the `ConfigurationError` it raises for any provider it has no branch for.
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


@dataclass(frozen=True)
class JudgementInForce:
    """One reading of the model selection, answering every question a run asks of it.

    Built only by `SelectedLangChainJudge.in_force`, and built whole: the selection, what a
    finding it produces is stamped with, which judge runs, what that judge stamps as its
    prompt, and whether it reaches a provider at all. There is no way to obtain one of those
    without the rest, which is the whole reason the record exists — `bootstrap` used to hold
    a `selected_model_identity()`, a `selected_prompt_identity()` and a
    `deterministic_retrieval_mode()`, three callbacks that each re-read the selection at a
    different moment and each re-derived a fact from it. Two of them derived it differently,
    and `records.py` records what that cost. The third name is still there, over a caller
    that now reads `deterministic` off this record instead of testing the provider itself;
    what it kept is a refusal only the retriever can make, not a derivation.

    `prompt_identity` is not a field. It is read off the class in `judge`, so the value the
    revision delta and the finding cache compare against is produced by the same object that
    stamps it, and a judge added here without its identity is a judge that does not compile.
    That is the part the two previous fixes of this defect did not have: they made both sides
    read one constant, which held until a third judge arrived with a constant of its own.

    `built_over` is how that judge is opened over a transport, and it is written in the same
    expression that names the class — so the pair cannot come apart the way a class named
    here and built somewhere else could. It is `None` for the stand-in, which reaches no
    provider and therefore has no transport to be opened over; that is also what
    `deterministic` means, rather than a second reading of the provider name.

    `deterministic` is the answer the other three capabilities take from this record too.
    The question generator, the synopsist and the answerer each fork between the stand-in
    and a real model, and each used to fork on a `_is_deterministic` helper here that spelled
    the provider test out a second time — the same shape as the defect above, one branch of
    one decision away from the branch that stamps what the delta compares against. They are
    handed this method now, so the four capabilities cannot disagree about which chain a
    workspace has selected.
    """

    #: What this workspace has selected, or `None` where it has selected nothing yet. Kept
    #: because a caller that has to refuse — the retriever, which cannot pick an embedding
    #: mode without one — needs to tell "nothing selected" from "the stand-in".
    model: ReasoningModelConfig | None
    #: What a finding produced under this selection carries as `Finding.model_identity`.
    #: Empty where nothing is selected, because there is no model to name.
    model_identity: str
    judge: (
        type[DeterministicJudge]
        | type[LangChainArchitectureJudge]
        | type[DeepArchitectureJudge]
    )
    built_over: (
        Callable[[BaseChatModel, str], LangChainArchitectureJudge | DeepArchitectureJudge]
        | None
    )

    @property
    def prompt_identity(self) -> str:
        return self.judge.identity

    @property
    def deterministic(self) -> bool:
        return self.built_over is None


class SelectedLangChainJudge:
    """The judge in force, and whether it is one that can read the repository.

    `toolbox` is what decides, and it is the only thing that does. With one, the judgement is
    a bounded conversation that may look things up — and where a particular run carries
    nothing to look at, that same judge falls back to one structured call rather than being
    handed to a different judge. Without a toolbox it is the single structured call it has
    always been. Both reach the same `FindingOutput`.

    That the subject no longer chooses is the point of `in_force` below being answerable at
    all: what a review is stamped with must not depend on a fact that only exists once the
    review is running.

    The model is resolved through `in_use` and held for the whole judgement rather than for
    each request inside it. That matters more here than it did: a judgement that looks things
    up is a dozen requests, and a local runner with one slot would otherwise interleave them
    with another candidate's.

    That same span is what `Finding.served_by` is observed over — see `judge` below.
    """

    def __init__(
        self,
        selected: SelectedLangChainChatModel,
        toolbox: ReviewToolbox | None = None,
    ) -> None:
        self._selected = selected
        self._toolbox = toolbox

    def in_force(self) -> JudgementInForce:
        """Which judge the next judgement is, and everything that follows from that.

        The one place any of it is decided. `CachingArchitectureJudge` keys on the record,
        `DeterministicRevisionCalculator` compares a stored finding's stamps against it,
        `bootstrap` asks it whether the retriever is in deterministic mode, and the question
        generator, the synopsist and the answerer ask it which chain answers them — all six
        hold this method rather than a constant or a rule of their own, so no reader can
        compare against a value produced by a different branch of the same decision than the
        value that was stamped.

        Asked per call, not once at build: a workspace changes its model through
        `PUT /api/models/selection` while the process runs, and a record read once at build
        time would go on describing a model a reviewer had already replaced — a chain chosen
        when the graph was built would still be answering deterministically for somebody who
        had just picked Gemini. When that reading takes effect is unchanged by this being one
        record rather than three callbacks — see "Intentional complexity" in
        `docs/architecture.md`.

        The three returns below are the entire dispatch, and each of them names a judge class
        and builds from that same class in one expression. Anything that could fork the judge
        and is *not* one of these three is a fork nothing can report — which is what `subject`
        was until `judge` below stopped forking on it.
        """

        config = self._selected.configuration()
        if config is not None and config.provider == DETERMINISTIC_DESCRIPTOR.name:
            # The one place the stand-in is recognised, and it recognises it by the name the
            # provider registers rather than by a copy of that name. Both halves of that are
            # load-bearing, and both have failed here before: `bootstrap` carried its own
            # `provider == "fake"` mapping the provider to `DETERMINISTIC_MODEL_IDENTITY` for
            # the revision calculator while the stand-in stamped the same constant from
            # `deterministic.py`, and three capabilities below carried a `_is_deterministic`
            # of their own. Both halves are held from the source, by the stand-in sweeps in
            # `test_boundaries.py` — the block of them that shares the `_STAND_IN_*`
            # constants, starting at
            # `test_the_stand_in_provider_is_written_out_in_exactly_one_place`.
            #
            # How far those reach, and what they decline to reach, is deliberately not
            # written out here. A sentence describing a sweep is a copy of the sweep, and a
            # copy of a rule is the defect this whole comment is about, one level up: the
            # sweep moves and the sentence does not. This comment carried such a sentence
            # twice and it was false both times, each claiming more coverage than the sweeps
            # had. The draft that replaced it named the spellings that escaped instead, and
            # that went stale the same day, because a new sweep closed them while it was
            # being written. Even the number of those sweeps has moved since this paragraph
            # was first typed, which is why no number is given.
            #
            # Read the docstrings on those tests and on `_stand_in_spellings`. Each of them
            # states its own reach and its own limits, and each sits beside the code that
            # decides them, so the two move together — which is the property no sentence here
            # can have.
            return JudgementInForce(
                model=config,
                model_identity=DeterministicJudge.model_identity,
                judge=DeterministicJudge,
                built_over=None,
            )
        # An unselected workspace answers rather than raising, because the revision delta is
        # calculated before anything asks a provider for anything, and a review of a branch
        # nobody has chosen a model for still has to say what changed. The empty identity is
        # what a stored finding is then compared against, and it matches nothing — which is
        # the honest answer to "was this judged by the model in force".
        identity = "" if config is None else model_identity(config)
        toolbox = self._toolbox
        if toolbox is None:
            return JudgementInForce(
                model=config,
                model_identity=identity,
                judge=LangChainArchitectureJudge,
                built_over=lambda model, stamp: LangChainArchitectureJudge(
                    model, model_identity=stamp
                ),
            )
        return JudgementInForce(
            model=config,
            model_identity=identity,
            judge=DeepArchitectureJudge,
            built_over=lambda model, stamp: DeepArchitectureJudge(
                model, toolbox, model_identity=stamp
            ),
        )

    def judge(
        self,
        candidate: Candidate,
        case: ArchitectureCase,
        policies: RetrievedPolicySet,
        investigation: RecordedInvestigation | None = None,
        *,
        subject: ReviewedSubject | None = None,
    ) -> Finding:
        # The toolbox alone decides which judge this is, and a missing `subject` no longer
        # sends the judgement to the other one. `DeepArchitectureJudge` has its own fallback
        # for having nothing to look at — the same single structured call, from the same
        # prompt — and it stamps its own identity on the way out of it. Forking here instead
        # meant one run stamped `judge:deep-v2` and the next stamped `judge:v3` over a
        # difference `in_force` cannot see, because whether a run carries a subject is not
        # knowable until the run happens.
        #
        # `investigation` is forwarded and dropped inside: the second pass that used to
        # produce one no longer exists, and forwarding it keeps the port's shape honest for
        # the one caller — `CachingArchitectureJudge` — that still passes whatever it was
        # given straight through.
        built_over = self.in_force().built_over
        if built_over is None:
            return DeterministicJudge().judge(
                candidate, case, policies, investigation, subject=subject
            )
        with self._selected.in_use() as (model, identity), observed_route() as route:
            finding = built_over(model, identity).judge(
                candidate, case, policies, investigation, subject=subject
            )
        # Which endpoint served the judgement is stamped here rather than inside either
        # judge, and afterwards rather than passed down, because the observation is only
        # complete when the last request is. A judgement is a conversation of up to
        # twenty-six requests and the gateway routes each of them separately, so there is no
        # moment inside a judge at which the finished value could be handed to
        # `finding_from_output` — and there is one here, when the block closes. This is also
        # the only layer that knows which provider is in force, which is what keeps
        # `langchain.py` and `deep_judge.py` free of any notion of a gateway: on Ollama the
        # record stays empty and this writes back the empty string the field already had.
        return replace(finding, served_by=route.served_by)


class SelectedLangChainQuestionGenerator:
    """The clarification round, asked by whichever chain is in force.

    `in_force` is `SelectedLangChainJudge.in_force` — the same bound method the revision
    calculator and the finding cache hold, and the reason this class takes it rather than
    testing the provider itself is written out on `JudgementInForce`.
    """

    def __init__(
        self,
        selected: SelectedLangChainChatModel,
        in_force: Callable[[], JudgementInForce],
    ) -> None:
        self._selected = selected
        self._in_force = in_force

    def generate(
        self,
        case: ArchitectureCase,
        findings: tuple[Finding, ...],
        *,
        round: int,
        excluded_equivalence_keys: frozenset[str],
    ) -> tuple[Question, ...]:
        if self._in_force().deterministic:
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

    `in_force` is `SelectedLangChainJudge.in_force`, for the reason given on the question
    generator above: which chain answers is one decision, taken in one place.
    """

    def __init__(
        self,
        selected: SelectedLangChainChatModel,
        in_force: Callable[[], JudgementInForce],
    ) -> None:
        self._selected = selected
        self._in_force = in_force

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
        if self._in_force().deterministic:
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
    """A reader's question about a review, answered by the chain that is in force.

    `in_force` is `SelectedLangChainJudge.in_force`, for the reason given on the question
    generator above: which chain answers is one decision, taken in one place.
    """

    def __init__(
        self,
        selected: SelectedLangChainChatModel,
        in_force: Callable[[], JudgementInForce],
        toolbox: ReviewToolbox | None = None,
    ) -> None:
        self._selected = selected
        self._in_force = in_force
        self._toolbox = toolbox

    def answer(
        self,
        review: Review,
        history: tuple[ConversationMessage, ...],
        question: str,
        *,
        about: Question | None = None,
    ) -> ConversationAnswer:
        if self._in_force().deterministic:
            return DeterministicAnswerer(self._toolbox).answer(
                review, history, question, about=about
            )
        with self._selected.in_use() as (model, identity):
            return LangChainReviewAnswerer(
                model, self._toolbox, model_identity=identity
            ).answer(review, history, question, about=about)
