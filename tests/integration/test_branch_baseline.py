"""Run two is quieter than run one, and only because someone said so.

Against the real HTTP surface and a real database, because the claim is about a loop rather
than about a function: a run, an act of adoption, and a second run that reads differently
without anything in the repository having changed. The deterministic substitute judges, so
the verdicts are stable by construction — what is asserted is the partition, not the
judgement.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, cast

import pytest

pytest.importorskip("fastapi")

from fastapi.testclient import TestClient

from archcompass.bootstrap import Runtime
from archcompass.domain.case import ArchitectureCase, RepositoryReference
from archcompass.domain.errors import ReviewHasNoBranchError
from archcompass.domain.review import BoundaryReview, ReviewStatus
from archcompass.presentation.web import create_app

EXAMPLE = "boundary-review"
UNSTAMPED_FIXTURE = Path("eval/cases/speech-vendor/repository").resolve()


@pytest.fixture
def client(runtime: Runtime) -> TestClient:
    return TestClient(create_app(runtime))


def _reviewed(client: TestClient) -> tuple[str, str]:
    """An indexed example and a case about it, ready to be reviewed more than once."""

    loaded = client.post(f"/api/examples/{EXAMPLE}/load")
    assert loaded.status_code == 201, loaded.text
    root = cast("str", loaded.json()["root_path"])
    started = client.post("/api/repositories/start", json={"root_path": root})
    assert started.status_code == 200, started.text
    return cast("str", started.json()["case_id"]), root


def _run(client: TestClient, case_id: str, root: str) -> str:
    response = client.post(
        "/api/reviews", json={"case_id": case_id, "repository_root": root}
    )
    assert response.status_code == 201, response.text
    return cast("str", response.json()["review_id"])


def _detail(client: TestClient, review_id: str) -> dict[str, Any]:
    response = client.get(f"/api/reviews/{review_id}")
    assert response.status_code == 200, response.text
    return cast("dict[str, Any]", response.json())


def _dispositions(detail: dict[str, Any]) -> list[str | None]:
    report = cast("dict[str, Any]", detail["report"])
    return [
        cast("str | None", boundary["disposition"])
        for boundary in cast("list[dict[str, Any]]", report["reviewed"])
    ]


def _atlas_version_id(runtime: Runtime, root: str) -> str:
    atlas = runtime.atlas_repository.latest_for_path(Path(root))
    assert atlas is not None
    return atlas.version.version_id


def test_baselining_a_review_makes_the_next_run_report_every_boundary_as_known(
    client: TestClient,
) -> None:
    case_id, root = _reviewed(client)
    first = _run(client, case_id, root)

    before = _detail(client, first)
    boundaries = len(_dispositions(before))
    assert boundaries > 0, "the example is here to produce boundaries"
    assert _dispositions(before) == ["new"] * boundaries
    assert before["baseline_summary"] == {
        "new": boundaries,
        "changed": 0,
        "known": 0,
    }

    adopted = client.post(f"/api/reviews/{first}/baseline")
    assert adopted.status_code == 201, adopted.text
    assert adopted.json()["entries_written"] == boundaries
    assert adopted.json()["baseline_size"] == boundaries
    assert adopted.json()["boundaries_without_fingerprint"] == 0

    # Nothing about the repository changed, so the second run finds the same structures —
    # and every one of them is now something this branch has already looked at.
    second = _run(client, case_id, root)
    after = _detail(client, second)
    assert _dispositions(after) == ["known"] * boundaries
    assert after["baseline_summary"] == {"new": 0, "changed": 0, "known": boundaries}

    # The review that was baselined reads the same way, because the comparison is made when
    # the review is read rather than stored on it.
    assert _dispositions(_detail(client, first)) == ["known"] * boundaries


def test_removing_one_entry_surfaces_that_boundary_and_nothing_else(
    client: TestClient,
) -> None:
    case_id, root = _reviewed(client)
    review_id = _run(client, case_id, root)
    assert client.post(f"/api/reviews/{review_id}/baseline").status_code == 201

    detail = _detail(client, review_id)
    branch_id = cast("str", detail["branch_id"])
    report = cast("dict[str, Any]", detail["report"])
    boundaries = cast("list[dict[str, Any]]", report["reviewed"])
    released = cast("str", boundaries[0]["fingerprint"])

    listing = client.get(f"/api/branches/{branch_id}/baseline")
    assert listing.status_code == 200, listing.text
    assert listing.json()["count"] == len(boundaries)
    assert released in {
        entry["boundary_fingerprint"] for entry in listing.json()["entries"]
    }

    removed = client.delete(f"/api/branches/{branch_id}/baseline/{released}")
    assert removed.status_code == 204, removed.text

    after = _detail(client, review_id)
    assert _dispositions(after) == ["new"] + ["known"] * (len(boundaries) - 1)
    assert after["baseline_summary"] == {
        "new": 1,
        "changed": 0,
        "known": len(boundaries) - 1,
    }

    # The ratchet is released once. Asking again is a mistake worth reporting, not a
    # second success.
    assert client.delete(f"/api/branches/{branch_id}/baseline/{released}").status_code == 404


def test_baselining_the_same_review_twice_updates_rather_than_accumulates(
    client: TestClient,
) -> None:
    """The button is safe to press twice, and pressing it twice changes no count."""

    case_id, root = _reviewed(client)
    review_id = _run(client, case_id, root)

    first = client.post(f"/api/reviews/{review_id}/baseline")
    second = client.post(f"/api/reviews/{review_id}/baseline")
    assert first.status_code == 201
    assert second.status_code == 201
    assert second.json() == first.json()

    branch_id = cast("str", _detail(client, review_id)["branch_id"])
    listing = client.get(f"/api/branches/{branch_id}/baseline")
    assert listing.json()["count"] == first.json()["baseline_size"]


def test_a_branch_nobody_has_baselined_answers_with_an_empty_baseline(
    client: TestClient,
) -> None:
    listing = client.get("/api/branches/branch_never_seen/baseline")

    assert listing.status_code == 200, listing.text
    assert listing.json() == {
        "branch_id": "branch_never_seen",
        "entries": [],
        "count": 0,
    }


def test_a_review_with_no_branch_lineage_is_refused_and_named_the_cure(
    runtime: Runtime, client: TestClient
) -> None:
    """An atlas stored without a lineage, which is what every pre-lineage workspace holds.

    Saved through the repository rather than indexed through the service, because indexing
    is exactly the step that stamps the lineage — the state under test is a workspace that
    has not taken it.
    """

    runtime.atlas_repository.save(runtime.analyzer.analyze(UNSTAMPED_FIXTURE))
    revision = runtime.case_repository.create(
        ArchitectureCase(
            title="Provider variation",
            problem_statement="Decide where provider-specific knowledge should live.",
            desired_outcome="One owner for provider differences.",
            expected_future_changes=["A hosted provider may be added later"],
            repository=RepositoryReference(root_path=str(UNSTAMPED_FIXTURE)),
        ),
        actor="test",
    )
    review = runtime.review_service.review(
        revision.case_id, repository_root=UNSTAMPED_FIXTURE
    )
    assert review.status is ReviewStatus.SUCCEEDED
    assert review.branch_id is None

    refused = client.post(f"/api/reviews/{review.review_id}/baseline")

    assert refused.status_code == 409, refused.text
    assert refused.json()["code"] == "state_conflict"
    assert "Re-index the repository" in refused.json()["message"]

    # And the same refusal reaches an in-process caller as its own error type.
    with pytest.raises(ReviewHasNoBranchError):
        runtime.baseline_service.baseline_review(review.review_id)

    # A review that cannot be baselined is still readable, and says nothing rather than
    # claiming every boundary is new.
    detail = _detail(client, review.review_id)
    assert detail["baseline_summary"] is None
    assert set(_dispositions(detail)) == {None}


def test_a_review_that_reached_no_verdicts_cannot_be_baselined(
    runtime: Runtime, client: TestClient
) -> None:
    """A run that is still going, which is the state someone can actually click through to.

    Written straight to the repository because that is what a run in flight looks like on
    disk: a row with a status and no report. There is nothing in it to declare seen.
    """

    case_id, root = _reviewed(client)
    running = BoundaryReview(
        status=ReviewStatus.RUNNING,
        case_id=case_id,
        case_revision=1,
        atlas_version_id=_atlas_version_id(runtime, root),
        reasoning_model="fake:fake-answerer",
        prompt_identity="judge-finding-candidate:v1:abcdef123456",
    )
    runtime.review_repository.begin(running)

    refused = client.post(f"/api/reviews/{running.review_id}/baseline")

    assert refused.status_code == 409, refused.text
    assert "no verdicts" in refused.json()["message"]
