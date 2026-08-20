from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from archcompass.domain import (
    ArchitectureCase,
    Candidate,
    Finding,
    Participant,
    RepositoryAtlas,
    RepositoryRef,
    Review,
    ReviewDelta,
    ReviewStatus,
    Verdict,
)
from archcompass.domain._support import utc_now
from archcompass.workflow.ci import CleanBreakCiRunService, FailOn


class Repositories:
    def index(self, root: Path, *, branch_name: str | None = None) -> object:
        return SimpleNamespace(repo_id="repo", branch_id="feature")


class Workflow:
    def __init__(self, review: Review) -> None:
        self.review = review

    def start(self, **_: object) -> Review:
        return self.review


class Decisions:
    def __init__(self, decided: set[str] | None = None) -> None:
        self.decided = decided or set()
        self.requested: tuple[str, ...] = ()

    def standings(self, *branch_ids: str) -> dict[str, object]:
        self.requested = branch_ids
        return {candidate_id: object() for candidate_id in self.decided}


def _review(tmp_path: Path) -> Review:
    repository = RepositoryRef("repo", tmp_path, "feature", "content")
    atlas = RepositoryAtlas("atlas", repository)
    material = Candidate.identified(
        pattern="boundary",
        summary="New material boundary",
        participants=(Participant("app.Port", "abstraction"),),
    )
    held = Candidate.identified(
        pattern="boundary",
        summary="Boundary waiting on context",
        participants=(Participant("app.HeldPort", "abstraction"),),
    )
    findings = (
        Finding(material, Verdict.MATERIAL, "It costs more than it earns.", (), ()),
        Finding(held, Verdict.HELD, "Intent is missing.", (), (), hinge="ownership"),
    )
    now = utc_now()
    return Review(
        "review",
        1,
        repository,
        atlas,
        ArchitectureCase.create(),
        findings,
        (),
        ReviewStatus.COMPLETED,
        ReviewDelta(new=(material, held)),
        now,
        now,
    )


def test_ci_blocks_only_new_material_unsettled_findings(tmp_path: Path) -> None:
    review = _review(tmp_path)
    decisions = Decisions()
    service = CleanBreakCiRunService(
        repositories=Repositories(), workflow=Workflow(review), decisions=decisions  # type: ignore[arg-type]
    )

    result = service.run("case", repository_root=tmp_path)

    assert result.exit_code == 1
    assert result.blocking_candidate_ids == (str(review.findings[0].candidate.id),)
    assert result.findings[1].holding is True
    assert result.findings[1].blocking is False
    assert decisions.requested[1] == "feature"


def test_ci_base_decision_and_adoption_mode_are_quiet(tmp_path: Path) -> None:
    review = _review(tmp_path)
    candidate_id = str(review.findings[0].candidate.id)
    decided = CleanBreakCiRunService(
        repositories=Repositories(),
        workflow=Workflow(review),
        decisions=Decisions({candidate_id}),  # type: ignore[arg-type]
    ).run("case", repository_root=tmp_path)
    adoption = CleanBreakCiRunService(
        repositories=Repositories(), workflow=Workflow(review), decisions=Decisions()  # type: ignore[arg-type]
    ).run("case", repository_root=tmp_path, fail_on=FailOn.NOTHING)

    assert decided.exit_code == 0
    assert decided.findings[0].decided is True
    assert adoption.exit_code == 0
    assert adoption.blocking_candidate_ids == (candidate_id,)
