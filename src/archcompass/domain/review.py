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
from typing import Literal

from pydantic import Field, model_validator

from archcompass.domain.atlas import FindingCandidate
from archcompass.domain.base import DomainModel, new_id, utc_now
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
    #: What to do about it. Empty when the verdict is that nothing needs doing, because
    #: an advisor that always has a next action has not really answered the question.
    recommended_response: str = ""


class ReviewStatus(StrEnum):
    SUCCEEDED = "succeeded"
    FAILED = "failed"


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
    #: Present only when material. A verdict that nothing needs doing has no next action,
    #: and an advisor that always produces one has not answered the question.
    recommended_response: str = ""

    @model_validator(mode="after")
    def response_only_when_material(self) -> ReviewedBoundary:
        if self.recommended_response and not self.material:
            raise ValueError("A boundary that is not material must not carry a response")
        return self

    @property
    def title(self) -> str:
        return self.candidate.summary


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


class ReviewOverview(DomainModel):
    """What the boundaries add up to, composed once from all of them.

    Deliberately has no verdict field. There is nowhere in this shape to record that a
    boundary is material, so an overview cannot contradict a verdict as data, and nothing
    downstream reads its prose as a key. It says what the review means; it cannot revise it.

    `themes` and `recommended_sequence` may both be empty. Two cleared boundaries have no
    pattern running across them and nothing to do about them, and saying so is a result.
    """

    #: What this repository is being asked to do — the ground the rest stands on.
    situation: str = Field(min_length=1)
    themes: list[OverviewStatement] = Field(default_factory=list[OverviewStatement])
    recommended_sequence: list[OverviewStatement] = Field(
        default_factory=list[OverviewStatement]
    )
    #: What this review could not see. Stated once here because it is a property of the
    #: method rather than of any one boundary, which prints its own limits too.
    limits: str = Field(min_length=1)


class BoundaryReviewReport(DomainModel):
    """Every boundary in one repository, judged against one case, and what that amounts to."""

    schema_version: Literal[2] = 2
    report_id: str = Field(default_factory=lambda: new_id("review"))
    case_title: str = Field(min_length=1)
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
        }
        unknown = sorted(cited - known)
        if unknown:
            raise ValueError(f"The overview cites boundaries this review lacks: {unknown}")
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
        verdict = (
            "none were judged material"
            if material == 0
            else f"{material} of them {'was' if material == 1 else 'were'} judged material"
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
        if self.status is ReviewStatus.FAILED and self.report is not None:
            raise ValueError("A failed review must not carry a report")
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
            "One detector ran: an abstraction with exactly one implementation. Finding "
            "nothing means that shape is absent, not that the repository is without "
            "structural problems."
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
            recommended_response=verdict.recommended_response if verdict.material else "",
        )
        for ordinal, (candidate, verdict) in enumerate(verdicts, start=1)
    ]
