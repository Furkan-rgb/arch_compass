from __future__ import annotations

import threading
import time
from pathlib import Path

from fastapi.testclient import TestClient

from archcompass.bootstrap import Runtime
from archcompass.presentation.web.app import create_app


def _quiet() -> None:
    """Wait for every run thread to stop before the test ends.

    A cancelled run stops at its next stage boundary, so the thread outlives the request
    that cancelled it — and a thread still analysing a repository when the next test starts
    one is two analyses at once, which the type oracle is not built for. This is the test
    waiting for the work it started rather than leaving it to the next test.
    """

    for _ in range(600):
        if not any(
            thread.name.startswith("archcompass-review-") and thread.is_alive()
            for thread in threading.enumerate()
        ):
            return
        time.sleep(0.02)
    raise AssertionError("a review run thread never stopped")


def _settled(client: TestClient, run_id: str) -> dict[str, object]:
    """Poll a run until it stops running, and hand back what it settled as.

    A run is a thread and this is the only honest way to wait for one from outside it.
    The deterministic runtime finishes in well under a second; the ceiling is a failure
    message rather than a timing assumption.
    """

    for _ in range(600):
        run = client.get(f"/api/reviews/runs/{run_id}")
        assert run.status_code == 200, run.text
        state = run.json()
        if state["status"] != "running":
            return state
        time.sleep(0.02)
    raise AssertionError(f"run {run_id} never settled")


def test_a_run_reports_the_graph_stages_it_has_reached(runtime: Runtime) -> None:
    repository = str(Path("examples/cases/warehouse-sync/repository").resolve())
    with TestClient(create_app(runtime)) as client:
        started = client.post("/api/repositories/start", json={"root_path": repository})
        response = client.post(
            "/api/reviews/runs",
            json={
                "case_id": started.json()["case_id"],
                "repository_root": repository,
            },
        )
        assert response.status_code == 202, response.text
        # The run is addressable before it has done anything, which is what makes the page
        # that watches it reloadable.
        assert response.json()["run_id"]
        assert response.json()["started_at"]

        state = _settled(client, response.json()["run_id"])
        assert state["status"] == "awaiting_answers"
        assert "analyze_repository" in state["stages"]
        assert "detect_candidates" in state["stages"]
        assert "generate_questions" in state["stages"]

        waiting = client.get(f"/api/reviews/{state['review_id']}").json()
        assert waiting["status"] == "awaiting_answers"
        cancelled = client.post(f"/api/reviews/{waiting['id']}/cancel")
        assert cancelled.status_code == 200, cancelled.text
        assert cancelled.json()["status"] == "cancelled"
        # Cancelling is how this revision ended, not the revision after it.
        assert cancelled.json()["sequence"] == waiting["sequence"]
        assert cancelled.json()["round"] == waiting["round"]


def test_a_run_is_listed_until_it_is_finished_rather_than_until_it_has_a_review(
    runtime: Runtime,
) -> None:
    """The half of the listing a client could not previously tell apart.

    A run used to leave `/api/reviews/runs` the moment a review id was attached, which is
    several nodes before the end — so the marker vanished, the review was not in the
    reviews listing yet, and a finished run and a run that had never existed produced the
    same answer.
    """

    repository = str(Path("examples/cases/warehouse-sync/repository").resolve())
    with TestClient(create_app(runtime)) as client:
        started = client.post("/api/repositories/start", json={"root_path": repository})
        case_id = started.json()["case_id"]
        run_id = client.post(
            "/api/reviews/runs",
            json={"case_id": case_id, "repository_root": repository},
        ).json()["run_id"]
        waiting_id = _settled(client, run_id)["review_id"]

        # It asked a question, so it is a review now and not a run.
        assert [item["run_id"] for item in client.get("/api/reviews/runs").json()] == []

        answered = client.post(
            f"/api/reviews/{waiting_id}/answers/runs",
            json={"answers": [], "stop": True},
        )
        assert answered.status_code == 202, answered.text
        # The same thread, so one address covers the whole review.
        assert answered.json()["run_id"] == run_id
        assert answered.json()["review_id"] == waiting_id

        completed = _settled(client, run_id)
        assert completed["status"] == "completed"
        assert client.get(f"/api/reviews/{completed['review_id']}").json()["status"] == (
            "completed"
        )
        assert [item["run_id"] for item in client.get("/api/reviews/runs").json()] == []


