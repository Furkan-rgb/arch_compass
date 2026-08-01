"""Choosing a reasoning model over the API, including having chosen none."""

from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("fastapi")

from fastapi.testclient import TestClient

from archcompass.bootstrap import Runtime, build_runtime
from archcompass.presentation.web import create_app

_FAKE = """models:
  reasoning:
    provider: fake
    model: deterministic-architecture-v1
    base_url: http://127.0.0.1:11434
    timeout_seconds: 1
"""

_UNREACHABLE_OLLAMA = """models:
  reasoning:
    provider: ollama
    model: gemma4:26b
    base_url: http://127.0.0.1:1
    timeout_seconds: 1
"""


def _workspace(tmp_path: Path, **files: str) -> Path:
    directory = tmp_path / "config"
    directory.mkdir(parents=True, exist_ok=True)
    for name, text in files.items():
        (directory / name.replace("__", ".")).write_text(text, encoding="utf-8")
    return tmp_path


def _review_request(client: TestClient) -> dict[str, str]:
    """The loaded example, as a review request. Its repository ships beside the case."""

    example = next(
        item
        for item in client.get("/api/bundled-cases").json()
        if item["name"] == "boundary-review"
    )
    case_id = client.get("/api/cases").json()[0]["case_id"]
    return {"case_id": case_id, "repository_root": example["repository_root"]}


def _unpinned(tmp_path: Path, **files: str) -> Runtime:
    """A runtime that found its own configuration, as the web workspace does.

    Deliberately not the shared `runtime` fixture: that one is handed an explicit
    `models_config`, which pins the run and makes the model not the workspace's to choose.
    """

    return build_runtime(_workspace(tmp_path, **files))


def test_a_workspace_with_two_configurations_and_no_choice_still_opens(
    tmp_path: Path,
) -> None:
    """The case that used to refuse to boot. It is this repository's own `config/`.

    Everything a review does not need a model for goes on working; the summary reports no
    model rather than the process failing to start, which is what leaves somewhere to fix it.
    """

    runtime = _unpinned(
        tmp_path, models__ollama__yaml=_UNREACHABLE_OLLAMA, models__fake__yaml=_FAKE
    )

    with TestClient(create_app(runtime)) as client:
        summary = client.get("/api/workspace")
        assert summary.status_code == 200
        models = summary.json()["models"]
        assert models["reasoning"] is None
        assert models["pinned"] is False
        assert models["from_configuration"] is False

        # A read that has nothing to do with reasoning is unaffected.
        assert client.get("/api/cases").status_code == 200


def test_a_review_asked_for_without_a_model_is_refused_by_name(tmp_path: Path) -> None:
    """A required field, not an outage: the code says which, and nothing is written.

    The refusal lands before the review row is created, so an unanswerable request leaves
    no half-made record behind for a reader to wonder about.
    """

    runtime = _unpinned(
        tmp_path, models__ollama__yaml=_UNREACHABLE_OLLAMA, models__fake__yaml=_FAKE
    )

    with TestClient(create_app(runtime)) as client:
        loaded = client.post("/api/bundled-cases/boundary-review/load")
        assert loaded.status_code == 201, loaded.text

        refusal = client.post("/api/reviews", json=_review_request(client))

        assert refusal.status_code == 409, refusal.text
        problem = refusal.json()
        assert problem["code"] == "no_model_selected"
        assert "model chip" in problem["message"]
        assert client.get("/api/reviews").json() == []


def test_choosing_a_model_changes_what_the_workspace_reports(tmp_path: Path) -> None:
    runtime = _unpinned(
        tmp_path, models__ollama__yaml=_UNREACHABLE_OLLAMA, models__fake__yaml=_FAKE
    )

    with TestClient(create_app(runtime)) as client:
        chosen = client.put(
            "/api/models/selection",
            json={"profile_id": "models.fake.yaml", "model": "deterministic-architecture-v4"},
        )

        assert chosen.status_code == 200, chosen.text
        assert chosen.json()["models"]["reasoning"] == {
            "provider": "fake",
            "model": "deterministic-architecture-v4",
        }
        # The response is the whole summary so a page can replace what it is reading.
        assert client.get("/api/workspace").json() == chosen.json()

        client.delete("/api/models/selection")
        assert client.get("/api/workspace").json()["models"]["reasoning"] is None


def test_the_catalog_names_a_provider_that_did_not_answer(tmp_path: Path) -> None:
    """The unreachable row is the useful one, so it is reported rather than omitted."""

    runtime = _unpinned(
        tmp_path, models__ollama__yaml=_UNREACHABLE_OLLAMA, models__fake__yaml=_FAKE
    )

    with TestClient(create_app(runtime)) as client:
        catalog = client.get("/api/models")

        assert catalog.status_code == 200, catalog.text
        body = catalog.json()
        by_profile = {item["profile_id"]: item for item in body["providers"]}
        assert by_profile["models.fake.yaml"]["available"] is True
        unreachable = by_profile["models.ollama.yaml"]
        assert unreachable["available"] is False
        assert "127.0.0.1:1" in unreachable["detail"]
        # An unreachable provider contributes no candidates, which is why the row carrying
        # the reason has to exist separately from them.
        assert [item["model"] for item in body["candidates"]] == [
            "deterministic-architecture-v4"
        ]


def test_a_chosen_model_reviews_and_the_review_records_which_one(tmp_path: Path) -> None:
    """The point of the whole change: a choice made here is what the next review runs on."""

    runtime = _unpinned(
        tmp_path, models__ollama__yaml=_UNREACHABLE_OLLAMA, models__fake__yaml=_FAKE
    )

    with TestClient(create_app(runtime)) as client:
        client.post("/api/bundled-cases/boundary-review/load")
        request = _review_request(client)
        client.put(
            "/api/models/selection",
            json={"profile_id": "models.fake.yaml", "model": "deterministic-architecture-v4"},
        )

        review = client.post("/api/reviews", json=request)

        assert review.status_code == 201, review.text
        assert review.json()["reasoning_model"] == "fake:deterministic-architecture-v4"


def test_a_pinned_run_reports_its_configuration_and_refuses_to_change_it(
    tmp_path: Path,
) -> None:
    """`--models-config` decided which provider this process costs against."""

    workspace = _workspace(
        tmp_path, models__fake__yaml=_FAKE, models__ollama__yaml=_UNREACHABLE_OLLAMA
    )
    runtime = build_runtime(workspace, models_config=workspace / "config" / "models.fake.yaml")

    with TestClient(create_app(runtime)) as client:
        models = client.get("/api/workspace").json()["models"]
        assert models["pinned"] is True
        assert models["reasoning"]["provider"] == "fake"

        refused = client.put(
            "/api/models/selection",
            json={"profile_id": "models.ollama.yaml", "model": "gemma4:26b"},
        )

        assert refused.status_code == 400, refused.text
        assert "--models-config" in refused.json()["message"]
