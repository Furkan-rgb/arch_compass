from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from hashlib import sha256

from archcompass.domain._support import freeze_pairs, freeze_sequences, require_text
from archcompass.domain.atlas import RepositoryAtlas
from archcompass.domain.candidate import Candidate, CandidateId
from archcompass.domain.case import ArchitectureCase, Question
from archcompass.domain.finding import Finding, Verdict
from archcompass.domain.repository import RepositoryRef


class ReviewStatus(StrEnum):
    AWAITING_ANSWERS = "awaiting_answers"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class ChangeCause(StrEnum):
    CONTENT = "content"
    SHAPE = "shape"
    CASE = "case"
    POLICIES = "policies"
    MODEL = "model"
    PROMPT = "prompt"
    RESURFACED = "resurfaced"


@dataclass(frozen=True, slots=True)
class CandidateChange:
    candidate: Candidate
    causes: tuple[ChangeCause, ...]
    predecessor_id: CandidateId | None = None


@dataclass(frozen=True, slots=True)
class AddressedCandidate:
    candidate_id: CandidateId
    title: str
    last_seen_review_id: str
    last_verdict: Verdict


@dataclass(frozen=True, slots=True)
class ReviewDelta:
    unchanged: tuple[Candidate, ...] = ()
    changed: tuple[CandidateChange, ...] = ()
    new: tuple[Candidate, ...] = ()
    addressed: tuple[AddressedCandidate, ...] = ()

    def __post_init__(self) -> None:
        freeze_sequences(self, "unchanged", "changed", "new", "addressed")


@dataclass(frozen=True, slots=True)
class RetrievalProvenance:
    """Strategy-neutral audit of the policies selected for one candidate."""

    candidate_id: CandidateId
    retriever: str
    version: str
    corpus_fingerprint: str
    selected_policy_ids: tuple[str, ...]
    model_identity: str | None = None
    query_fingerprint: str | None = None
    metadata: tuple[tuple[str, str], ...] = ()

    def __post_init__(self) -> None:
        freeze_sequences(self, "selected_policy_ids")
        freeze_pairs(self, "metadata")

    @property
    def identity(self) -> str:
        material = (
            str(self.candidate_id),
            self.retriever,
            self.version,
            self.corpus_fingerprint,
            *self.selected_policy_ids,
            self.model_identity or "",
            self.query_fingerprint or "",
            *(f"{key}={value}" for key, value in self.metadata),
        )
        return sha256("\0".join(material).encode()).hexdigest()


@dataclass(frozen=True, slots=True)
class InvestigationLookup:
    """One thing a review asked the repository, and what the repository said.

    The port's `RecordedLookup` says the same three things and is deliberately not this.
    That one is a transport-side value handed between an adapter and a toolbox; this is
    part of a stored document, so it validates, serialises and reads back with everything
    else the review kept.
    """

    tool: str
    #: Exactly what was asked, so the lookup can be made again. A result nobody can
    #: reproduce is the unverifiable evidence the charter refuses, and the arguments are
    #: half of reproducing it. Pairs rather than a mapping, like `RetrievalProvenance`'s
    #: metadata: this domain is frozen dataclasses, and a dict on one is neither hashable
    #: nor frozen by the helpers every other record here uses.
    arguments: tuple[tuple[str, str], ...] = ()
    #: What came back, as the model was shown it — clamped, and including the refusals. A
    #: lookup that found nothing is kept for the same reason the useful ones are: "checked
    #: and empty" and "never checked" are opposite facts about a question.
    result: str = ""

    def __post_init__(self) -> None:
        require_text(self.tool, "lookup tool")
        freeze_pairs(self, "arguments")


@dataclass(frozen=True, slots=True)
class RecordedInvestigation:
    """What a review checked before it asked a person, kept with the review.

    This is what makes a hinge legible. A reader shown "is this seam deliberate?" cannot
    otherwise tell a question asked because the repository is silent from one asked
    because nothing looked — and that difference is the whole of whether the question is
    worth answering.

    No lookups beside a `withheld` sentence is a real state: nothing could look, and the
    reader is told why. No lookups beside an `abandoned` sentence is the other one: the
    looking started and stopped, so the hinge stands unchecked. Empty on every count is
    never stored.
    """

    candidate_id: CandidateId
    lookups: tuple[InvestigationLookup, ...] = ()
    #: The model's own account of which findings mattered. The one thing the lookups
    #: cannot hold, which is why it sits beside them rather than among them.
    closing: str = ""
    #: Why no lookup was possible at all — no atlas to ask, a model that cannot call
    #: tools. Distinct from `abandoned`, which is a looking that began and stopped short.
    withheld: str = ""
    #: Why the looking stopped short, or "" where it ran to its own end.
    abandoned: str = ""
    #: Whether the hinge was settled. Derivable from the finding, and kept here anyway so
    #: a reader of the manifest need not join back to learn what the looking was for.
    resolved: bool = False
    #: The content fingerprint of the repository these answers came from. A hinge settled
    #: by a lookup rests on code the candidate's own spans do not cover, so the record has
    #: to say which snapshot answered — without it nothing can tell a settled hinge from a
    #: stale one.
    atlas_fingerprint: str = ""
    prompt_identity: str = ""
    model_identity: str = ""

    def __post_init__(self) -> None:
        freeze_sequences(self, "lookups")

    @property
    def identity(self) -> str:
        material = (
            str(self.candidate_id),
            self.atlas_fingerprint,
            self.prompt_identity,
            self.model_identity,
            "resolved" if self.resolved else "held",
            *(
                f"{item.tool}("
                + ";".join(f"{key}={value}" for key, value in item.arguments)
                + f")\0{item.result}"
                for item in self.lookups
            ),
            self.closing,
            self.withheld,
            self.abandoned,
        )
        return sha256("\0".join(material).encode()).hexdigest()


@dataclass(frozen=True, slots=True)
class Review:
    id: str
    sequence: int
    repository: RepositoryRef
    atlas: RepositoryAtlas
    case: ArchitectureCase
    findings: tuple[Finding, ...]
    questions: tuple[Question, ...]
    status: ReviewStatus
    delta: ReviewDelta
    started_at: datetime
    finished_at: datetime | None = None
    previous_review_id: str | None = None
    markdown_report: str | None = None
    #: The model's own account of what this review found, written once when the review was
    #: composed and stored with it. Not derived on read: a review is a record, and prose
    #: that changed every time somebody opened it would not be part of one.
    synopsis: str | None = None
    #: Which model wrote that account. Kept apart from `model_identity`, which names the
    #: models that judged: a finding carried forward from an earlier review was judged by
    #: whatever was selected then, and the summary by whatever is selected now.
    synopsis_identity: str = ""
    retrieval_manifest: tuple[RetrievalProvenance, ...] = ()
    #: What each hinged finding checked against the repository before the review
    #: asked a person about it. Carried here rather than on the finding for the same
    #: reason the retrieval manifest is: a finding is cached, carried forward between
    #: reviews and compared by the delta, and one whose bytes changed when a lookup
    #: was recorded would compare as a different verdict.
    investigation_manifest: tuple[RecordedInvestigation, ...] = ()
    model_identity: str = ""
    prompt_identity: str = ""
    failure: str | None = None

    def __post_init__(self) -> None:
        freeze_sequences(
            self,
            "findings",
            "questions",
            "retrieval_manifest",
            "investigation_manifest",
        )