def test_a_cancelled_run_says_so_rather_than_disappearing(runtime: Runtime) -> None:
    repository = str(Path("examples/cases/warehouse-sync/repository").resolve())
    with TestClient(create_app(runtime)) as client:
        started = client.post("/api/repositories/start", json={"root_path": repository})
        run_id = client.post(
            "/api/reviews/runs",
            json={
                "case_id": started.json()["case_id"],
                "repository_root": repository,
            },
        ).json()["run_id"]

        cancelled = client.post(f"/api/reviews/runs/{run_id}/cancel")
        assert cancelled.status_code == 200, cancelled.text
        assert cancelled.json()["status"] == "cancelled"
        # The id still answers, with the lineage it always had. A run that vanished would
        # leave whoever pressed the button unable to tell that it had.
        again = client.get(f"/api/reviews/runs/{run_id}")
        assert again.status_code == 200, again.text
        assert again.json()["status"] == "cancelled"
        assert again.json()["run_id"] == run_id
        assert [item["run_id"] for item in client.get("/api/reviews/runs").json()] == []
        _quiet()


def test_clean_break_api_resumes_the_same_graph_without_elicited_from(
    runtime: Runtime,
) -> None:
    repository = str(Path("examples/cases/warehouse-sync/repository").resolve())
    with TestClient(create_app(runtime)) as client:
        started = client.post("/api/repositories/start", json={"root_path": repository})
        assert started.status_code == 200, started.text

        first = client.post(
            "/api/reviews",
            json={
                "case_id": started.json()["case_id"],
                "repository_root": repository,
            },
        )
        assert first.status_code == 201, first.text
        waiting = first.json()
        assert waiting["status"] == "awaiting_answers"
        assert waiting["questions"]
        assert waiting["retrieval_manifest"]
        assert "elicited_from" not in waiting

        resumed = client.post(
            f"/api/reviews/{waiting['id']}/answers",
            json={"answers": [], "stop": True},
        )
        assert resumed.status_code == 200, resumed.text
        completed = resumed.json()
        assert completed["status"] == "completed"
        # One review, one revision: answering the questions finished the revision that
        # asked them rather than starting the next one, and the case revision it was
        # judged against is the one this review opened and kept.
        assert completed["sequence"] == waiting["sequence"]
        assert completed["previous_review_id"] == waiting["previous_review_id"]
        assert completed["round"] == waiting["round"] + 1
        assert completed["case"]["revision"] == waiting["case"]["revision"] + 1
        assert all(answer["status"] == "skipped" for answer in completed["case"]["answers"])

        # A superseded waiting snapshot stays readable under the id somebody was already
        # holding. What it no longer does is appear in a listing as a revision of its own.
        assert client.get(f"/api/reviews/{waiting['id']}").json()["status"] == (
            "awaiting_answers"
        )

        candidate_id = completed["findings"][0]["candidate"]["id"]
        invalid_waiver = client.post(
            "/api/decisions",
            json={
                "review_id": completed["id"],
                "candidate_id": candidate_id,
                "disposition": "waive",
                "author": "architect",
            },
        )
        assert invalid_waiver.status_code == 422
        decision = client.post(
            "/api/decisions",
            json={
                "review_id": completed["id"],
                "candidate_id": candidate_id,
                "disposition": "accept",
                "author": "architect",
                "reasoning": "This boundary is intentional.",
            },
        )
        assert decision.status_code == 201, decision.text
        stored_decision = decision.json()
        assert stored_decision["finding_verdict"] == completed["findings"][0]["verdict"]
        branch_id = completed["repository"]["branch_id"]
        standings = client.get(f"/api/branches/{branch_id}/decisions")
        assert standings.json()["decisions"] == [stored_decision]
        history = client.get(
            f"/api/decisions/{branch_id}/{candidate_id}/history"
        )
        assert history.json() == [stored_decision]

        conversation = client.post(
            "/api/review-conversations", json={"review_id": completed["id"]}
        )
        assert conversation.status_code == 201, conversation.text
        conversation_id = conversation.json()["id"]
        answered = client.post(
            f"/api/review-conversations/{conversation_id}/messages",
            json={"question": "What supports the first finding?"},
        )
        assert answered.status_code == 200, answered.text
        assert answered.json()["messages"][-1]["answer"][
            "supporting_candidate_ids"
        ] == [candidate_id]

        duplicate = client.post(
            f"/api/reviews/{waiting['id']}/answers",
            json={"answers": [], "stop": True},
        )
        assert duplicate.json()["id"] == completed["id"]

        listing = client.get("/api/reviews")
        assert listing.status_code == 200
        assert {item["id"] for item in listing.json()} == {completed["id"]}
        # The document a review is read as is not on the review. Twenty kilobytes of
        # Markdown on every row of every listing, for one tab that fetches it by name.
        assert "markdown_report" not in listing.json()[0]
        assert client.get(f"/api/reviews/{completed['id']}/report").status_code == 200

        summaries = client.get("/api/reviews", params={"view": "summary"})
        assert summaries.status_code == 200, summaries.text
        summary = summaries.json()[0]
        assert summary["id"] == completed["id"]
        assert summary["sequence"] == completed["sequence"]
        assert summary["repository"] == completed["repository"]
        assert summary["case_revision"] == completed["case"]["revision"]
        assert summary["started_at"] == completed["started_at"]
        assert summary["finished_at"] == completed["finished_at"]
        assert summary["finding_count"] == len(completed["findings"])
        assert summary["new_count"] == len(completed["delta"]["new"])
        # Counts, not collections: that is the whole of what the view is for.
        assert "findings" not in summary
        assert "atlas" not in summary

        obsolete = client.post(
            "/api/reviews",
            json={
                "case_id": started.json()["case_id"],
                "repository_root": repository,
                "elicited_from": waiting["id"],
            },
        )
        assert obsolete.status_code == 422


