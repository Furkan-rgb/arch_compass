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
that has decided nothing, so measuring it against itself would re-open every boundary the
repository settled on `main` years ago. The standings are read through the base chain, and
through the branch this run was told to compare against, because a boundary waived on `main`
was waived for the pull request too.

*Only boundaries this revision put on the table can fail the check.* Everything else is
information. A team must be able to switch this on before it has agreed with anything the tool
says, which is what `FailOn.NOTHING` is for, and ratchet it to blocking once it has.

The document speaks the partition rather than a baseline comparison. `new`, `changed` and
`known` are gone with the baseline that gave them their meaning: a revision reports what it
carried, what it judged, what it matched across a rename, and what closed — and, cutting
across all of that, which boundaries still need somebody's attention. That last number is the
one a pipeline acts on, and it is defined once, in `application/standings.py`, so the check and
the workspace cannot disagree about what is outstanding.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from enum import StrEnum
from pathlib import Path
from typing import Literal

from pydantic import Field

from archcompass.application.repository_index import RepositoryIndexService
from archcompass.application.reviews import ReviewService
from archcompass.application.standings import needs_attention, standing_for
from archcompass.application.triage import TriageService
from archcompass.domain.base import DomainModel
from archcompass.domain.delta import AddressedBoundary, BoundaryState, JudgedBecause
from archcompass.domain.errors import ReviewHasNoReportError
from archcompass.domain.lineage import DEFAULT_BRANCH_NAME, derive_branch_id
from archcompass.domain.review import (
    BoundaryReviewReport,
    OpenQuestion,
    ReviewedBoundary,
    ReviewStatus,
)
from archcompass.domain.triage import DecisionState, StandingDecision

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

    #: A boundary this revision judged, that the advisor thinks is costing more than it earns,
    #: that nobody has decided about, and that is not resting on an unanswered question.
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
    #: The branch the decision is held on, which may be a base branch rather than this run's:
    #: an inherited decision names where it was actually taken.
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
    #: Where this boundary stands against the branch's previous revision, copied off the
    #: stored review rather than recomputed. `None` on a run that had nothing to compare with —
    #: no branch lineage — which is not the same as having compared and found no difference.
    delta_state: BoundaryState | None = None
    #: Which input moved, where this revision did not carry the boundary. Named rather than
    #: left as "changed", so a reader is never told their code moved when the model did.
    judged_because: JudgedBecause | None = None
    #: The fingerprint this boundary succeeded, where a rename was matched. What the standing
    #: was carried across from.
    succeeds: str | None = None
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
    #: Material and undecided: the boundary is still asking something of the team. Reported
    #: separately from `blocking`, because a held boundary needs attention and cannot fail a
    #: pipeline, and telling a reader those are the same thing would be false either way.
    needs_attention: bool = False
    #: The review this verdict was first reached in, when it was reused rather than reached
    #: again. `None` means the model was asked about this boundary during this run.
    verdict_reused_from: str | None = None
    #: Whether this boundary alone would fail the check, before `fail_on` is applied.
    blocking: bool = False


class CiCounts(DomainModel):
    """How this run's boundaries divide.

    `carried + judged + succeeded` is every boundary reviewed; `addressed` counts lines that
    closed and therefore have no row in the report at all. `attention` and `holding` cut
    across the rest rather than sitting beside them — a boundary that needs attention is still
    carried or judged, and where it stands and whether anyone has answered it are two
    different questions.
    """

    carried: int = 0
    judged: int = 0
    succeeded: int = 0
    addressed: int = 0
    #: How many of the judged boundaries are fingerprints this branch closed and that are back.
    resurfaced: int = 0
    #: Material and undecided, through the read-through. The number a team acts on.
    attention: int = 0
    holding: int = 0
    #: How many verdicts were reused from an earlier run, and how many there were in total.
    #: The pair rather than a ratio, so a reader can see "3 of 47" and not a percentage.
    verdicts_reused: int = 0
    verdicts_total: int = 0


