"""What a boundary review produces, and nothing else.

Deliberately not `RecommendationReport`. That aggregate is shaped for *recommend an
architecture*: it requires design forces, alternatives, scenario analysis, an ADR and an
implementation sequence, because the path that built it reasoned its way to a proposed
design. A review does not do that. It looks at boundaries that already exist and says,
one at a time, whether each is earning its place.

Filling those fields from a review would mean inventing alternatives nobody weighed and
scenarios nobody evaluated — the failure in master plan 3.1 reproduced inside the one
artifact a person actually reads. So the review has its own report, carrying what it
genuinely knows and declaring nothing it does not.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from enum import StrEnum
from typing import Annotated, Final, Literal, cast

from pydantic import Field, StringConstraints, computed_field, model_validator

from archcompass.domain.atlas import FindingCandidate, FindingPattern, SourceLocation
from archcompass.domain.base import DomainModel, new_id, utc_now
from archcompass.domain.case import ArchitectureCase, CaseField
from archcompass.domain.diagnostics import FailureDiagnostic
from archcompass.domain.fingerprint import boundary_fingerprint


class PolicyBearing(DomainModel):
    """A policy the model said bears on one candidate, resolved back to its identity.

    The model is asked only whether each presented policy bears and how; which policy it
    was answering about is fixed by position in the presented list, and the identity is
    attached here. A mistyped or recalled-from-memory policy ID therefore has no route
    into the record, because no policy ID is ever read back from a response (12.0).
    """

    policy_id: str = Field(min_length=1)
    policy_title: str = Field(min_length=1)
    how: str = Field(min_length=1)


class VerdictHinge(DomainModel):
    """The circumstance a verdict assumed because the case did not state it (6C.2).

    Not the same thing as a detection limit. A candidate already says what the *method*
    could not see — an implementation registered at runtime, a name that might be a
    coincidence. This says what the *case* did not say, which is the other half of what a
    verdict rests on and the only half a user can fix.

    Present only where the verdict actually moves. A hinge on every boundary would be a
    verdict hedging itself, and the whole value here is that the ones carrying a hinge are
    the ones worth asking about.
    """

    #: What the case does not state, phrased as the circumstance rather than as a question.
    #: The question is composed later, across boundaries, where duplicates can be merged.
    unknown: str = Field(min_length=1)
    #: The verdict this boundary gets if the unknown turns out to hold, and if it does not.
    #: Both are required: a hinge that cannot say which way it moves is not a hinge, it is
    #: an admission of unease, and a reader cannot act on it.
    if_confirmed: str = Field(min_length=1)
    if_denied: str = Field(min_length=1)


class CandidateVerdict(DomainModel):
    """Whether a detected pattern matters in this case, and why.

    `material=False` is the ordinary answer, not a failure to find something. A detector
    reports shapes and most shapes are earning their place, so a stage that cannot say
    "this is fine here" turns the advisor into an instrument for deleting abstractions —
    the mirror image of the failure in 3.1 and just as wrong.
    """

    candidate_id: str = Field(min_length=1)
    material: bool
    rationale: str = Field(min_length=1)
    policy_bearings: list[PolicyBearing] = Field(default_factory=list[PolicyBearing])
    #: What the verdict turned on that the case did not settle, where it turned on anything.
    #: `None` is the ordinary answer and means the verdict stands whichever way the unknown
    #: falls — translated from an explicit declaration by the adapter, never inferred from
    #: a model's silence.
    hinge: VerdictHinge | None = None
    #: What to do about it. Empty when the verdict is that nothing needs doing, because
    #: an advisor that always has a next action has not really answered the question.
    recommended_response: str = ""


class ReviewStatus(StrEnum):
    #: A review that is being produced right now. It exists so a run is visible while it
    #: happens rather than appearing only once it is over; it carries no report, and it is
    #: the one status a stored review ever moves out of.
    RUNNING = "running"
    #: Every boundary was judged and the run then asked for what would settle the verdicts
    #: it could not settle alone. Deliberately not a flavour of `succeeded`: a first pass
    #: against an unwritten case moved four of five verdicts once its questions were
    #: answered, so presenting those verdicts as findings would be presenting conclusions
    #: that are far more likely to be wrong than right (ADR 0010).
    #:
    #: This is the one terminal status that is waiting on a person rather than on the
    #: application, and it is terminal: nobody is obliged to answer, and a record that says
    #: "still waiting" for ever is the truthful account of a question nobody came back to.
    #: Answering does not move it — it produces a second review, pinned to the case revision
    #: the answers created.
    AWAITING_ANSWERS = "awaiting_answers"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    #: Stopped because someone asked it to stop. Kept apart from `failed`: a review nobody
    #: wanted any more is not a review that broke, and a listing that showed them the same
    #: way would have the reader looking for a problem that never existed.
    CANCELLED = "cancelled"


#: The verdict in the vocabulary of each shape, keyed by pattern and then by `material`.
#: Exhaustive over `FindingPattern` by construction — a pattern added without a phrase here
#: raises on the first verdict rather than quietly borrowing another shape's words.
_VERDICT_LABELS: Final[dict[FindingPattern, dict[bool, str]]] = {
    FindingPattern.SOLE_IMPLEMENTATION: {
        True: "Not earning its place",
        False: "Earning its place",
    },
    FindingPattern.DUPLICATED_KNOWLEDGE: {
        True: "Needs one owner",
        False: "Separate concerns",
    },
    FindingPattern.SCATTERED_CONCEPT: {
        True: "Has leaked past its boundary",
        False: "Named where it should be",
    },
}


class BoundaryExcerpt(DomainModel):
    """One participant's recorded span, and the code at it.

    Stored on the review, and that is a reversal worth stating. It was read live from the
    repository instead, on the grounds that the span was already pinned and the text could
    always be recovered from it. That holds only while the repository still says what it said,
    and measurement is what settled it: appending one comment to a file no finding cites took
    a six-boundary review from sixteen excerpts to none. The evidence expired the moment
    someone started acting on the findings, which is exactly when a review is read.

    Three things follow from storing it. A review is pinned to the exact inputs that produced
    it — case revision, atlas version, model and prompt identity — and the code was the one
    input that quietly expired; now it does not. A concluded review can still be discussed
    with its code in hand, rather than answering "the review does not include the specific
    lines" a week later because of an unrelated edit (ADR 0013). And it costs about 4,000
    characters against a 46,000-character stored review.

    What it is not is what the *judge* read. Judgement is structural, over the atlas: these
    are the lines a deterministic detector measured, recorded so a reader — and the stage
    answering that reader — can see what a verdict is about. The verdict still rests on
    structure; the code is here because someone will ask.
    """

    #: `BR-nnn`, so an excerpt can be attached to the finding it substantiates.
    reference: str = Field(pattern=r"^BR-[0-9]{3}$")
    qualified_name: str = Field(min_length=1)
    #: The candidate's own words for why this participant is implicated — "States
    #: BUILT_IN_VOICES at this location", "Declares the abstraction". Carried so an excerpt
    #: says what it is evidence *of* rather than only where it came from.
    role: str = Field(min_length=1)
    location: SourceLocation | None = None
    text: str = ""
    #: Why there is no text, in one sentence, when there is none. A boundary whose code
    #: cannot be shown is still a boundary: a proposed one has not been written, a stale
    #: repository no longer holds the lines that were judged, and saying which is more use
    #: than an empty panel.
    unavailable: str = ""

    @model_validator(mode="after")
    def an_excerpt_has_text_or_says_why_not(self) -> BoundaryExcerpt:
        if bool(self.text) == bool(self.unavailable):
            raise ValueError(
                "A boundary excerpt carries exactly one of its text or a reason it has none"
            )
        return self


class ReviewedBoundary(DomainModel):
    """One detected pattern and what the advisor concluded about it.

    Both outcomes are stored. A boundary the advisor examined and cleared is evidence that
    it looked, and a report containing only problems would read identically whether every
    boundary was cleared or none was inspected.
    """

    #: Short, readable, and assigned by the application in detection order. A person cites
    #: "BR-003" in a follow-up question; nothing in the model's reply is ever this value.
    reference: str = Field(pattern=r"^BR-[0-9]{3}$")
    candidate: FindingCandidate
    #: The structural identity of this boundary, which — unlike `reference` — is the same
    #: value on every run that sees the same structure. Stamped by the application from the
    #: candidate, so a stored review can be matched against a baseline or a standing
    #: decision without re-deriving anything from its prose.
    #:
    #: Optional with a default because a stored review is validated against the current
    #: schema and nothing shims it (ADR 0002): a review written before fingerprints existed
    #: has to remain readable, and it carries `None` rather than a value invented for it.
    fingerprint: str | None = None
    #: The review that first reached this verdict, when it was reused rather than reached
    #: again. `None` is the ordinary case and means the model was asked about this boundary
    #: during this run. Named here rather than only counted, because "the same conclusion as
    #: last time" and "the same conclusion, reached again" are different claims and only one
    #: of them is evidence that anything was looked at twice.
    verdict_reused_from: str | None = None
    material: bool
    rationale: str = Field(min_length=1)
    policy_bearings: list[PolicyBearing] = Field(default_factory=list[PolicyBearing])
    #: What this verdict assumed because the case was silent, where it assumed anything.
    #: Carried on the boundary rather than only in the overview's questions, because a
    #: reader deciding whether to act on this one verdict needs to know what it rested on
    #: at the point of deciding — the same reason detection limits print here.
    hinge: VerdictHinge | None = None
    #: Present only when material. A verdict that nothing needs doing has no next action,
    #: and an advisor that always produces one has not answered the question.
    recommended_response: str = ""

    @model_validator(mode="before")
    @classmethod
    def recompute_the_verdict_label(cls, data: object) -> object:
        """Drop a stored `verdict_label` so it is always derived, never read back.

        The field is computed and therefore serialised, and a stored review read back would
        otherwise fail `extra="forbid"` on its own output. Discarding it rather than
        accepting it is the deliberate half: the label is a function of the pattern and the
        verdict, so a stored copy can only ever agree or be wrong, and there is no version
        of this where the copy should win. Not an upgrade shim — nothing here tolerates a
        superseded schema (ADR-0002); it declines to trust a value the model itself owns.
        """

        if not isinstance(data, dict):
            return data
        fields = cast("dict[str, object]", data)
        return {key: value for key, value in fields.items() if key != "verdict_label"}

    @model_validator(mode="after")
    def response_only_when_material(self) -> ReviewedBoundary:
        if self.recommended_response and not self.material:
            raise ValueError("A boundary that is not material must not carry a response")
        return self

    @property
    def title(self) -> str:
        return self.candidate.summary

    @computed_field
    @property
    def verdict_label(self) -> str:
        """What this verdict means, in the vocabulary of the shape it is about.

        One named home for the wording, computed rather than stored and never written by a
        model. The catalogue has two opposite directions and a single phrase cannot serve
        both: "not earning its place" is exactly right for indirection that hides nothing
        and nonsense for a constant copied into four modules, where the finding is that
        something is missing rather than surplus.

        Serialised, so the page and the Markdown report read the same words without each
        keeping its own copy of the vocabulary.
        """

        return _VERDICT_LABELS[self.candidate.pattern][self.material]


class OverviewStatement(DomainModel):
    """One claim about the review as a whole, and the boundaries it rests on.

    A claim resting on no boundary is never recorded. The overview exists to say what the
    verdicts amount to, so a sentence none of them support is the model describing a
    repository it was not shown (12.0).
    """

    text: str = Field(min_length=1)
    #: `BR-nnn`, attached by the application from positional flags rather than read back
    #: out of the reply. Nothing here was ever written by a model.
    supporting_references: list[str] = Field(min_length=1)


class OpenQuestion(DomainModel):
    """One thing the case does not say that would settle verdicts, and where it belongs.

    Composed across the whole set rather than per boundary, because that is the only place
    duplicates can be merged: four boundaries turning on whether a second vendor is coming
    are one question citing four boundaries, and asking it four times is noise (6C.2).

    This is advisor output and lives in the review, immutable and pinned like every other
    conclusion. It is never written into the case. An answer enters the case only as a
    revision the user authored and saw (6C.4, invariant 25).
    """

    #: `Q-n`, assigned by the application in presentation order after validation. Nothing
    #: in a model's reply is ever this value.
    reference: str = Field(pattern=r"^Q-[0-9]+$")
    #: What the review actually saw that raised this — which abstractions, what the code
    #: does today, and what the case says about it now. The question and the unknown are
    #: both one line, and one line is not enough to decide an answer from: a reader is being
    #: asked about their own project by something that has read code they may not have, and
    #: what it read is the part they cannot supply for themselves.
    what_the_review_saw: str = Field(min_length=1)
    #: The circumstance the case does not state, in one line and phrased to stand as the
    #: subject of a sentence. It is not a restatement of the question; it is what the question
    #: is about, which is why it can title a discussion of that question and why a reader
    #: recognises the same subject coming back across two passes.
    #:
    #: It used to be half of the recorded case entry: the workspace joined it to the user's
    #: answer so that the answer still meant something read on its own. The case holds the
    #: question-and-answer pair now (§6C.4), so the subject arrives with the question rather than
    #: being welded onto the reply, and nothing composes anything.
    unknown: str = Field(min_length=1)
    #: Which way the cited verdicts move under each answer, so a reader can tell a question
    #: worth answering from one that changes nothing.
    why_it_matters: str = Field(min_length=1)
    #: Phrased so the user can answer it from what they know. A question they cannot settle
    #: is the model returning its own uncertainty to sender rather than asking for anything.
    question: str = Field(min_length=1)
    #: Plausible answers, each stated as the reader would state it — "A second vendor is
    #: planned this year", "No second vendor is coming".
    #:
    #: An option set is an offer, never a constraint. The answer path takes free text and
    #: never checks what it is given against this list; a chosen option arrives as its own
    #: text, indistinguishable from one that was typed. Nothing keys off an option either,
    #: because every one of them is model-written (12.0).
    #:
    #: Empty is the correct shape for a genuinely open-ended question and stays the common
    #: one: a question asking the reader to describe how something is used has no enumerable
    #: answers, and four guesses at them would narrow the reply to what was guessed.
    #:
    #: Capped at four. A longer list is a reader studying a menu instead of answering, and
    #: the box beside it is faster than the fifth option.
    answer_options: list[Annotated[str, StringConstraints(min_length=1)]] = Field(
        default_factory=list[str], max_length=4
    )
    #: Which case field the answer belongs in, chosen from a closed set — the model picks a
    #: slot, never names one.
    answer_belongs_in: CaseField

    @model_validator(mode="after")
    def offered_options_are_distinct_and_say_something(self) -> OpenQuestion:
        """Two options a reader cannot tell apart are one offer, presented as a choice.

        Compared with whitespace collapsed, because the difference between "no second vendor"
        and "no  second vendor" is nothing a reader can see and a duplicate they can see is
        the whole defect. Nothing further is normalized here: casing and punctuation are how
        these read as sentences, and folding them would call two real alternatives one.
        """

        collapsed = [" ".join(option.split()) for option in self.answer_options]
        if any(not option for option in collapsed):
            raise ValueError("An answer option must state an answer")
        if len(collapsed) != len(set(collapsed)):
            raise ValueError("Answer options must be mutually distinct")
        return self
    #: `BR-nnn`, attached by the application from positional flags. A question resting on no
    #: boundary is discarded rather than recorded, exactly as an ungrounded theme is.
    supporting_references: list[str] = Field(min_length=1)


class ReviewOverview(DomainModel):
    """What the boundaries add up to, composed once from all of them.

    Deliberately has no verdict field. There is nowhere in this shape to record that a
    boundary is material, so an overview cannot contradict a verdict as data, and nothing
    downstream reads its prose as a key. It says what the review means; it cannot revise it.

    `themes` and `recommended_sequence` may both be empty. Two cleared boundaries have no
    pattern running across them and nothing to do about them, and saying so is a result.
    """

    #: The bottom line: what this repository is being asked to do, what the verdicts found
    #: wrong with how it is built for that, and what to do about it. A reader who gets no
    #: further than this sentence should still know where they stand.
    situation: str = Field(min_length=1)
    themes: list[OverviewStatement] = Field(default_factory=list[OverviewStatement])
    recommended_sequence: list[OverviewStatement] = Field(
        default_factory=list[OverviewStatement]
    )
    #: What this review could not see. Stated once here because it is a property of the
    #: method rather than of any one boundary, which prints its own limits too.
    limits: str = Field(min_length=1)
    #: What the case would have to say for the contingent verdicts to settle (6C). Empty is
    #: the good outcome, not a gap: it means no verdict turned on anything the case left
    #: open. There is no cap — the bound is structural, since every question traces to a
    #: hinge and hinges exist only where a verdict admitted contingency (6C.5).
    open_questions: list[OpenQuestion] = Field(default_factory=list[OpenQuestion])


class BoundaryReviewReport(DomainModel):
    """Every boundary in one repository, judged against one case, and what that amounts to."""

    # 3 adds the overview's open questions (6C). No shim, under ADR 0002: a stored version-2
    # review no longer parses, is reported through `UnreadableStoredRecordError`, and is
    # re-run. A report that may or may not carry questions would multiply states on every
    # read path from here on, which is the cost the version number exists to refuse.
    schema_version: Literal[3] = 3
    report_id: str = Field(default_factory=lambda: new_id("review"))
    case_title: str = Field(min_length=1)
    #: What the case said it was for, where it said anything. A review can run against a
    #: repository and an unwritten case, and this is then the sentence saying so rather than
    #: a blank a reader has to interpret.
    problem_and_desired_outcome: str = Field(min_length=1)
    #: Every boundary examined, material or not. Empty is valid and meaningful: the
    #: detector ran and found no candidate, which is a result rather than a failure.
    reviewed: list[ReviewedBoundary] = Field(default_factory=list[ReviewedBoundary])
    overview: ReviewOverview
    #: Which policies the advisor was shown, so a reader can tell a policy that did not
    #: apply from one that was never presented.
    policies_presented: list[str] = Field(default_factory=list[str])
    #: The code at every participant's recorded span, read once when the review completed and
    #: pinned here with everything else the run depended on.
    #:
    #: Optional with a default, which is the whole reason it can be added at all. ADR 0002
    #: refuses a shim for a *narrowed* schema — a review that no longer parses is re-run —
    #: and this widens: a review stored before this field existed reads back with none, and
    #: falls through to a live read exactly as it did. `elicited_from` was added the same
    #: way and for the same reason.
    #:
    #: Empty therefore means two different things, and neither needs distinguishing here: a
    #: review stored before this existed, or one whose repository could not be read when it
    #: finished. Both are answered the same way — by trying the repository now.
    excerpts: list[BoundaryExcerpt] = Field(default_factory=list[BoundaryExcerpt])

    @model_validator(mode="after")
    def require_unique_references(self) -> BoundaryReviewReport:
        references = [item.reference for item in self.reviewed]
        if len(references) != len(set(references)):
            raise ValueError("Reviewed boundary references must be unique")
        return self

    @model_validator(mode="after")
    def overview_cites_only_boundaries_of_this_review(self) -> BoundaryReviewReport:
        """The last line of defence for grounding, independent of any adapter.

        Positions are mapped to references before this model is built, so a citation that
        does not resolve means the mapping was wrong — and a report that cites a boundary
        it does not contain is worse than one that says less.
        """

        known = {item.reference for item in self.reviewed}
        cited = {
            reference
            for statement in (*self.overview.themes, *self.overview.recommended_sequence)
            for reference in statement.supporting_references
        } | {
            reference
            for question in self.overview.open_questions
            for reference in question.supporting_references
        }
        unknown = sorted(cited - known)
        if unknown:
            raise ValueError(f"The overview cites boundaries this review lacks: {unknown}")
        return self

    @model_validator(mode="after")
    def require_unique_question_references(self) -> BoundaryReviewReport:
        references = [item.reference for item in self.overview.open_questions]
        if len(references) != len(set(references)):
            raise ValueError("Open question references must be unique")
        return self

    @property
    def material(self) -> list[ReviewedBoundary]:
        return [item for item in self.reviewed if item.material]

    @property
    def cleared(self) -> list[ReviewedBoundary]:
        return [item for item in self.reviewed if not item.material]

    @property
    def headline(self) -> str:
        """A factual sentence of counts, composed rather than written.

        No model call: every number here is already known, and asking for prose about
        counts would be spending judgement on bookkeeping (master plan 12.0). The model's
        contribution is `overview`, which says what the counts mean.
        """

        if not self.reviewed:
            return (
                "No boundary of a detectable shape was found in this repository, so there "
                "was nothing for this review to judge."
            )
        material = len(self.material)
        subject = "boundary" if len(self.reviewed) == 1 else "boundaries"
        # Spelled out, never the word "material". Read as ordinary English that term says a
        # boundary matters, which is the opposite of the verdict it names.
        verdict = (
            "every one was found to be earning its place"
            if material == 0
            else (
                f"{material} of them was found not to be earning its place"
                if material == 1
                else f"{material} of them were found not to be earning their place"
            )
        )
        return (
            f"{len(self.reviewed)} {subject} reviewed against "
            f"{len(self.policies_presented)} policies; {verdict}."
        )


class BoundaryReview(DomainModel):
    """One immutable review, pinned to the exact inputs that produced it."""

    schema_version: Literal[1] = 1
    review_id: str = Field(default_factory=lambda: new_id("rev"))
    status: ReviewStatus
    case_id: str = Field(min_length=1)
    case_revision: int = Field(ge=1)
    atlas_version_id: str = Field(min_length=1)
    reasoning_model: str = Field(min_length=1)
    prompt_identity: str = Field(min_length=1)
    #: The review whose questions produced the case revision this one judges against, where
    #: this review is the second pass of an elicitation. `None` is a first pass, which is
    #: every review that was not reached by answering.
    #:
    #: A stored link rather than an inference. "Has this review been carried on from?" was
    #: previously read off the listing — any newer review of the same case counted — and
    #: that is wrong in a way a user meets: revising the case by hand also produces a newer
    #: review, which would silently mark the questions answered. It is also what lets the
    #: second pass show what the answers actually changed.
    #:
    #: An optional field with a default, so every stored document still parses; ADR 0002
    #: refuses shims for a *narrowed* schema, and this widens.
    elicited_from: str | None = None
    #: The durable repository and branch this run was about, copied from the atlas it judged.
    #: The atlas version already pins *which checkout at which commit*; this says which line
    #: of work that commit belongs to, which is the level baselines and standing decisions
    #: will attach to.
    #:
    #: Optional with a default for the same reason `elicited_from` is: a stored document is
    #: validated against the current schema and nothing shims it, so every field added after
    #: the fact has to be one an older document can be missing. Absent on a review of an atlas
    #: indexed before lineages existed; re-indexing and re-running fills it.
    repo_id: str | None = None
    branch_id: str | None = None
    report: BoundaryReviewReport | None = None
    markdown_report: str | None = None
    duration_seconds: float = Field(default=0.0, ge=0)
    sanitized_errors: list[str] = Field(default_factory=list[str])
    failure_diagnostics: list[FailureDiagnostic] = Field(
        default_factory=list[FailureDiagnostic]
    )
    created_at: datetime = Field(default_factory=utc_now)

    @model_validator(mode="after")
    def reviews_that_reached_verdicts_carry_a_report(self) -> BoundaryReview:
        """A report belongs to exactly the two statuses that got as far as judging.

        A review waiting on answers has judged every boundary — the questions it asks are
        the residue of those verdicts and cite them by reference, so there is nowhere else
        for them to live. What it does not have is a conclusion, and its report says so by
        carrying an overview the application composed rather than one a model wrote.

        The other three statuses reached no verdict at all, and a report on any of them
        would be a claim about a repository nothing examined.
        """

        reached_verdicts = {ReviewStatus.SUCCEEDED, ReviewStatus.AWAITING_ANSWERS}
        if self.status in reached_verdicts and self.report is None:
            raise ValueError(f"A {self.status.value} review must carry its report")
        if self.status not in reached_verdicts and self.report is not None:
            raise ValueError(f"A {self.status.value} review must not carry a report")
        return self

    @model_validator(mode="after")
    def only_a_second_pass_names_the_review_it_came_from(self) -> BoundaryReview:
        """A first pass has nothing to point at, and a self-link would be a cycle."""

        if self.elicited_from is not None and self.elicited_from == self.review_id:
            raise ValueError("A review cannot have been elicited from itself")
        return self

    @property
    def awaiting_answers(self) -> bool:
        return self.status is ReviewStatus.AWAITING_ANSWERS


def empty_review_overview() -> ReviewOverview:
    """The overview of a review with nothing in it, composed rather than asked for.

    A sweep that found no candidate has no verdicts to synthesise, so there is nothing for
    judgement to do and a model call would be inventing content from an empty input.
    """

    return ReviewOverview(
        situation=(
            "The detector swept this repository and found no boundary of a shape it can "
            "recognise, so there was nothing to judge against this case."
        ),
        limits=(
            "Three detectors ran: an abstraction with exactly one implementation, a "
            "constant stated in several modules with no owner, and a concept named beyond "
            "the package that owns it. Finding nothing means those shapes are absent, not "
            "that the repository is without structural problems."
        ),
    )


def first_pass_overview(
    boundaries: list[ReviewedBoundary],
    questions: list[OpenQuestion],
) -> ReviewOverview:
    """The overview of a pass that asked instead of concluding, composed rather than asked for.

    A first pass runs `elicit_questions`, not `summarise_review`, so it has no model-written
    conclusion — and that is deliberate rather than a gap. A summary composed against a case
    that says nothing would be a conclusion drawn from silence, and the second pass discards
    it anyway; spending a model call on a document nobody reads is the definition of
    bookkeeping dressed as judgement (master plan 12.0).

    So `situation` and `limits` are written here, from facts already known, and they say what
    this pass actually is: verdicts reached, and the questions that would settle the ones that
    could not settle themselves. `themes` and `recommended_sequence` stay empty because a first
    pass has nothing to say about the set — saying it is the second pass's job.
    """

    hinged = sum(1 for item in boundaries if item.hinge is not None)
    subject = "boundary" if len(boundaries) == 1 else "boundaries"
    rested = (
        "Every one of them stood on what it already knew"
        if hinged == 0
        else (
            "One of them rested on something it was not told"
            if hinged == 1
            else f"{hinged} of them rested on something it was not told"
        )
    )
    asking = (
        "one question" if len(questions) == 1 else f"{len(questions)} questions"
    )
    # Relayed from the candidates rather than restated. The detector is what knows what it
    # could not see, and prose written here would be this function's opinion of a method it
    # does not implement.
    stated: list[str] = []
    for item in boundaries:
        if item.candidate.limitations and item.candidate.limitations not in stated:
            stated.append(item.candidate.limitations)
    return ReviewOverview(
        situation=(
            f"{len(boundaries)} {subject} were judged against what this case says so far. "
            f"{rested}, so before these verdicts are worth reading as findings, this pass is "
            f"asking {asking}. Answering carries the review on: the same boundaries are "
            "judged again against your answers, and that second pass is the one that "
            "concludes."
        ),
        limits=(
            " ".join(stated)
            or "The detector stated no limitation on what it could see."
        ),
        open_questions=questions,
    )


class AnsweredQuestion(DomainModel):
    """One question a first pass asked, beside what the reader wrote back.

    Both halves already existed and neither could be reached from the other. The question is
    advisor output pinned in the first-pass review for ever; the answer is user-authored and
    lives on the case revision that answering produced. Nothing joined them, so a reader who
    asked a concluded review "what were the questions and answers again?" was told the review
    holds no such record — true of the review it was looking at, and false of the pair.
    """

    question: OpenQuestion
    #: What the reader wrote, or empty where they skipped it or where this revision was
    #: authored by hand. Which of those it was is `ReviewEvidence.answers_were_recorded`,
    #: because it is a property of the round rather than of any one question.
    answer: str = ""


class ReviewEvidence(DomainModel):
    """Everything about a review that a reasoning stage is shown, assembled in one place.

    A bundle rather than four parameters, and the reason is a defect that landed three times.
    The stages' inputs were assembled at the call site, argument by argument, and each time
    something the record already held was simply not passed: the code at every recorded span,
    then the spans of a scattered concept, then the questions and answers of the elicitation
    round. Every time the model correctly reported an absence, and every time the absence was
    ours. `answer_review_question` has said "the review does not contain..." about three
    different things it does contain.

    What a value fixes that a fourth parameter would not is that "what does this stage see?"
    becomes one answer instead of a reading of every call site. An omission is then visible
    in one place, and testable there.

    Evidence only. `MethodKnowledge` stays a separate argument because it is a different kind
    of thing — it explains the review's vocabulary and says nothing about this repository, so
    nothing here binds to it and an answer never cites it (§12.1). Folding the two together
    would make that distinction a matter of which field a reader looked at.

    Assembled by the application, never by a model, and never trimmed to a question: what
    reaches a stage is decided by which stage it is, not by what was asked (§12.0).
    """

    #: The revision the review pinned, whole — not the workspace's current case. Half of what
    #: every verdict was reached from.
    case: ArchitectureCase
    #: The code at each participant's recorded span, read from the repository the review
    #: pinned. Some may carry a reason instead of text.
    excerpts: list[BoundaryExcerpt] = Field(default_factory=list[BoundaryExcerpt])
    #: The round that produced this review's case revision, where there was one. Empty on a
    #: first pass, which has asked nothing yet.
    elicitation: list[AnsweredQuestion] = Field(default_factory=list[AnsweredQuestion])
    #: Whether the revision recorded which line answered which question. False for one
    #: authored by hand, where the questions were still asked and no answer is attributable
    #: to any of them — a distinction worth keeping, because "you skipped this" and "nobody
    #: wrote down what you said" are different things to tell a reader.
    answers_were_recorded: bool = False


def reviewed_boundaries(
    verdicts: list[tuple[FindingCandidate, CandidateVerdict]],
    *,
    reused_from: Mapping[str, str] | None = None,
) -> list[ReviewedBoundary]:
    """Number the judged candidates in detection order, and stamp what outlives the run.

    References are assigned here, from position, because the application owns every
    identifier a reader will later cite (master plan 12.0). Detection is deterministic, so
    re-running the same atlas gives the same boundary the same reference. The fingerprint
    is stamped in the same place and for the opposite reason: the reference is what a
    reader cites *within* one review, and the fingerprint is what anything outside one
    matches on.

    `reused_from` names, by `candidate_id`, the review a verdict was carried forward from,
    for the candidates whose verdicts were not reached again. Keyed rather than positional
    so that adding it cannot silently re-attribute a boundary the way a mismatched parallel
    list would.
    """

    carried = reused_from or {}
    return [
        ReviewedBoundary(
            reference=f"BR-{ordinal:03d}",
            candidate=candidate,
            fingerprint=boundary_fingerprint(candidate),
            verdict_reused_from=carried.get(candidate.candidate_id),
            material=verdict.material,
            rationale=verdict.rationale,
            policy_bearings=verdict.policy_bearings,
            hinge=verdict.hinge,
            recommended_response=verdict.recommended_response if verdict.material else "",
        )
        for ordinal, (candidate, verdict) in enumerate(verdicts, start=1)
    ]