def test_a_run_carries_the_folders_it_was_started_without(runtime: Runtime) -> None:
    """The run says what it left out, so what started it can be offered again.

    "Start again" after a failed run carried `?root=` and nothing else, because nothing on
    the wire recorded which folders the run had skipped. The repository came back and the
    scope did not, so the reader re-ticked by hand a choice that was on screen twenty lines
    above — and a rerun made with a different scope is a review of a different question.

    Sorted rather than echoed back as it was sent, because that is what the workspace
    recorded: one scope typed two ways is one scope, and a client comparing the two spellings
    would find a difference the analysis does not have.
    """

    repository = str(Path("examples/cases/warehouse-sync/repository").resolve())
    with TestClient(create_app(runtime)) as client:
        started = client.post(
            "/api/repositories/start",
            json={"root_path": repository, "excluded_paths": ["tests", "reporting"]},
        )
        assert started.status_code == 200, started.text

        run = client.post(
            "/api/reviews/runs",
            json={
                "case_id": started.json()["case_id"],
                "repository_root": repository,
            },
        )
        assert run.status_code == 202, run.text
        assert run.json()["excluded_paths"] == ["reporting", "tests"]

        # And on every later read of the same run, because the page that offers to start
        # again is reading a run it did not start.
        run_id = run.json()["run_id"]
        cancelled = client.post(f"/api/reviews/runs/{run_id}/cancel")
        assert cancelled.json()["excluded_paths"] == ["reporting", "tests"]
        assert client.get(f"/api/reviews/runs/{run_id}").json()["excluded_paths"] == [
            "reporting",
            "tests",
        ]
        _quiet()
