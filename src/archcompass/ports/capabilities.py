"""Application seams used one-for-one by the review graph.

The protocols describe ArchCompass operations, never a library.  LangGraph sequences them;
adapters decide whether an implementation uses LangChain, SQLite, or deterministic Python.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol

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
    """The one component allowed to say what a candidate means.

    `investigation` is what a hinged finding's lookups established, and it is passed on the
    second judgement of the same candidate rather than the first. It is kept apart from the
    candidate's own evidence on purpose: evidence is application-selected, and observations
    are what a model asked to see. A judge may weigh both; nothing may promote one into the
    other.
    """

    def judge(
        self,
        candidate: Candidate,
        case: ArchitectureCase,
        policies: RetrievedPolicySet,
        investigation: RecordedInvestigation | None = None,
    ) -> Finding: ...


class HingeInvestigator(Protocol):
    """A second, bounded pass over the findings that stopped to ask a person.

    Judging is one structured call over pinned evidence. When a verdict turns on a fact
    that evidence does not carry, the judgement emits a hinge, and a hinge stops the
    review. Many hinges are answerable from the repository itself, and stopping to ask a
    person something the repository could have answered is the worst outcome the charter
    names.

    So this pass gets read-only lookups and one job: establish what the repository says
    about the hinge. It returns the record of that and nothing else — no verdict, no
    reasoning, no recommendation, not even a narrowed question. All of those are readings
    of the facts rather than facts, and `ArchitectureJudge` is the one component allowed to
    make them.

    It used to return the finding, changed. That made two components able to mint an
    architecture verdict under two different contracts, and the weaker of the two — this
    one, which sees policy titles rather than their guidance — could overwrite the stronger.
    Measured on a local model, four investigations in twelve returned a verdict that their
    own reasoning argued against.

    Whether the selected model can call tools is asked per dispatch rather than answered at
    startup, for the same reason `_is_deterministic` is asked per call: the model is
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
    ) -> RecordedInvestigation | None:
        """What was looked up, or `None` where there was nothing to record at all."""
        ...


class QuestionGenerator(Protocol):
    def generate(
        self,
        case: ArchitectureCase,
        findings: tuple[Finding, ...],
        *,
        round: int,
        excluded_equivalence_keys: frozenset[str],
    ) -> tuple[Question, ...]: ...


class CaseReviser(Protocol):
    """The case a review is judged against, over the life of that one review.

    Three methods because a revision has three moments and only the graph knows which one
    it is in. `open` takes the number, once, the first time this review has an answer to
    record. `revise` adds a round's answers to the revision that is open. `seal` writes it,
    at the end, so that a review which asked and was never answered leaves no revision
    behind and a review which asked three times leaves exactly one.
    """

    def open(self, case: ArchitectureCase) -> ArchitectureCase: ...

    def revise(
        self, case: ArchitectureCase, answers: Sequence[Answer]
    ) -> ArchitectureCase: ...

    def seal(self, case: ArchitectureCase) -> ArchitectureCase: ...


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
    #: Which clarification round this snapshot is being composed in. Defaulted because a
    #: review that never asks is only ever in the first one.
    round: int = 1


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
