"""A revision judges the delta, and keeps the line through it.

Every test here is a pair of runs over the same branch with something specific moved between
them, because that is the only way to assert a claim about a *delta*: a single run has
nothing to be a delta against, and the whole design is about what the second one does with
what the first one left.

Against a real committed git repository in `tmp_path`, because the partition keys on
`branch_id` and that identity comes from the root commit and the branch name. A workspace
beside the repository rather than around it, since what a workspace holds is excluded from
its own atlases.

The repository is three modules and yields exactly two boundaries — an abstraction with one
implementation, and a module name that has leaked past its package — which is what makes the
mixed assertions possible: a change that moves one of them must leave the other alone, and a
partition that could only say "everything" or "nothing" would pass every test here while
being useless.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from archcompass.adapters.models.deterministic import DETERMINISTIC_MODEL
from archcompass.bootstrap import Runtime, build_runtime, pinned_model
from archcompass.domain.atlas import FindingCandidate, FindingPattern
from archcompass.domain.case import ArchitectureCase, RepositoryReference
from archcompass.domain.delta import BoundaryLineEventType, BoundaryState, JudgedBecause
from archcompass.domain.errors import NothingToReviewError
from archcompass.domain.policy import PolicyDocument
from archcompass.domain.review import (
    BoundaryReview,
    BoundaryReviewReport,
    CandidateVerdict,
    OpenQuestion,
    ReviewedBoundary,
    ReviewOverview,
    ReviewStatus,
)
from archcompass.domain.triage import DecisionComment, DecisionState, StandingDecision
from archcompass.ports.reasoning import FocusedReasoningProvider, ReasoningTask

PORTS = '''from typing import Protocol


class Store(Protocol):
    """Where narration audio is kept."""

    def put(self, key: str, payload: bytes) -> None: ...

    def get(self, key: str) -> bytes: ...
'''

DISK = '''from pathlib import Path

from ports import Store


class DiskStore(Store):
    """Keeps audio on the local disk."""

    def __init__(self, root: Path) -> None:
        self._root = root

    def put(self, key: str, payload: bytes) -> None:
        (self._root / key).write_bytes(payload)

    def get(self, key: str) -> bytes:
        return (self._root / key).read_bytes()
'''

APP = '''from pathlib import Path

from disk import DiskStore
from ports import Store


def build(root: Path) -> Store:
    return DiskStore(root)
'''

#: A second implementation of the same abstraction. Nothing is renamed and nothing is
#: deleted, and yet the sole-implementation boundary stops existing — which is exactly the
#: shape of a boundary somebody addressed.
MEMORY = '''from ports import Store


class MemoryStore(Store):
    """Keeps audio in this process."""

    def __init__(self) -> None:
        self._items: dict[str, bytes] = {}

    def put(self, key: str, payload: bytes) -> None:
        self._items[key] = payload

    def get(self, key: str) -> bytes:
        return self._items[key]
'''

#: The same class, same name, same file, with its method bodies rewritten. Nothing the shape
#: fingerprint can see has moved: this is the content dimension and nothing else.
REWRITTEN_DISK = '''from pathlib import Path

from ports import Store


class DiskStore(Store):
    """Keeps audio on the local disk, one directory per key."""

    def __init__(self, root: Path) -> None:
        self._root = root

    def put(self, key: str, payload: bytes) -> None:
        target = self._root / key
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(payload)

    def get(self, key: str) -> bytes:
        target = self._root / key
        if not target.exists():
            raise KeyError(key)
        return target.read_bytes()
'''


class RecordingReasoner:
    """The real substitute, plus a record of what each stage was actually shown.

    Wrapping rather than replacing, so the run goes on working: what is asserted here is not
    what the model concluded but which boundaries it was asked about, and that is a property
    of the application whatever a real model would have said.
    """

    def __init__(self, delegate: FocusedReasoningProvider) -> None:
        self._delegate = delegate
        self.judgements = 0
        #: One entry per elicitation, holding the references it was given. A list rather than
        #: a flag because "asked about nothing" and "not asked at all" are different things
        #: and only one of them is what a carried revision does.
        self.elicited: list[list[str]] = []

    @property
    def model_identity(self) -> str:
        return self._delegate.model_identity

    def prompt_identity(self, task: ReasoningTask) -> str:
        return self._delegate.prompt_identity(task)

    def judge_finding_candidate(
        self,
        case: ArchitectureCase,
        candidate: FindingCandidate,
        policies: list[PolicyDocument],
    ) -> CandidateVerdict:
        self.judgements += 1
        return self._delegate.judge_finding_candidate(case, candidate, policies)

    def elicit_questions(
        self,
        case: ArchitectureCase,
        boundaries: list[ReviewedBoundary],
    ) -> list[OpenQuestion]:
        self.elicited.append([item.reference for item in boundaries])
        return self._delegate.elicit_questions(case, boundaries)

    def summarise_review(
        self,
        case: ArchitectureCase,
        boundaries: list[ReviewedBoundary],
    ) -> ReviewOverview:
        return self._delegate.summarise_review(case, boundaries)


def _git(repository: Path, *arguments: str) -> None:
    subprocess.run(
        ["git", "-C", str(repository), *arguments],
        check=True,
        capture_output=True,
        text=True,
        timeout=30,
    )


@pytest.fixture
def repository(tmp_path: Path) -> Path:
    """Three modules, committed, so the branch has a durable identity to be a line on."""

    checkout = tmp_path / "repository"
    checkout.mkdir()
    (checkout / "ports.py").write_text(PORTS, encoding="utf-8")
    (checkout / "disk.py").write_text(DISK, encoding="utf-8")
    (checkout / "app.py").write_text(APP, encoding="utf-8")
    _git(checkout, "init", "--quiet", "-b", "main")
    _git(checkout, "config", "user.email", "test@example.invalid")
    _git(checkout, "config", "user.name", "Test")
    _git(checkout, "add", ".")
    _git(checkout, "commit", "--quiet", "-m", "first")
    return checkout


@pytest.fixture
def workspace(tmp_path: Path) -> Runtime:
    return build_runtime(
        tmp_path / "workspace", pin=pinned_model("fake", DETERMINISTIC_MODEL)
    )


@pytest.fixture
def reasoner(workspace: Runtime, monkeypatch: pytest.MonkeyPatch) -> RecordingReasoner:
    service = workspace.review_service
    spy = RecordingReasoner(service._reasoner)  # pyright: ignore[reportPrivateUsage]
    monkeypatch.setattr(service, "_reasoner", spy)
    return spy


@pytest.fixture
def case_id(workspace: Runtime, repository: Path) -> str:
    """A case that says enough that no verdict hinges on what it left out.

    Deliberately not an empty case. An unwritten one leaves the substitute hinging on what is
    coming, so every run would stop to ask and the assertions here would be about the
    elicitation loop rather than about the delta. What is under test is which boundaries reach
    the asking stage, not whether the asking stage finds anything to say.
    """

    revision = workspace.case_repository.create(
        ArchitectureCase(
            title="Where audio lives",
            problem_statement="Decide where the store abstraction earns its place.",
            desired_outcome="One owner for storage differences.",
            expected_future_changes=["A hosted store may be added next year"],
            repository=RepositoryReference(root_path=str(repository)),
        ),
        actor="test",
    )
    return revision.case_id


def _review(workspace: Runtime, case_id: str, repository: Path) -> BoundaryReview:
    """One revision: re-index whatever the repository says now, then judge the delta."""

    workspace.repository_service.index(repository)
    return workspace.review_service.review(case_id, repository_root=repository)


def _report(review: BoundaryReview) -> BoundaryReviewReport:
    report = review.report
    assert report is not None
    return report


def _of_pattern(review: BoundaryReview, pattern: FindingPattern) -> ReviewedBoundary:
    matching = [
        item for item in _report(review).reviewed if item.candidate.pattern is pattern
    ]
    assert len(matching) == 1, f"expected exactly one {pattern.value} boundary"
    return matching[0]


def _standing(
    workspace: Runtime, branch_id: str, fingerprint: str
) -> StandingDecision | None:
    """What this branch currently thinks about one boundary, read the way a page reads it."""

    return next(
        (
            item
            for item in workspace.triage_service.decisions_for_branch(branch_id)
            if item.boundary_fingerprint == fingerprint
        ),
        None,
    )


def _states(review: BoundaryReview) -> dict[str, BoundaryState | None]:
    return {
        item.candidate.pattern.value: item.delta_state for item in _report(review).reviewed
    }


def test_a_first_revision_judges_everything_and_says_it_had_nothing_to_compare_with(
    workspace: Runtime, reasoner: RecordingReasoner, case_id: str, repository: Path
) -> None:
    """The base case, and the one that must not read as "nothing changed".

    A branch's first revision has no predecessor, so every boundary is news — but the delta
    has to say *why* it is all news, because a page that showed two judged boundaries with no
    further context would look identical whether this was revision one or a revision that
    broke everything.
    """

    first = _review(workspace, case_id, repository)

    report = _report(first)
    assert first.status is ReviewStatus.SUCCEEDED
    delta = report.delta
    assert delta is not None
    assert delta.first_revision is True
    assert delta.previous_review_id is None
    assert (delta.judged, delta.carried, delta.succeeded, delta.addressed) == (2, 0, 0, 0)
    assert all(
        item.judged_because is JudgedBecause.NEW for item in report.reviewed
    ), "on a first revision every boundary is new, and none of them is a change"
    assert reasoner.judgements == 2, "and every one of them was paid for"


def test_an_unchanged_rerun_is_refused_before_anything_is_written(
    workspace: Runtime, reasoner: RecordingReasoner, case_id: str, repository: Path
) -> None:
    """The headline promise: a revision that would change nothing is reported, not recorded.

    Refused by the run itself rather than by whichever button asked — the service works out
    the whole partition before the run has a record, so every caller gets the same answer,
    and a branch's history stays a line of what happened to the code rather than of who
    pressed what. The refusal names the revision the repository is already up to date with,
    and the three tables a revision appends to are exactly as they were.
    """

    first = _review(workspace, case_id, repository)
    before = _rows(workspace)
    paid = reasoner.judgements
    asked = len(reasoner.elicited)

    with pytest.raises(NothingToReviewError, match="Nothing has changed") as refusal:
        _review(workspace, case_id, repository)

    assert refusal.value.current_against == first.review_id, (
        "the reader is told which revision they are already up to date with"
    )
    assert _rows(workspace) == before, (
        "no case revision, no review row, and nothing on the branch's ledger"
    )
    assert reasoner.judgements == paid, "no boundary was put to the model to find that out"
    assert len(reasoner.elicited) == asked, "and the asking stage was never reached"


def test_a_rewrite_that_renames_nothing_is_judged_again(
    workspace: Runtime, reasoner: RecordingReasoner, case_id: str, repository: Path
) -> None:
    """The content dimension, which the shape fingerprint alone cannot see.

    `DiskStore` keeps its name, its file and its abstraction; only its method bodies change.
    Without a content term in the inputs identity this carries the old verdict for ever — the
    advisor reporting a judgement about code that no longer exists, with nothing in the record
    admitting it. The other boundary is untouched by the edit and must stay quiet, which is
    what makes this an assertion about the delta rather than about a cache being cleared.
    """

    first = _review(workspace, case_id, repository)
    paid = reasoner.judgements
    (repository / "disk.py").write_text(REWRITTEN_DISK, encoding="utf-8")

    second = _review(workspace, case_id, repository)

    rewritten = _of_pattern(second, FindingPattern.SOLE_IMPLEMENTATION)
    assert rewritten.delta_state is BoundaryState.JUDGED
    assert rewritten.judged_because is JudgedBecause.CONTENT
    assert rewritten.fingerprint == _of_pattern(
        first, FindingPattern.SOLE_IMPLEMENTATION
    ).fingerprint, "the shape never moved, which is exactly why content had to be an input"
    assert rewritten.verdict_reused_from is None, "it was genuinely put to the model again"
    assert reasoner.judgements == paid + 1, "and only it was"
    assert (
        _of_pattern(second, FindingPattern.SCATTERED_CONCEPT).delta_state
        is BoundaryState.CARRIED
    ), "an edit somewhere else is not a reason to re-open a boundary it did not touch"


def test_renaming_a_participant_carries_the_standing_across_and_records_the_succession(
    workspace: Runtime, case_id: str, repository: Path
) -> None:
    """A rename is a new fingerprint, and without succession the decision silently orphans.

    The team accepts the boundary, somebody renames the class, and what must not happen is the
    boundary coming back as brand new with the acceptance stranded on a fingerprint nothing
    detects any more. It carries across, it says which fingerprint it came from — so the page
    can mark it rather than apply it silently — and the succession is on the branch's ledger,
    filed under the predecessor, where anyone asking what became of that decision will look.
    """

    first = _review(workspace, case_id, repository)
    branch_id = first.branch_id
    assert branch_id is not None
    before = _of_pattern(first, FindingPattern.SOLE_IMPLEMENTATION)
    assert before.fingerprint is not None
    workspace.triage_service.decide(
        StandingDecision(
            branch_id=branch_id,
            boundary_fingerprint=before.fingerprint,
            state=DecisionState.ACCEPTED,
            author="test",
            review_id=first.review_id,
            boundary_reference=before.reference,
            material=before.material,
            verdict_label=before.verdict_label,
        )
    )

    (repository / "disk.py").write_text(
        DISK.replace("DiskStore", "LocalDiskStore"), encoding="utf-8"
    )
    (repository / "app.py").write_text(
        APP.replace("DiskStore", "LocalDiskStore"), encoding="utf-8"
    )
    second = _review(workspace, case_id, repository)

    after = _of_pattern(second, FindingPattern.SOLE_IMPLEMENTATION)
    assert after.fingerprint != before.fingerprint, "renaming a participant is a new shape"
    assert after.delta_state is BoundaryState.SUCCEEDED
    assert after.judged_because is JudgedBecause.SHAPE
    assert after.succeeds == before.fingerprint
    delta = _report(second).delta
    assert delta is not None
    assert delta.succeeded == 1
    assert delta.addressed == 0, "a shape that was matched has not gone anywhere"
    assert delta.addressed_boundaries == []

    events = workspace.boundary_line_repository.history(branch_id, before.fingerprint)
    assert [item.event for item in events] == [BoundaryLineEventType.SUCCEEDED]
    assert events[0].successor_fingerprint == after.fingerprint
    assert events[0].review_id == second.review_id
    standing = _standing(workspace, branch_id, before.fingerprint)
    assert standing is not None and standing.state is DecisionState.ACCEPTED, (
        "the decision was never moved, which is what the successor's mark points at"
    )


def test_a_boundary_that_vanished_closes_as_addressed_and_keeps_its_thread(
    workspace: Runtime, case_id: str, repository: Path
) -> None:
    """The best news the tool can deliver, which it used to throw away by going quiet.

    A second implementation appears, so the sole-implementation boundary stops existing. No
    successor matches it — the pattern is gone, not moved — so the revision reports it closed,
    names what closed, and files the closure on the branch's ledger. What was argued about it
    stays exactly where it was: a closed line is not a deleted one, which is what makes taking
    the closure automatically safe.
    """

    first = _review(workspace, case_id, repository)
    branch_id = first.branch_id
    assert branch_id is not None
    gone = _of_pattern(first, FindingPattern.SOLE_IMPLEMENTATION)
    assert gone.fingerprint is not None
    workspace.triage_service.comment(
        DecisionComment(
            branch_id=branch_id,
            boundary_fingerprint=gone.fingerprint,
            author="test",
            body="We think a second store is coming, so this one earns its place.",
        )
    )

    (repository / "memory.py").write_text(MEMORY, encoding="utf-8")
    second = _review(workspace, case_id, repository)

    assert [item.candidate.pattern for item in _report(second).reviewed] == [
        FindingPattern.SCATTERED_CONCEPT
    ], "the boundary really is not there any more"
    delta = _report(second).delta
    assert delta is not None
    assert delta.addressed == 1
    closed = delta.addressed_boundaries[0]
    assert closed.fingerprint == gone.fingerprint
    assert closed.title == gone.candidate.summary, "named in the words it was presented in"
    assert closed.material == gone.material
    assert closed.verdict_label == gone.verdict_label
    assert closed.last_seen_in_review == first.review_id
    assert closed.last_reference == gone.reference

    events = workspace.boundary_line_repository.history(branch_id, gone.fingerprint)
    assert [item.event for item in events] == [BoundaryLineEventType.ADDRESSED]
    thread = workspace.triage_service.comments(branch_id, gone.fingerprint)
    assert [item.body for item in thread] == [
        "We think a second store is coming, so this one earns its place."
    ], "closing a line archives the argument with it; it does not delete it"


def test_a_reappearing_fingerprint_resurfaces_with_the_standing_it_had(
    workspace: Runtime, case_id: str, repository: Path
) -> None:
    """Three revisions: here, gone, back. The rule that makes automatic closure safe.

    Nothing is restored when a boundary returns, because nothing was taken away — the standing
    and its thread key on `(branch, fingerprint)` and simply apply again. What the revision
    adds is the *saying so*: the boundary is marked as having been closed earlier and by which
    revision, so the page can say "addressed in an earlier revision, back now" rather than
    presenting a boundary with a history as though nobody had ever seen it.
    """

    first = _review(workspace, case_id, repository)
    branch_id = first.branch_id
    assert branch_id is not None
    original = _of_pattern(first, FindingPattern.SOLE_IMPLEMENTATION)
    assert original.fingerprint is not None
    workspace.triage_service.decide(
        StandingDecision(
            branch_id=branch_id,
            boundary_fingerprint=original.fingerprint,
            state=DecisionState.WAIVED,
            author="test",
            reason="A hosted store is planned, so the abstraction stays.",
            review_id=first.review_id,
            boundary_reference=original.reference,
            material=original.material,
            verdict_label=original.verdict_label,
        )
    )

    (repository / "memory.py").write_text(MEMORY, encoding="utf-8")
    closing = _review(workspace, case_id, repository)
    (repository / "memory.py").unlink()
    back = _review(workspace, case_id, repository)

    returned = _of_pattern(back, FindingPattern.SOLE_IMPLEMENTATION)
    assert returned.fingerprint == original.fingerprint
    assert returned.delta_state is BoundaryState.JUDGED
    assert returned.judged_because is JudgedBecause.RESURFACED, (
        "it is news again, but not the same kind of news as something never seen"
    )
    assert returned.resurfaced_from_review == closing.review_id
    delta = _report(back).delta
    assert delta is not None
    assert delta.resurfaced == 1

    events = workspace.boundary_line_repository.history(branch_id, original.fingerprint)
    assert [item.event for item in events] == [
        BoundaryLineEventType.ADDRESSED,
        BoundaryLineEventType.RESURFACED,
    ]
    standing = _standing(workspace, branch_id, original.fingerprint)
    assert standing is not None and standing.state is DecisionState.WAIVED
    assert standing.reason == "A hosted store is planned, so the abstraction stays."


def test_elicitation_is_shown_only_the_boundaries_this_revision_judged(
    workspace: Runtime, reasoner: RecordingReasoner, case_id: str, repository: Path
) -> None:
    """The rule that makes re-asking structurally impossible rather than merely cached away.

    The first revision has everything on the table and shows the asking stage both boundaries.
    The second changes one of them, and the stage is handed that one alone — not because a
    question about the other was composed and discarded, but because the run does not have it
    to compose from.
    """

    first = _review(workspace, case_id, repository)
    assert reasoner.elicited == [
        [item.reference for item in _report(first).reviewed]
    ], "a first revision has nothing settled, so everything may be asked about"

    (repository / "disk.py").write_text(REWRITTEN_DISK, encoding="utf-8")
    second = _review(workspace, case_id, repository)

    judged = _of_pattern(second, FindingPattern.SOLE_IMPLEMENTATION)
    assert reasoner.elicited[-1] == [judged.reference]
    assert _states(second) == {
        FindingPattern.SOLE_IMPLEMENTATION.value: BoundaryState.JUDGED,
        FindingPattern.SCATTERED_CONCEPT.value: BoundaryState.CARRIED,
    }


def _rows(workspace: Runtime) -> dict[str, int]:
    """How much this workspace has written, in the three tables a revision appends to.

    Counted from the tables rather than through the services, because what is being asserted
    is the absence of writes and a service can only be asked what it would return. A row
    count is the one reading that cannot be satisfied by a repository quietly answering from
    somewhere else.
    """

    with workspace.database.connect() as connection:
        return {
            table: int(
                connection.execute(f"SELECT count(*) AS total FROM {table}").fetchone()[
                    "total"
                ]
            )
            for table in ("case_revisions", "boundary_reviews", "boundary_lines")
        }


def test_a_quiet_second_pass_is_still_recorded_because_it_closes_the_loop(
    workspace: Runtime, reasoner: RecordingReasoner, case_id: str, repository: Path
) -> None:
    """The one caller the refusal must not touch: a second pass over untouched code.

    A reader may answer nothing at all, and the loop still has to end — the second pass
    concludes without asking again, which only works if it is allowed to run when every
    boundary would carry. So the quiet gate applies to first passes alone, and this run
    records a revision whose whole delta is carried verdicts: not noise, but the record
    that the round was closed.
    """

    first = _review(workspace, case_id, repository)
    paid = reasoner.judgements

    second = workspace.review_service.review(
        case_id, repository_root=repository, elicited_from=first.review_id
    )

    assert second.status is ReviewStatus.SUCCEEDED
    report = _report(second)
    assert report.overview.open_questions == [], "a second pass never asks"
    delta = report.delta
    assert delta is not None
    assert (delta.carried, delta.judged) == (2, 0)
    assert delta.quiet
    assert reasoner.judgements == paid, "every verdict was carried, none was paid for again"


def test_two_branches_of_one_repository_are_two_lines(
    workspace: Runtime, repository: Path
) -> None:
    """The delta scopes to the branch even where the case does not.

    A feature branch's first revision compares against nothing, however much has been reviewed
    on `main`. Comparing across would tell a branch that boundaries it never touched are its
    own carried work — and, the other way round, would let `main`'s history close lines the
    branch still has.

    The case is the deliberate exception, and this is where the two rules sit side by side.
    A branch reads through to the one it came from for the *backbone* — the answers on `main`
    are about this code, and re-asking them would be the failure continuity exists to prevent
    — while the line of revisions stays its own. What a branch inherits is context; what it
    owns is its history.
    """

    on_main = workspace.repository_service.index(repository)
    main_case = workspace.case_service.continue_from_repository(
        repository, branch_id=on_main.branch_id
    ).case_id
    first = workspace.review_service.review(main_case, repository_root=repository)

    _git(repository, "checkout", "--quiet", "-b", "feature")
    on_feature = workspace.repository_service.index(repository)
    feature_case = workspace.case_service.continue_from_repository(
        repository, branch_id=on_feature.branch_id
    ).case_id

    assert on_feature.branch_id != on_main.branch_id
    assert feature_case == main_case, "the branch reads main's case through, rather than blank"
    second = workspace.review_service.review(feature_case, repository_root=repository)
    delta = _report(second).delta
    assert delta is not None
    assert delta.first_revision is True, "the branch's own line starts here"
    assert delta.previous_review_id is None
    assert delta.carried == 0
    assert first.branch_id == on_main.branch_id
