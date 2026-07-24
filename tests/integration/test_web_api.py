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
        removed_follow_up = client.post(
            f"/api/runs/{run_id}/follow-ups",
            json={"question": "What findings support the result?"},
        )
        conversation = client.post(
            "/api/conversations",
            json={"run_id": run_id},
        )

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
        assert structured.json()["schema_version"] == 3
        assert structured.json()["findings"][0]["finding_id"] == "FIND-001"
        assert removed_follow_up.status_code == 404
        assert conversation.status_code == 201, conversation.text
        conversation_id = conversation.json()["conversation_id"]
        answer = client.post(
            f"/api/conversations/{conversation_id}/messages",
            json={"question": "What findings support the result?"},
        )
        history = client.get(f"/api/conversations/{conversation_id}/history")
        conversation_markdown = client.get(
            f"/api/conversations/{conversation_id}/export",
            params={"format": "markdown"},
        )
        conversation_json = client.get(
            f"/api/conversations/{conversation_id}/export",
            params={"format": "json"},
        )
        assert answer.status_code == 201, answer.text
        assert answer.json()["role"] == "assistant"
        assert answer.json()["answer"]["relevant_finding_ids"]
        assert history.status_code == 200
        assert [item["role"] for item in history.json()] == ["user", "assistant"]
        assert conversation_markdown.status_code == 200
        assert conversation_markdown.headers["content-type"].startswith("text/markdown")
        assert f"Consultation run: `{run_id}`" in conversation_markdown.text
        assert conversation_json.status_code == 200
        assert conversation_json.headers["content-type"].startswith("application/json")
        assert (
            conversation_json.json()["conversation"]["conversation_id"]
            == conversation_id
        )


def test_web_api_returns_stable_problem_details(runtime: Runtime) -> None:
    with TestClient(create_app(runtime)) as client:
        response = client.get("/api/cases/not-a-case")
        invalid = client.post(
            "/api/conversations/not-a-conversation/messages",
            json={"question": ""},
        )

    assert response.status_code == 404
    assert response.json() == {
        "code": "not_found",
        "message": "Architecture case not-a-case was not found",
        "retryable": False,
        "field_errors": [],
    }
    assert invalid.status_code == 422
    assert invalid.json()["code"] == "validation_error"
    assert invalid.json()["field_errors"]


def test_web_api_maps_missing_consultation_runs_to_not_found(
    runtime: Runtime,
) -> None:
    with TestClient(create_app(runtime)) as client:
        shown = client.get("/api/runs/not-a-run")
        created = client.post(
            "/api/conversations",
            json={"run_id": "not-a-run"},
        )
        listed = client.get(
            "/api/conversations",
            params={"run_id": "not-a-run"},
        )

    for response in (shown, created, listed):
        assert response.status_code == 404
        assert response.json()["code"] == "not_found"
        assert response.json()["retryable"] is False


def test_web_openapi_declares_problem_and_export_contracts(
    runtime: Runtime,
) -> None:
    schema = create_app(runtime).openapi()
    paths = schema["paths"]

    assert "ProblemDetail" in schema["components"]["schemas"]
    assert "HTTPValidationError" not in schema["components"]["schemas"]
    expected_problem_reference = {"$ref": "#/components/schemas/ProblemDetail"}
    for path_item in paths.values():
        for operation in path_item.values():
            response = operation["responses"].get("422")
            if response is not None:
                assert (
                    response["content"]["application/json"]["schema"]
                    == expected_problem_reference
                )
    conversation_operations = (
        paths["/api/conversations"]["post"],
        paths["/api/conversations"]["get"],
        paths["/api/conversations/{conversation_id}"]["get"],
        paths["/api/conversations/{conversation_id}/history"]["get"],
        paths["/api/conversations/{conversation_id}/messages"]["post"],
        paths["/api/conversations/{conversation_id}/export"]["get"],
    )
    for operation in conversation_operations:
        assert set(operation["responses"]) >= {"404", "422"}
        for status in ("404", "422"):
            assert (
                operation["responses"][status]["content"]["application/json"]["schema"]
                == expected_problem_reference
            )

    ask_responses = paths["/api/conversations/{conversation_id}/messages"]["post"][
        "responses"
    ]
    assert set(ask_responses) >= {"201", "404", "409", "422", "503"}
    for status in ("404", "409", "422", "503"):
        assert (
            ask_responses[status]["content"]["application/json"]["schema"]
            == expected_problem_reference
        )

    for path in (
        "/api/runs/{run_id}/report",
        "/api/conversations/{conversation_id}/export",
    ):
        content = paths[path]["get"]["responses"]["200"]["content"]
        assert set(content) >= {"application/json", "text/markdown"}
        assert content["application/json"]["schema"]
        assert content["text/markdown"]["schema"] == {"type": "string"}


def test_web_api_explores_repository_atlas_progressively(runtime: Runtime) -> None:
    repository = Path("eval/cases/provider-leakage/repository").resolve()

    with TestClient(create_app(runtime)) as client:
        indexed = client.post(
            "/api/repositories/index", json={"root_path": str(repository)}
        )
        assert indexed.status_code == 201, indexed.text

        summary = client.get(
            "/api/repositories/summary", params={"root_path": str(repository)}
        )
        assert summary.status_code == 200, summary.text
        root = next(
            node
            for node in summary.json()["node_summaries"]
            if node["node_type"] == "repository"
        )

        children = client.post(
            "/api/repositories/explore",
            json={
                "root_path": str(repository),
                "operation": "children",
                "node_id": root["node_id"],
            },
        )
        searched = client.post(
            "/api/repositories/explore",
            json={
                "root_path": str(repository),
                "operation": "search",
                "terms": ["provider"],
            },
        )
        signals = client.post(
            "/api/repositories/explore",
            json={
                "root_path": str(repository),
                "operation": "signals",
            },
        )
        invalid = client.post(
            "/api/repositories/explore",
            json={"root_path": str(repository), "operation": "shortest_path"},
        )

    assert children.status_code == 200, children.text
    assert children.json()["node_summaries"]
    assert any(
        edge["edge_type"] == "contains"
        for edge in children.json()["relationships"]
    )
    assert searched.status_code == 200, searched.text
    assert any(
        "provider" in node["qualified_name"].lower()
        for node in searched.json()["node_summaries"]
    )
    assert signals.status_code == 200, signals.text
    assert signals.json()["signals"]
    assert signals.json()["node_summaries"]
    assert invalid.status_code == 422
