from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient

from archcompass.bootstrap import Runtime
from archcompass.presentation.web.app import create_app


def test_clean_break_stream_exposes_graph_stages(runtime: Runtime) -> None:
    repository = str(Path("eval/cases/warehouse-sync/repository").resolve())
    with TestClient(create_app(runtime)) as client:
        started = client.post("/api/repositories/start", json={"root_path": repository})
        response = client.post(
            "/api/reviews/stream",
            json={
                "case_id": started.json()["case_id"],
                "repository_root": repository,
            },
        )
        assert response.status_code == 200
        events = [json.loads(line) for line in response.text.splitlines()]
        stages = [item["event"] for item in events]
        assert "analyze_repository" in stages
        assert "detect_candidates" in stages
        assert "generate_questions" in stages
        assert events[-1]["event"] == "awaiting_answers"
        assert events[-1]["review"]["status"] == "awaiting_answers"
        waiting = events[-1]["review"]
        cancelled = client.post(f"/api/reviews/{waiting['id']}/cancel")
        assert cancelled.status_code == 200, cancelled.text
        assert cancelled.json()["status"] == "cancelled"
        assert cancelled.json()["sequence"] == waiting["sequence"] + 1


def test_clean_break_api_resumes_the_same_graph_without_elicited_from(
    runtime: Runtime,
) -> None:
    repository = str(Path("eval/cases/warehouse-sync/repository").resolve())
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
        assert completed["previous_review_id"] == waiting["id"]
        assert all(answer["status"] == "skipped" for answer in completed["case"]["answers"])

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
        assert {item["id"] for item in listing.json()} >= {waiting["id"], completed["id"]}

        obsolete = client.post(
            "/api/reviews",
            json={
                "case_id": started.json()["case_id"],
                "repository_root": repository,
                "elicited_from": waiting["id"],
            },
        )
        assert obsolete.status_code == 422
