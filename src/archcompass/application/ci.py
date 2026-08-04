"""One review, run where nobody is watching, reduced to a number a check can act on.

The workspace run and this one judge the same boundaries with the same service. What is
different is that nothing here can be asked a question and nothing here can be scrolled: a
pipeline gets one document and one exit code, and both have to be defensible without a human
reading the prose behind them (docs/plans/company-readiness.md §5).

Three rules carry the whole design, and each of them is a refusal:

*A run never waits.* A first pass may come back holding, with the verdicts it could not
settle resting on questions the case does not answer. CI cannot answer them, so the held
boundaries are reported as holding, their questions travel with them, and they are never
blocking. The clarifications already on the case are what carries an answered question
forward — nothing here re-asks, and nothing here answers on anybody's behalf.

*A branch is measured against the branch it came from.* A pull request opens a fresh lineage
with an empty baseline, so measuring it against itself would call every boundary in the
repository new on every pull request — the wall of noise the baseline exists to prevent. The
comparison is against an explicitly named base branch, and its standing decisions are read
the same way, because a boundary waived on `main` was waived for the pull request too.

*Only new adverse boundaries fail the check.* Everything else is information. A team must be
able to switch this on before it has agreed with anything the tool says, which is what
`FailOn.NOTHING` is for, and ratchet it to blocking once it has.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from enum import StrEnum
from pathlib import Path
from typing import Literal

from pydantic import Field

from archcompass.application.baseline import BaselineService
from archcompass.application.repository_index import RepositoryIndexService
from archcompass.application.reviews import ReviewService
from archcompass.application.triage import TriageService
from archcompass.domain.base import DomainModel
from archcompass.domain.baseline import BaselineEntry, BoundaryDisposition, disposition_of
from archcompass.domain.errors import ReviewHasNoReportError
from archcompass.domain.lineage import DEFAULT_BRANCH_NAME, derive_branch_id
from archcompass.domain.review import (
    BoundaryReviewReport,
    OpenQuestion,
    ReviewedBoundary,
    ReviewStatus,
)
from archcompass.domain.triage import DecisionState, StandingDecision
from archcompass.ports.repositories import LineageRepository

#: The two dispositions that make a boundary its own team's problem. Anything else has been
#: seen before under this exact structure, and re-raising it is what makes a check ignorable.
_SILENCING = frozenset({DecisionState.ACCEPTED, DecisionState.WAIVED})

#: Exit codes, named once. `2` is the CLI's existing convention for an operational failure and
#: is never produced here — a document that got far enough to exist reports 0 or 1, and 2 is
#: raised by the error path above this module.
EXIT_CLEAN = 0
EXIT_BLOCKING = 1


class FailOn(StrEnum):
    """What this run is allowed to fail for.

    Two members rather than a matrix of severities. The only distinction a team actually
    makes on adoption day is "tell me" versus "stop me", and a third setting would invite the
    check to be tuned instead of the code being fixed.
    """

    #: New, material, undecided and settled: a boundary nobody has seen, the advisor thinks
    #: is costing more than it earns, and no answer is outstanding on.
    NEW_MATERIAL = "new-material"
    #: Report everything, fail for nothing. Adoption mode, and the honest way to start.
    NOTHING = "nothing"


class CiDecision(DomainModel):
    """The team's standing disposition toward one boundary, as the check found it.

    Copied onto the entry rather than referenced, because the consumer of this document is a
    pipeline with no second call to make. Whether the decision was taken against the verdict
    this run reached is stated too: a waiver names a structural state and a verdict that has
    moved since is a waiver a reader should look at again.
    """

    decision_id: str
    state: DecisionState
    author: str
    reason: str | None = None
    #: The branch the decision is held on, which is the base branch rather than this run's.
    branch_id: str
    #: Whether the decision was taken against a verdict saying what this run's verdict says.
    taken_on_this_verdict: bool


class CiQuestion(DomainModel):
    """One thing the case does not say, travelling with the boundary it holds up.

    Repeated per boundary rather than listed once, and deliberately: a question that settles
    four verdicts appears against all four, because a reader of a pull request comment is
    looking at a boundary and asking why it has no answer, not reading a report from the top.
    """

    reference: str
    question: str
    unknown: str
    answer_belongs_in: str


class CiBoundary(DomainModel):
    """One reviewed boundary, and everything the check decided about it.

    The verdict fields are the review's own words, unedited. Nothing in this module summarises
    a rationale or restates a verdict label — a check that paraphrased what the advisor said
    would be a second, unaccountable author of the finding.
    """

    reference: str
    #: Absent only on a review stored before fingerprints existed, which a CI run cannot
    #: produce. Carried as optional because the boundary it is copied from carries it that way.
    fingerprint: str | None = None
    disposition: BoundaryDisposition
    material: bool
    verdict_label: str
    rationale: str
    #: The verdict turns on a question the case does not answer. Held verdicts are reported
    #: and never blocking: failing a pull request over something nobody was asked about is how
    #: a check gets switched off.
    holding: bool = False
    #: The questions whose answers would settle this verdict. Empty unless holding.
    questions: list[CiQuestion] = Field(default_factory=list[CiQuestion])
    decision: CiDecision | None = None
    #: The review this verdict was first reached in, when it was reused rather than reached
    #: again. `None` means the model was asked about this boundary during this run.
    verdict_reused_from: str | None = None
    #: Whether this boundary alone would fail the check, before `fail_on` is applied.
    blocking: bool = False


class CiCounts(DomainModel):
    """How this run's boundaries divide. `new + changed + known` is every boundary reviewed."""

    new: int = 0
    changed: int = 0
    known: int = 0
    #: Boundaries whose verdict is held on an open question. Counted across the other three
    #: rather than beside them: a held boundary is still new or known, and holding is a fact
    #: about the verdict rather than a fourth place to stand.
    holding: int = 0
    #: How many verdicts were reused from an earlier run, and how many there were in total.
    #: The pair rather than a ratio, so a reader can see "3 of 47" and not a percentage.
    verdicts_reused: int = 0
    verdicts_total: int = 0


