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

from datetime import datetime
from enum import StrEnum
from typing import Final, Literal, cast

from pydantic import Field, computed_field, model_validator

from archcompass.domain.atlas import FindingCandidate, FindingPattern
from archcompass.domain.base import DomainModel, new_id, utc_now
from archcompass.domain.case import CaseField
from archcompass.domain.diagnostics import FailureDiagnostic


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
    #: The circumstance the case does not state.
    unknown: str = Field(min_length=1)
    #: Which way the cited verdicts move under each answer, so a reader can tell a question
    #: worth answering from one that changes nothing.
    why_it_matters: str = Field(min_length=1)
    #: Phrased so the user can answer it from what they know. A question they cannot settle
    #: is the model returning its own uncertainty to sender rather than asking for anything.
    question: str = Field(min_length=1)
    #: Which case field the answer belongs in, chosen from a closed set — the model picks a
    #: slot, never names one.
    answer_belongs_in: CaseField
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
    report: BoundaryReviewReport | None = None
    markdown_report: str | None = None
    duration_seconds: float = Field(default=0.0, ge=0)
    sanitized_errors: list[str] = Field(default_factory=list[str])
    failure_diagnostics: list[FailureDiagnostic] = Field(
        default_factory=list[FailureDiagnostic]
    )
    created_at: datetime = Field(default_factory=utc_now)

    @model_validator(mode="after")
    def succeeded_reviews_carry_a_report(self) -> BoundaryReview:
        if self.status is ReviewStatus.SUCCEEDED and self.report is None:
            raise ValueError("A succeeded review must carry its report")
        if self.status is not ReviewStatus.SUCCEEDED and self.report is not None:
            raise ValueError(f"A {self.status.value} review must not carry a report")
        return self


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


def reviewed_boundaries(
    verdicts: list[tuple[FindingCandidate, CandidateVerdict]],
) -> list[ReviewedBoundary]:
    """Number the judged candidates in detection order.

    References are assigned here, from position, because the application owns every
    identifier a reader will later cite (master plan 12.0). Detection is deterministic, so
    re-running the same atlas gives the same boundary the same reference.
    """

    return [
        ReviewedBoundary(
            reference=f"BR-{ordinal:03d}",
            candidate=candidate,
            material=verdict.material,
            rationale=verdict.rationale,
            policy_bearings=verdict.policy_bearings,
            hinge=verdict.hinge,
            recommended_response=verdict.recommended_response if verdict.material else "",
        )
        for ordinal, (candidate, verdict) in enumerate(verdicts, start=1)
    ]
