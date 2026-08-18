from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from hashlib import sha256

from archcompass.domain._support import freeze_pairs, freeze_sequences
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
    retrieval_manifest: tuple[RetrievalProvenance, ...] = ()
    model_identity: str = ""
    prompt_identity: str = ""
    failure: str | None = None

    def __post_init__(self) -> None:
        freeze_sequences(self, "findings", "questions", "retrieval_manifest")