class CiRun(DomainModel):
    """What one headless run found, in the form a pipeline consumes it.

    Stable by intent: this document is what an Action parses and what a team writes assertions
    against, so fields are added and not re-meant. It is computed, never stored — the review
    behind it is the record, and where its boundaries stand against a baseline is a fact about
    now that changes the moment somebody baselines or waives something.
    """

    schema_version: Literal[1] = 1
    case_id: str
    case_title: str
    review_id: str
    status: ReviewStatus
    repo_id: str | None = None
    #: The lineage this run wrote to: the branch under review.
    branch_id: str | None = None
    branch_name: str | None = None
    #: The lineage this run read from: the branch whose baseline and decisions it measured
    #: against. `branch_id` when a run is on its own base branch, which is the ordinary shape
    #: of a scheduled run on `main`.
    base_branch_name: str
    base_branch_id: str | None = None
    atlas_version_id: str
    reasoning_model: str
    #: How many entries the base branch's baseline held when this run read it. Zero on a
    #: repository nobody has adopted yet, which is why a first run reports everything as new.
    baseline_size: int = 0
    counts: CiCounts
    boundaries: list[CiBoundary] = Field(default_factory=list[CiBoundary])
    #: The references of every blocking boundary, in report order. Empty is the clean run.
    blocking: list[str] = Field(default_factory=list[str])
    fail_on: FailOn
    exit_code: int

    @property
    def surfaced(self) -> list[CiBoundary]:
        """New and changed boundaries, in report order: what this run is actually about.

        Known boundaries are counted and not listed. They are neither hidden nor repeated —
        the count is a claim a reader can go and audit in the workspace — and a check that
        re-presented forty of them on every push would be read exactly once.
        """

        return [
            item
            for item in self.boundaries
            if item.disposition is not BoundaryDisposition.KNOWN
        ]

    @property
    def held(self) -> list[CiBoundary]:
        return [item for item in self.boundaries if item.holding]


class CiRunService:
    """Index, review once, and say what a pipeline should do about it."""

    def __init__(
        self,
        *,
        repositories: RepositoryIndexService,
        reviews: ReviewService,
        baselines: BaselineService,
        triage: TriageService,
        lineages: LineageRepository,
    ) -> None:
        self._repositories = repositories
        self._reviews = reviews
        self._baselines = baselines
        self._triage = triage
        self._lineages = lineages

    def run(
        self,
        case_id: str,
        *,
        repository_root: Path,
        base_branch: str = DEFAULT_BRANCH_NAME,
        branch_name: str | None = None,
        fail_on: FailOn = FailOn.NEW_MATERIAL,
    ) -> CiRun:
        """Judge this checkout against one case, and report where it stands.

        `branch_name` is stated rather than detected because a CI checkout is detached: git
        knows the commit and not the branch it was reached from, and a run that believed the
        working tree would file every pull request under the default branch.

        One pass, and only one. `elicited_from` is left absent, so a first pass that has
        something to ask comes back holding and this returns it as it is. Running a second
        pass would mean answering the questions from somewhere, and the only two places to get
        an answer are a person and a guess.
        """

        version = self._repositories.index(repository_root, branch_name=branch_name)
        review = self._reviews.review(case_id, repository_root=repository_root)
        report = review.report
        if report is None:
            raise ReviewHasNoReportError(
                f"Review {review.review_id} ended as {review.status.value} and reached no "
                "verdicts, so there is nothing for this check to report."
            )
        base_branch_id = (
            derive_branch_id(version.repo_id, base_branch)
            if version.repo_id is not None
            else None
        )
        baseline = self._baselines.for_branch(base_branch_id) if base_branch_id else {}
        decisions = self._decisions_on(base_branch_id)
        boundaries = [
            _entry(item, baseline, decisions, questions=report.overview.open_questions)
            for item in report.reviewed
        ]
        blocking = [item.reference for item in boundaries if item.blocking]
        return CiRun(
            case_id=review.case_id,
            case_title=report.case_title,
            review_id=review.review_id,
            status=review.status,
            repo_id=version.repo_id,
            branch_id=review.branch_id,
            branch_name=version.branch_name or branch_name,
            base_branch_name=base_branch,
            base_branch_id=base_branch_id,
            atlas_version_id=review.atlas_version_id,
            reasoning_model=review.reasoning_model,
            baseline_size=len(baseline),
            counts=_counts(boundaries, report),
            boundaries=boundaries,
            blocking=blocking,
            fail_on=fail_on,
            exit_code=exit_code_for(blocking, fail_on),
        )

    def _decisions_on(self, branch_id: str | None) -> dict[str, StandingDecision]:
        """What the base branch currently thinks, keyed by boundary fingerprint.

        A base branch nobody has indexed in this workspace has no lineage row, and that is an
        ordinary state rather than an error: the first pull request against a fresh repository
        reaches this, and the honest answer is that nobody has decided anything. Asking the
        triage service would raise instead, because a *write* to an unknown branch is a
        mistake worth refusing and a read of one is not.
        """

        if branch_id is None or self._lineages.get_branch(branch_id) is None:
            return {}
        return {
            decision.boundary_fingerprint: decision
            for decision in self._triage.decisions_for_branch(branch_id)
        }


