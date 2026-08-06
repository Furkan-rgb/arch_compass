"""Reviewing the same repository twice continues the conversation it started.

The first pass asks, the reader answers, the second concludes — and then the reader comes
back next week and points at the same repository again. What they get has to be the case
they wrote by answering, not a blank one that asks them the same five questions: an advisor
that forgets what it was told between visits is one nobody uses twice.

Committed git repositories in `tmp_path`, because continuity is keyed on `repo_id` and that
identity comes from the root commit. A workspace beside the repository rather than around
it, since what a workspace holds is excluded from its own atlases.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

pytest.importorskip("fastapi")

from fastapi.testclient import TestClient

from archcompass.adapters.models.deterministic import DETERMINISTIC_MODEL
from archcompass.application.cases import WrittenAnswer
from archcompass.bootstrap import Runtime, build_runtime, pinned_model
from archcompass.domain.errors import NothingToReviewError
from archcompass.domain.review import BoundaryReview, ReviewStatus
from archcompass.presentation.web import create_app

EXAMPLE = Path("eval/cases/warehouse-sync/repository").resolve()


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
    """The example repository, committed, so it has a root commit to be identified by."""

    checkout = tmp_path / "repository"
    shutil.copytree(EXAMPLE, checkout)
    _git(checkout.parent, "init", "--quiet", "-b", "main", checkout.name)
    _git(checkout, "config", "user.email", "test@example.invalid")
    _git(checkout, "config", "user.name", "Test")
    _git(checkout, "add", ".")
    _git(checkout, "commit", "--quiet", "-m", "first")
    return checkout


@pytest.fixture
def workspace(tmp_path: Path) -> Runtime:
    """A workspace beside the repository under review, not around it."""

    return build_runtime(
        tmp_path / "workspace", pin=pinned_model("fake", DETERMINISTIC_MODEL)
    )


def _started(workspace: Runtime, repository: Path) -> str:
    """The case a visitor gets by pointing at this repository, which is what the web start
    step does: index, then ask the application which case this repository is reviewed under.
    """

    version = workspace.repository_service.index(repository)
    return workspace.case_service.continue_from_repository(
        repository, branch_id=version.branch_id
    ).case_id


def _answer(workspace: Runtime, review: BoundaryReview) -> None:
    """Answer everything the run asked, the way the reader does through the browser."""

    report = review.report
    assert report is not None
    asked = report.overview.open_questions
    assert asked, "this run was supposed to have something to ask"
    workspace.case_service.answer(
        review,
        [
            WrittenAnswer(
                question_reference=question.reference,
                recorded_text="A second warehouse vendor arrives next quarter.",
            )
            for question in asked
        ],
    )


def test_a_repeat_review_continues_the_answered_case_and_concludes_in_one_pass(
    workspace: Runtime, repository: Path
) -> None:
    """The headline: coming back to a repository resumes the case, and it shows.

    Three visits, and the third is the one under test. One and two are the ordinary loop —
    ask, answer, conclude — and they are here because they are what leaves something to
    continue from. The third names no case at all, which is exactly what the browser sends
    when somebody points at a repository they have reviewed before.

    Continuity is what makes the third visit's answer honest: it resumes the same case at
    the revision the answers reached, so the partition finds nothing moved — not the code,
    not the case — and the run refuses to record a revision that would repeat the concluded
    one. The reader is told which revision they are already current against instead of
    being handed a copy of it, and not one model call is spent finding that out.
    """

    case_id = _started(workspace, repository)
    first = workspace.review_service.review(case_id, repository_root=repository)
    assert first.status is ReviewStatus.AWAITING_ANSWERS
    _answer(workspace, first)
    second = workspace.review_service.review(
        case_id, repository_root=repository, elicited_from=first.review_id
    )
    assert second.status is ReviewStatus.SUCCEEDED

    continued = _started(workspace, repository)

    assert continued == case_id, "a repeat visit is the same conversation, not a new one"
    revision = workspace.case_repository.get(continued)
    assert revision.snapshot.clarifications, (
        "and it arrives holding the answers, which is the whole point of continuing it"
    )

    with pytest.raises(NothingToReviewError) as refused:
        workspace.review_service.review(continued, repository_root=repository)

    assert refused.value.current_against == second.review_id, (
        "the repeat visit is told it is already current with the concluded pass"
    )
    # The line still holds exactly the loop that ran: one pass that asked, one that
    # concluded, and nothing appended by coming back to look.
    recorded = workspace.review_repository.list(case_id=case_id)
    assert {item.review_id for item in recorded} == {first.review_id, second.review_id}
    waiting = [
        item
        for item in recorded
        if item.status == ReviewStatus.AWAITING_ANSWERS.value
    ]
    assert [item.review_id for item in waiting] == [first.review_id]


def test_a_repository_nothing_has_run_on_still_opens_a_fresh_case(
    workspace: Runtime, repository: Path
) -> None:
    """Continuity is about carrying on, so with nothing to carry it must not invent one.

    Two cases exist here — one opened and abandoned without being reviewed — and neither is
    continued, because a case nobody ever ran is a conversation that never happened.
    """

    abandoned = workspace.case_service.start_from_repository(repository).case_id

    opened = _started(workspace, repository)

    assert opened != abandoned
    assert workspace.case_repository.get(opened).revision == 1


def test_starting_clean_opens_a_new_case_and_leaves_the_old_one_alone(
    workspace: Runtime, repository: Path
) -> None:
    """The opt-out, over the API the browser calls: a different question about the same code.

    Asserted through HTTP because the flag is the API's promise. The old case is untouched
    and still findable — starting clean adds a conversation, it does not end one.
    """

    root = str(repository)
    with TestClient(create_app(workspace)) as client:
        started = client.post("/api/repositories/start", json={"root_path": root})
        assert started.status_code == 200, started.text
        case_id = started.json()["case_id"]
        review = client.post(
            "/api/reviews", json={"case_id": case_id, "repository_root": root}
        )
        assert review.status_code == 201, review.text

        continued = client.post("/api/repositories/start", json={"root_path": root})
        assert continued.status_code == 200, continued.text
        assert continued.json()["case_id"] == case_id, "continuing is the default"

        clean = client.post(
            "/api/repositories/start", json={"root_path": root, "start_clean": True}
        )

        assert clean.status_code == 200, clean.text
        assert clean.json()["case_id"] != case_id
        assert clean.json()["revision"] == 1
        assert clean.json()["snapshot"]["clarifications"] == []
        listed = {item["case_id"] for item in client.get("/api/cases").json()}
        assert {case_id, clean.json()["case_id"]} <= listed
