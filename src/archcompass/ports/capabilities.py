"""Application seams used one-for-one by the review graph.

The protocols describe ArchCompass operations, never a library.  LangGraph sequences them;
adapters decide whether an implementation uses LangChain, SQLite, or deterministic Python.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Literal, Protocol, runtime_checkable

from archcompass.domain import (
    Answer,
    ArchitectureCase,
    Candidate,
    Finding,
    Policy,
    Question,
    RecordedInvestigation,
    RepositoryAtlas,
    RepositoryRef,
    Review,
    ReviewDelta,
)
from archcompass.ports.policy_retrieval import RetrievedPolicySet


class RepositoryAnalyzer(Protocol):
    def analyze(self, repository: RepositoryRef) -> RepositoryAtlas: ...


class CandidateDetector(Protocol):
    def detect(self, atlas: RepositoryAtlas) -> tuple[Candidate, ...]: ...


class RevisionCalculator(Protocol):
    def calculate(
        self,
        candidates: tuple[Candidate, ...],
        case: ArchitectureCase,
        previous: Review | None,
        repository: RepositoryRef,
        history: tuple[Review, ...] = (),
    ) -> ReviewDelta: ...


class PolicyRetriever(Protocol):
    def retrieve(
        self,
        candidate: Candidate,
        case: ArchitectureCase,
        corpus: tuple[Policy, ...],
    ) -> RetrievedPolicySet: ...


class ArchitectureJudge(Protocol):
    def judge(
        self,
        candidate: Candidate,
        case: ArchitectureCase,
        policies: RetrievedPolicySet,
    ) -> Finding: ...


@dataclass(frozen=True, slots=True)
class JudgementRequest:
    """One candidate, and everything the model needs to judge it."""

    candidate: Candidate
    case: ArchitectureCase
    policies: RetrievedPolicySet


#: What a judge says about the batch it was asked for, while it is asking.
#:
#: `supports_batch` is a prediction — the provider is the only thing that knows whether it
#: will take a batch from this key, and it says so by accepting or refusing the submission.
#: So the prediction is not something to report to a person: a review that told its reader
#: it had queued a batch, on the strength of a routing decision, went on saying so through
#: the whole interactive fallback that followed a refusal. This is the observed half.
BatchOutcome = Literal["queued", "unavailable"]


@runtime_checkable
class BatchArchitectureJudge(Protocol):
    """A judge that can put a whole review to the model in one submission.

    A hosted provider meters interactive calls per minute and a batch of them per day,
    which is the difference between a review of forty candidates failing halfway through
    and finishing. Whether that is available depends on the model selected right now, not
    on how the graph was built, so `supports_batch` is asked at dispatch time rather than
    answered once at startup.

    `supports_batch` answering true is a prediction and never a promise. The Gemini Batch
    API refuses a project that is not eligible with `400 FAILED_PRECONDITION`, which cannot
    be known without submitting — so `judge_all` reports what actually happened through
    `observe`, and every caller that tells somebody about a batch has to wait for it.
    """

    def supports_batch(self) -> bool: ...

    def judge_all(
        self,
        requests: Sequence[JudgementRequest],
        *,
        observe: Callable[[BatchOutcome], None] | None = None,
    ) -> tuple[Finding, ...]: ...


@dataclass(frozen=True, slots=True)
class InvestigatedFinding:
    """One hinged finding after the lookups, and the record of what was looked up.

    `investigation is None` says nothing was recorded, which is the ordinary answer where
    no model could look. A record holding no lookups and a `withheld` sentence is the
    opposite of that: it says the repository could not be reached, and that is a fact about
    the question underneath it rather than an absence of one.
    """

    finding: Finding
    investigation: RecordedInvestigation | None = None


class HingeInvestigator(Protocol):
    """A second, bounded pass over the findings that stopped to ask a person.

    Judging is one structured call over pinned evidence. When a verdict turns on a fact
    that evidence does not carry, the judgement emits a hinge, and a hinge stops the
    review. Many hinges are answerable from the repository itself, and stopping to ask a
    person something the repository could have answered is the worst outcome the charter
    names.

    So this pass gets read-only lookups and one job: decide whether the question is worth a
    person's interruption. It may settle a held verdict or narrow the hinge. It may not
    touch a policy bearing, an excerpt, or a verdict that was never held — investigating
    informs *whether to ask*, never what a verdict rests on, and that is the whole of why
    it is allowed at all.

    Whether the selected model can call tools is asked per dispatch rather than answered at
    startup, for the same reason `BatchArchitectureJudge.supports_batch` is: the model is
    chosen while the workspace is running.
    """

    def supports_tools(self) -> bool: ...

    def investigate(
        self,
        finding: Finding,
        case: ArchitectureCase,
        *,
        repository: RepositoryRef,
        atlas: RepositoryAtlas,
    ) -> InvestigatedFinding: ...


class QuestionGenerator(Protocol):
    def generate(
        self,
        case: ArchitectureCase,
        findings: tuple[Finding, ...],
        *,
        round: int,
        excluded_equivalence_keys: frozenset[str],
    ) -> tuple[Question, ...]: ...


class RejudgementSelector(Protocol):
    def select(
        self,
        candidates: tuple[Candidate, ...],
        previous_case: ArchitectureCase,
        revised_case: ArchitectureCase,
    ) -> tuple[Candidate, ...]: ...


class CaseReviser(Protocol):
    def revise(
        self, case: ArchitectureCase, answers: Sequence[Answer]
    ) -> ArchitectureCase: ...


@dataclass(frozen=True, slots=True)
class ReviewSynopsis:
    """What the review amounts to, said by the model that judged it.

    A report opens on counts, and counts are orientation rather than an answer: "two
    material, three held" does not say whether the two are the same problem twice or which
    one to take first. This is the paragraph that does, and it is the model's — it reasons
    over verdicts it already reached and asserts nothing that is not in them.

    Written once, when the review is composed, and carried on the record. The alternative —
    composing it when somebody opens the report — would mean two readers of one immutable
    review seeing two different documents, and the downloaded Markdown matching neither.
    """

    text: str
    model_identity: str = ""


@dataclass(frozen=True, slots=True)
class ReviewDraft:
    repository: RepositoryRef
    atlas: RepositoryAtlas
    case: ArchitectureCase
    findings: tuple[Finding, ...]
    questions: tuple[Question, ...]
    delta: ReviewDelta
    previous: Review | None
    retrievals: tuple[RetrievedPolicySet, ...]
    synopsis: ReviewSynopsis | None = None
    investigations: tuple[RecordedInvestigation, ...] = ()


class ReviewSynopsisWriter(Protocol):
    """Prose over a finished set of judgements. Separate from the judge on purpose.

    `None` is a real answer and not a failure: a review with nothing judged has nothing to
    summarise, and a workspace with no model available should still compose its report.
    """

    def write(
        self,
        case: ArchitectureCase,
        findings: tuple[Finding, ...],
        *,
        questions: tuple[Question, ...],
        delta: ReviewDelta,
        previous: Review | None,
        waiting: bool,
    ) -> ReviewSynopsis | None: ...


class ReviewComposer(Protocol):
    def compose(self, draft: ReviewDraft, *, waiting: bool) -> Review: ...


class ReviewRecorder(Protocol):
    def record(self, review: Review) -> Review: ...


class PolicyCorpus(Protocol):
    def policies_for(self, repository: RepositoryRef) -> tuple[Policy, ...]: ...


@dataclass(frozen=True, slots=True)
class LoadedReviewContext:
    repository: RepositoryRef
    case: ArchitectureCase
    previous_review: Review | None
    review_history: tuple[Review, ...] = ()


class ContextLoader(Protocol):
    def load(
        self,
        repository_id: str,
        branch_id: str,
        case_id: str,
        case_revision: int | None,
    ) -> LoadedReviewContext: ...


@dataclass(frozen=True, slots=True)
class CandidateSelection:
    selected: tuple[Candidate, ...]
    carried_findings: tuple[Finding, ...] = ()


class InitialCandidateSelector(Protocol):

    def select(
        self,
        candidates: tuple[Candidate, ...],
        delta: ReviewDelta,
        previous: Review | None,
        ci: bool,
    ) -> CandidateSelection: ...
