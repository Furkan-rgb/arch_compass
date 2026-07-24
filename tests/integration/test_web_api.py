from __future__ import annotations

from pathlib import Path
from time import monotonic, sleep

import pytest
import yaml

pytest.importorskip("fastapi")

from fastapi.testclient import TestClient

from archcompass.bootstrap import Runtime
from archcompass.presentation.web import create_app


def test_web_api_covers_local_case_consultation_and_report(runtime: Runtime) -> None:
    source = yaml.safe_load(
        Path("eval/cases/audiobook-greenfield/case.yaml").read_text(encoding="utf-8")
    )

    with TestClient(create_app(runtime)) as client:
        workspace = client.get("/api/workspace")
        policies = client.get("/api/policies")
        created = client.post("/api/cases", json=source)

        assert workspace.status_code == 200
        assert workspace.json()["models"]["reasoning"]["provider"] == "fake"
        assert policies.status_code == 200
        assert any(item["id"] == "contain-dependencies" for item in policies.json())
        assert created.status_code == 201, created.text

        case_id = created.json()["case_id"]
        started = client.post(
            "/api/consultations",
            json={"case_id": case_id, "repository_root": None},
        )
        assert started.status_code == 202, started.text
        run_id = started.json()["run_id"]

        deadline = monotonic() + 10
        status = "queued"
        while status in {"queued", "running"} and monotonic() < deadline:
            response = client.get(f"/api/consultations/{run_id}")
            assert response.status_code == 200
            status = response.json()["status"]
            if status in {"queued", "running"}:
                sleep(0.01)

        assert status == "succeeded"
        events = client.get(f"/api/consultations/{run_id}/events")
        run = client.get(f"/api/runs/{run_id}")
        markdown = client.get(f"/api/runs/{run_id}/report?format=markdown")
        structured = client.get(f"/api/runs/{run_id}/report?format=json")

        assert events.status_code == 200
        assert any(
            item["event_type"] == "artifact_available"
            and item["stage"] == "design_forces"
            for item in events.json()
        )
        assert events.json()[-1]["event_type"] == "completed"
        assert run.status_code == 200
        assert run.json()["report"]["disposition"] == "move_responsibility"
        assert markdown.status_code == 200
        assert "Decision summary" in markdown.text
        assert structured.status_code == 200
        assert structured.json()["schema_version"] == 2


def test_web_api_returns_stable_problem_details(runtime: Runtime) -> None:
    with TestClient(create_app(runtime)) as client:
        response = client.get("/api/cases/not-a-case")

    assert response.status_code == 404
    assert response.json() == {
        "code": "not_found",
        "message": "Architecture case not-a-case was not found",
        "retryable": False,
        "field_errors": [],
    }
