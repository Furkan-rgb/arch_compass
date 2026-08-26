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

    def __post_init__(self) -> None:
        freeze_sequences(self, "causes")


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


class Termination(StrEnum):
    """Why one investigation's execution stopped. Not whether it found anything.

    A state per way the loop can actually end, and no more: an enum with a case nothing
    reaches is a case nobody maintains, and one that names a limit the code does not enforce
    reads as a promise.

    `NATURAL_END` is deliberately not called `completed`: it says the model stopped asking,
    which is a fact about the loop, and carries no claim that the search was sufficient,
    exhaustive, or that the hinge is settled. Whether the
    observations are enough is the judge's to decide, and this enum must never become the
    place that quietly answers it.
    """

    #: The model stopped calling tools of its own accord.
    NATURAL_END = "natural_end"
    #: The per-run model-call ceiling was reached.
    MODEL_CALL_LIMIT = "model_call_limit"
    #: The exploration budget was spent.
    LOOKUP_LIMIT = "lookup_limit"
    #: Everything looked up so far came to more than one investigation may carry.
    INVESTIGATION_SIZE_LIMIT = "investigation_size_limit"
    #: The provider stopped answering, after the retries it is given.
    PROVIDER_ERROR = "provider_error"
    #: The whole execution ran past the time one judgement may take.
    WALL_CLOCK_LIMIT = "wall_clock_limit"
    #: The same question was asked of the same tool a third time. The reviewed repository
    #: does not change while it is being judged and every tool is read-only, so a third
    #: identical answer cannot differ from the first two — this is a stuck loop, not a
    #: search, and it is the shape a spent budget hides.
    REPEATED_TOOL_CALL = "repeated_tool_call"
    #: The model answered in a shape the contract cannot use, twice — the second time having
    #: been shown the rule it broke. Not a fact about the repository and not a spent budget:
    #: the gathering is ended so the reserved final call can ask for the judgement plainly,
    #: because a schema the model cannot satisfy inside a tool loop is sometimes one it can
    #: satisfy without one.
    MALFORMED_JUDGEMENT = "malformed_judgement"


@dataclass(frozen=True, slots=True)
class RecordedInvestigation:
    """What a review checked before it asked a person, kept with the review.

    This is what makes a hinge legible. A reader shown "is this seam deliberate?" cannot
    otherwise tell a question asked because the repository is silent from one asked
    because nothing looked — and that difference is the whole of whether the question is
    worth answering.

    No lookups beside a `withheld` sentence is a real state: nothing could look, and the
    reader is told why. No lookups beside a `termination` is the other one: the looking began
    and stopped before it asked anything, so the hinge stands unchecked. Empty on every count
    is never stored.
    """

    candidate_id: CandidateId
    lookups: tuple[InvestigationLookup, ...] = ()
    #: The model's own account of which findings mattered. The one thing the lookups
    #: cannot hold, which is why it sits beside them rather than among them.
    closing: str = ""
    #: Why no lookup was possible at all — no atlas to ask, a model that cannot call
    #: tools. The other axis from `termination`, which says how a looking that *began*
    #: ended; `__post_init__` refuses a record claiming both.
    withheld: str = ""
    #: Why execution stopped. `None` means only that it was not recorded, which is true of
    #: every investigation stored before this field existed — never that the looking ended
    #: naturally, and never that it did not start. Anything that actually runs sets it, even
    #: a run whose every lookup was refused; `withheld` is how "it never started" is said.
    termination: Termination | None = None
    #: The content fingerprint of the repository these answers came from. A hinge settled
    #: by a lookup rests on code the candidate's own spans do not cover, so the record has
    #: to say which snapshot answered — without it nothing can tell a settled hinge from a
    #: stale one.
    atlas_fingerprint: str = ""
    prompt_identity: str = ""
    model_identity: str = ""

    def __post_init__(self) -> None:
        freeze_sequences(self, "lookups")
        # The two are opposite accounts of the same investigation — one says the looking
        # never began, the other says how it ended — so a record carrying both describes
        # something that cannot have happened. One line here rather than a lifecycle type.
        if self.withheld and self.termination is not None:
            raise ValueError(
                "a withheld investigation never ran, so nothing can have terminated it"
            )

    @property
    def identity(self) -> str:
        material = (
            str(self.candidate_id),
            self.atlas_fingerprint,
            self.prompt_identity,
            self.model_identity,
            # Was "resolved"/"held" — a verdict this record no longer reaches. What is
            # hashed now is why the looking stopped, which is a fact about this run.
            self.termination or "unrecorded",
            *(
                f"{item.tool}("
                + ";".join(f"{key}={value}" for key, value in item.arguments)
                + f")\0{item.result}"
                for item in self.lookups
            ),
            self.closing,
            self.withheld,
        )
        return sha256("\0".join(material).encode()).hexdigest()


@dataclass(frozen=True, slots=True)
class Review:
    id: str
    #: Which revision of the branch this is. One review takes one number and keeps it, from
    #: the first snapshot it records to the last — asking a question and being answered is
    #: something that happens inside a revision, not something that starts the next one.
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
    #: Which clarification round of this revision the snapshot was taken in. A review that
    #: settled without asking is round 1; a review that asked, was answered and asked again
    #: records round 1, round 2 and a final snapshot under one `sequence`. It is here so
    #: that two snapshots of one revision can be told apart — by a reader, and by the
    #: identity a snapshot is filed under — without the revision number having to move.
    round: int = 1
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
        if self.round < 1:
            raise ValueError("review round must be positive")