def exit_code_for(blocking: Sequence[str], fail_on: FailOn) -> int:
    """The process's answer, from the blocking set and what this run was told to fail for."""

    if fail_on is FailOn.NOTHING:
        return EXIT_CLEAN
    return EXIT_BLOCKING if blocking else EXIT_CLEAN


def _entry(
    boundary: ReviewedBoundary,
    baseline: Mapping[str, BaselineEntry],
    decisions: Mapping[str, StandingDecision],
    *,
    questions: Sequence[OpenQuestion],
) -> CiBoundary:
    disposition = disposition_of(boundary, baseline)
    decision = (
        decisions.get(boundary.fingerprint) if boundary.fingerprint is not None else None
    )
    holding = boundary.hinge is not None
    return CiBoundary(
        reference=boundary.reference,
        fingerprint=boundary.fingerprint,
        disposition=disposition,
        material=boundary.material,
        verdict_label=boundary.verdict_label,
        rationale=boundary.rationale,
        holding=holding,
        questions=[
            CiQuestion(
                reference=question.reference,
                question=question.question,
                unknown=question.unknown,
                answer_belongs_in=question.answer_belongs_in.value,
            )
            for question in questions
            if holding and boundary.reference in question.supporting_references
        ],
        decision=_joined(decision, boundary),
        verdict_reused_from=boundary.verdict_reused_from,
        blocking=is_blocking(
            disposition=disposition,
            material=boundary.material,
            holding=holding,
            decision=decision,
        ),
    )


def is_blocking(
    *,
    disposition: BoundaryDisposition,
    material: bool,
    holding: bool,
    decision: StandingDecision | None,
) -> bool:
    """Whether one boundary alone should fail the check.

    Four conditions, and each excludes a different way of being unfair. *New*, because a
    boundary the base branch has already seen is not something this change introduced.
    *Material*, because a cleared verdict is evidence the advisor looked and not a finding.
    *Undecided*, because a team that accepted or waived this exact structure has already
    answered — a parked boundary has not, which is what parking means. *Settled*, because a
    verdict resting on a question nobody was asked is not a basis for stopping anyone.

    Deliberately blind to `fail_on`: this says what the boundary is, and the run decides what
    to do about it. Mixing the two would make a boundary's own status depend on a flag.
    """

    if disposition is not BoundaryDisposition.NEW:
        return False
    if not material or holding:
        return False
    return decision is None or decision.state not in _SILENCING


def _joined(decision: StandingDecision | None, boundary: ReviewedBoundary) -> CiDecision | None:
    if decision is None:
        return None
    return CiDecision(
        decision_id=decision.decision_id,
        state=decision.state,
        author=decision.author,
        reason=decision.reason,
        branch_id=decision.branch_id,
        taken_on_this_verdict=decision.taken_on(
            material=boundary.material, verdict_label=boundary.verdict_label
        ),
    )


def _counts(boundaries: Sequence[CiBoundary], report: BoundaryReviewReport) -> CiCounts:
    totals = dict.fromkeys(BoundaryDisposition, 0)
    for item in boundaries:
        totals[item.disposition] += 1
    return CiCounts(
        new=totals[BoundaryDisposition.NEW],
        changed=totals[BoundaryDisposition.CHANGED],
        known=totals[BoundaryDisposition.KNOWN],
        holding=sum(1 for item in boundaries if item.holding),
        verdicts_reused=sum(
            1 for item in report.reviewed if item.verdict_reused_from is not None
        ),
        verdicts_total=len(report.reviewed),
    )


__all__ = [
    "EXIT_BLOCKING",
    "EXIT_CLEAN",
    "CiBoundary",
    "CiCounts",
    "CiDecision",
    "CiQuestion",
    "CiRun",
    "CiRunService",
    "FailOn",
    "exit_code_for",
    "is_blocking",
]
