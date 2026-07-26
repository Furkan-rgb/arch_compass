"""The local HTTP surface: the whole review loop, and the contracts a client relies on."""

from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("fastapi")

from fastapi.testclient import TestClient

from archcompass.bootstrap import Runtime
from archcompass.presentation.web import create_app

FIXTURE = "boundary-review"


def test_the_api_covers_the_whole_review_loop(runtime: Runtime) -> None:
    """Pick an example, review it, read it back, ask about it — in one client session."""

    with TestClient(create_app(runtime)) as client:
        workspace = client.get("/api/workspace")
        assert workspace.status_code == 200
        assert workspace.json()["models"]["reasoning"]["provider"] == "fake"

        examples = client.get("/api/bundled-cases")
        assert examples.status_code == 200
        listed = {item["name"]: item for item in examples.json()}
        assert FIXTURE in listed
        # Only an example that ships answers can be scored; the flag is what the workspace
        # uses to say so, and a client that trusted it wrongly would grade against nothing.
        assert listed[FIXTURE]["has_expected_answers"] is True

        loaded = client.post(f"/api/bundled-cases/{FIXTURE}/load")
        assert loaded.status_code == 201, loaded.text
        case_id = loaded.json()["case_id"]

        created = client.post(
            "/api/reviews",
            json={"case_id": case_id, "repository_root": listed[FIXTURE]["repository_root"]},
        )
        assert created.status_code == 201, created.text
        review = created.json()
        review_id = review["review_id"]
        assert review["status"] == "succeeded"
        assert review["report"]["reviewed"]
        assert review["markdown_report"]

        fetched = client.get(f"/api/reviews/{review_id}")
        assert fetched.status_code == 200
        assert fetched.json()["review_id"] == review_id

        summaries = client.get("/api/reviews")
        assert summaries.status_code == 200
        assert [item["review_id"] for item in summaries.json()] == [review_id]

        conversation = client.post(
            "/api/review-conversations", json={"review_id": review_id}
        )
        assert conversation.status_code == 201, conversation.text
        conversation_id = conversation.json()["conversation_id"]

        answered = client.post(
            f"/api/review-conversations/{conversation_id}/messages",
            json={"question": "What did you make of the TaskFormatter boundary?"},
        )
        assert answered.status_code == 201, answered.text
        message = answered.json()
        assert message["answer"]["answer"]
        known = {item["reference"] for item in review["report"]["reviewed"]}
        # Every citation resolves; references are assigned by the application from
        # position, so an unknown one could only mean the application invented it.
        assert set(message["answer"]["supporting_references"]) <= known

        history = client.get(f"/api/review-conversations/{conversation_id}")
        assert history.status_code == 200
        assert len(history.json()["messages"]) == 1

        scored = client.get(f"/api/reviews/{review_id}/score")
        assert scored.status_code == 200, scored.text
        result = scored.json()
        assert result is not None, "a bundled example that ships answers must be gradable"
        assert result["example"] == FIXTURE
        assert result["total"] == len(review["report"]["reviewed"])
        # Nothing may be silently excluded: an uncovered boundary means the example drifted
        # from its own key, and a score over the remainder would look complete.
        assert result["unscored"] == []
        assert {item["reference"] for item in result["boundaries"]} == known


def test_unknown_identifiers_return_stable_problem_details(runtime: Runtime) -> None:
    """A client distinguishes "not there" from "malformed" by code, not by prose."""

    with TestClient(create_app(runtime)) as client:
        missing = client.get("/api/reviews/rev_missing")
        assert missing.status_code == 404
        body = missing.json()
        assert body["code"]
        assert body["message"]

        malformed = client.post("/api/reviews", json={"case_id": ""})
        assert malformed.status_code == 422

        unknown_route = client.get("/api/not-a-route")
        assert unknown_route.status_code == 404
        assert unknown_route.json()["code"]


def test_a_review_of_an_unindexed_repository_fails_rather_than_reporting_nothing(
    runtime: Runtime,
    tmp_path: Path,
) -> None:
    """Zero boundaries and no atlas would serialise identically. They must not."""

    with TestClient(create_app(runtime)) as client:
        created = client.post("/api/cases", json={
            "title": "Unindexed",
            "problem_statement": "Nothing has been indexed yet.",
            "desired_outcome": "An honest error.",
        })
        assert created.status_code == 201, created.text

        attempted = client.post(
            "/api/reviews",
            json={
                "case_id": created.json()["case_id"],
                "repository_root": str(tmp_path),
            },
        )

        assert attempted.status_code == 404
        assert "repo index" in attempted.json()["message"]


def test_a_review_of_unscored_code_reports_no_score_rather_than_a_made_up_one(
    runtime: Runtime,
) -> None:
    """Someone's own repository has no right answer; inventing one would be worse than none."""

    atlas = runtime.analyzer.analyze(Path("eval/cases/provider-leakage/repository").resolve())
    runtime.atlas_repository.save(atlas)

    with TestClient(create_app(runtime)) as client:
        created = client.post("/api/cases", json={
            "title": "Unscored",
            "problem_statement": "A repository that ships no answer key.",
            "desired_outcome": "An honest absence of a score.",
        })
        review = client.post("/api/reviews", json={
            "case_id": created.json()["case_id"],
            "repository_root": atlas.version.root_path,
        })
        assert review.status_code == 201, review.text

        scored = client.get(f"/api/reviews/{review.json()['review_id']}/score")

        assert scored.status_code == 200
        assert scored.json() is None


def test_the_openapi_contract_declares_the_review_surface(runtime: Runtime) -> None:
    """The generated TypeScript client is derived from this; a gap here is a silent any."""

    with TestClient(create_app(runtime)) as client:
        document = client.get("/api/openapi.json")

    assert document.status_code == 200
    paths = document.json()["paths"]
    for route in (
        "/api/bundled-cases",
        "/api/reviews",
        "/api/reviews/{review_id}",
        "/api/review-conversations",
        "/api/review-conversations/{conversation_id}/messages",
        "/api/reviews/{review_id}/score",
        "/api/repositories/explore",
    ):
        assert route in paths, route

    schemas = document.json()["components"]["schemas"]
    assert "BoundaryReview" in schemas
    assert "ReviewedBoundary" in schemas
    assert "ReviewConversation" in schemas
    # The old consultation surface is gone, not merely unused by the workspace.
    assert not any(path.startswith("/api/consultations") for path in paths)
    assert not any(path.startswith("/api/runs") for path in paths)