class CiRun(DomainModel):
    """What one headless run found, in the form a pipeline consumes it.

    Version 2. The baseline is gone and the document that spoke in its vocabulary had to go
    with it: `new`/`changed`/`known` and `baseline_size` are not renamed here, they stopped
    being true. What replaces them is the revision partition, which is a statement about two
    immutable revisions rather than about what somebody has pressed a button on since.

    Computed, never stored — the review behind it is the record. The partition is read off
    that record rather than recomputed; what is genuinely computed here is where each boundary
    stands with the team, which is a fact about now.
    """

    schema_version: Literal[2] = 2
    case_id: str
    case_title: str
    review_id: str
    status: ReviewStatus
    repo_id: str | None = None
    #: The lineage this run wrote to: the branch under review.
    branch_id: str | None = None
    branch_name: str | None = None
    #: The lineage this run also read standings from. `branch_id` when a run is on its own base
    #: branch, which is the ordinary shape of a scheduled run on `main`.
    base_branch_name: str
    base_branch_id: str | None = None
    atlas_version_id: str
    reasoning_model: str
    #: The revision this one was judged against, and whether there was one. A first revision
    #: judges everything, and none of that means anything moved.
    previous_review_id: str | None = None
    first_revision: bool = True
    counts: CiCounts
    boundaries: list[CiBoundary] = Field(default_factory=list[CiBoundary])
    #: The lines that closed: present in the previous revision, matched by nothing here. The
    #: best news the tool has to deliver, and the only part of the partition with no row in
    #: `boundaries` — an addressed boundary was not detected in this run.
    addressed: list[AddressedBoundary] = Field(default_factory=list[AddressedBoundary])
    #: The references of every blocking boundary, in report order. Empty is the clean run.
    blocking: list[str] = Field(default_factory=list[str])
    fail_on: FailOn
    exit_code: int

    @property
    def surfaced(self) -> list[CiBoundary]:
        """Everything this revision did not carry, in report order: what the run is about.

        Carried boundaries are counted and not listed. They are neither hidden nor repeated —
        the count is a claim a reader can go and audit in the workspace — and a check that
        re-presented forty of them on every push would be read exactly once.
        """

        return [
            item for item in self.boundaries if item.delta_state is not BoundaryState.CARRIED
        ]

    @property
    def attention(self) -> list[CiBoundary]:
        """Material and undecided, wherever it stands in the partition."""

        return [item for item in self.boundaries if item.needs_attention]

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
        triage: TriageService,
    ) -> None:
        self._repositories = repositories
        self._reviews = reviews
        self._triage = triage

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
        standings = self._standings(review.branch_id, base_branch_id)
        boundaries = [
            _entry(item, standings, questions=report.overview.open_questions)
            for item in report.reviewed
        ]
        blocking = [item.reference for item in boundaries if item.blocking]
        delta = report.delta
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
            previous_review_id=None if delta is None else delta.previous_review_id,
            first_revision=True if delta is None else delta.first_revision,
            counts=_counts(boundaries, report),
            boundaries=boundaries,
            addressed=[] if delta is None else list(delta.addressed_boundaries),
            blocking=blocking,
            fail_on=fail_on,
            exit_code=exit_code_for(blocking, fail_on),
        )

    def _standings(
        self, branch_id: str | None, base_branch_id: str | None
    ) -> dict[str, StandingDecision]:
        """What governs this run's boundaries: the branch's own chain, over the named base's.

        Two reads rather than one, because the two answers come from different places and both
        are legitimate. The chain is what the workspace recorded — a branch pointed at the
        branch it was cut from — and `--base-branch` is what the pipeline states, which is the
        only signal available when the workspace has never seen the base branch at all. Where
        they agree, which is the ordinary scheduled run on `main`, the merge is a no-op.

        The run's own branch is applied last and therefore wins, which is the same rule the
        chain follows internally: the nearest opinion governs.
        """

        standings = self._triage.standings_for_branch(base_branch_id)
        standings.update(self._triage.standings_for_branch(branch_id))
        return standings


def exit_code_for(blocking: Sequence[str], fail_on: FailOn) -> int:
    """The process's answer, from the blocking set and what this run was told to fail for."""

    if fail_on is FailOn.NOTHING:
        return EXIT_CLEAN
    return EXIT_BLOCKING if blocking else EXIT_CLEAN


def _entry(
    boundary: ReviewedBoundary,
    standings: Mapping[str, StandingDecision],
    *,
    questions: Sequence[OpenQuestion],
) -> CiBoundary:
    decision = standing_for(boundary, standings)
    holding = boundary.hinge is not None
    attention = needs_attention(boundary, standings)
    return CiBoundary(
        reference=boundary.reference,
        fingerprint=boundary.fingerprint,
        delta_state=boundary.delta_state,
        judged_because=boundary.judged_because,
        succeeds=boundary.succeeds,
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
        needs_attention=attention,
        verdict_reused_from=boundary.verdict_reused_from,
        blocking=is_blocking(
            delta_state=boundary.delta_state,
            needs_attention=attention,
            holding=holding,
        ),
    )


def is_blocking(
    *,
    delta_state: BoundaryState | None,
    needs_attention: bool,
    holding: bool,
) -> bool:
    """Whether one boundary alone should fail the check.

    Three conditions, and each excludes a different way of being unfair. *This revision put it
    on the table*, because a boundary that carried is one nothing has moved under since the
    last run said its piece — and a boundary that carried its standing across a rename is not
    something this change introduced either. *Needs attention*, which is material and undecided
    read through the base branch: a cleared verdict is evidence the advisor looked rather than
    a finding, and a team that accepted, waived or parked this structure has already answered.
    *Settled*, because a verdict resting on a question nobody was asked is not a basis for
    stopping anyone.

    A boundary with no partition at all — a run whose atlas predates branch lineages, so there
    was no previous revision to compare with — counts as judged. That is what the run itself
    does with it: everything is on the table when nothing could be compared, which is exactly
    the state a first run is in.

    Deliberately blind to `fail_on`: this says what the boundary is, and the run decides what
    to do about it. Mixing the two would make a boundary's own status depend on a flag.
    """

    if delta_state in (BoundaryState.CARRIED, BoundaryState.SUCCEEDED):
        return False
    return needs_attention and not holding


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
    delta = report.delta
    totals = dict.fromkeys(BoundaryState, 0)
    for item in boundaries:
        # `None` is the run that could not partition itself, and it is counted as judged for
        # the reason `is_blocking` treats it as judged: everything was on the table.
        totals[item.delta_state or BoundaryState.JUDGED] += 1
    return CiCounts(
        carried=totals[BoundaryState.CARRIED],
        judged=totals[BoundaryState.JUDGED],
        succeeded=totals[BoundaryState.SUCCEEDED],
        addressed=0 if delta is None else delta.addressed,
        resurfaced=0 if delta is None else delta.resurfaced,
        attention=sum(1 for item in boundaries if item.needs_attention),
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
