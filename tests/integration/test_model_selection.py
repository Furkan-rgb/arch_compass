"""Choosing a reasoning model over the API, including having chosen none."""

from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("fastapi")

from fastapi.testclient import TestClient

from archcompass.adapters.models.catalog import DETERMINISTIC_MODEL
from archcompass.bootstrap import Runtime, build_runtime, pinned_model
from archcompass.domain.errors import ConfigurationError
from archcompass.presentation.web import create_app

#: The two providers these tests want in front of them: one that always answers and one that
#: never will. Ollama is pointed at a closed port rather than mocked, because the row a
#: chooser has to render is the one carrying why a provider did not answer.
_PROVIDERS = "fake,ollama"


@pytest.fixture(autouse=True)
def _enabled_providers(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ARCHCOMPASS_PROVIDERS", _PROVIDERS)
    monkeypatch.setenv("ARCHCOMPASS_OLLAMA_URL", "http://127.0.0.1:1")


def _load_the_example(client: TestClient) -> dict[str, str]:
    """The example as a review request: its repository indexed, and a case about it.

    An example ships no case, so the case is started from the repository the same way one a
    user picked would be.
    """

    loaded = client.post("/api/examples/boundary-review/load")
    assert loaded.status_code == 201, loaded.text
    root = loaded.json()["root_path"]
    started = client.post("/api/repositories/start", json={"root_path": root})
    assert started.status_code == 200, started.text
    return {"case_id": started.json()["case_id"], "repository_root": root}


def _unpinned(tmp_path: Path) -> Runtime:
    """A runtime that has chosen nothing, as a fresh web workspace has.

    Deliberately not the shared `runtime` fixture: that one is handed a pin, which makes the
    model not the workspace's to choose.
    """

    return build_runtime(tmp_path)


def test_a_workspace_that_has_chosen_nothing_still_opens(tmp_path: Path) -> None:
    """The case that used to refuse to boot.

    Everything a review does not need a model for goes on working; the summary reports no
    model rather than the process failing to start, which is what leaves somewhere to fix it.
    """

    runtime = _unpinned(tmp_path)

    with TestClient(create_app(runtime)) as client:
        summary = client.get("/api/workspace")
        assert summary.status_code == 200
        models = summary.json()["models"]
        assert models["reasoning"] is None
        assert models["embedding"] is None
        assert models["pinned"] is False

        # A read that has nothing to do with reasoning is unaffected.
        assert client.get("/api/cases").status_code == 200


def test_a_review_asked_for_without_a_model_is_refused_by_name(tmp_path: Path) -> None:
    """A required field, not an outage: the code says which, and nothing is written.

    The refusal lands before the review row is created, so an unanswerable request leaves
    no half-made record behind for a reader to wonder about.
    """

    runtime = _unpinned(tmp_path)

    with TestClient(create_app(runtime)) as client:
        request = _load_the_example(client)

        refusal = client.post("/api/reviews", json=request)

        assert refusal.status_code == 409, refusal.text
        problem = refusal.json()
        assert problem["code"] == "no_model_selected"
        assert "model chip" in problem["message"]
        failed = client.get("/api/reviews").json()
        assert len(failed) == 1
        assert failed[0]["status"] == "failed"
        assert "NoReasoningModelSelectedError" in failed[0]["failure"]


def test_choosing_a_model_changes_what_the_workspace_reports(tmp_path: Path) -> None:
    runtime = _unpinned(tmp_path)

    with TestClient(create_app(runtime)) as client:
        chosen = client.put(
            "/api/models/selection",
            json={"provider": "fake", "model": DETERMINISTIC_MODEL, "thinking": None},
        )

        assert chosen.status_code == 200, chosen.text
        assert chosen.json()["models"]["reasoning"] == {
            "provider": "fake",
            "model": DETERMINISTIC_MODEL,
            "thinking": None,
        }
        # The response is the whole summary so a page can replace what it is reading.
        assert client.get("/api/workspace").json() == chosen.json()

        client.delete("/api/models/selection")
        assert client.get("/api/workspace").json()["models"]["reasoning"] is None


def test_the_catalog_names_a_provider_that_did_not_answer(tmp_path: Path) -> None:
    """The unreachable row is the useful one, so it is reported rather than omitted."""

    runtime = _unpinned(tmp_path)

    with TestClient(create_app(runtime)) as client:
        catalog = client.get("/api/models")

        assert catalog.status_code == 200, catalog.text
        body = catalog.json()
        by_provider = {item["provider"]: item for item in body["providers"]}
        assert by_provider["fake"]["available"] is True
        unreachable = by_provider["ollama"]
        assert unreachable["available"] is False
        assert "127.0.0.1:1" in unreachable["detail"]
        # An unreachable provider contributes no candidates, which is why the row carrying
        # the reason has to exist separately from them.
        assert [item["model"] for item in body["candidates"]] == [DETERMINISTIC_MODEL]


def test_embedding_catalog_reports_unavailable_local_provider(tmp_path: Path) -> None:
    runtime = _unpinned(tmp_path)

    with TestClient(create_app(runtime)) as client:
        catalog = client.get("/api/embeddings")
        assert catalog.status_code == 200, catalog.text
        assert catalog.json()["providers"][0]["provider"] == "ollama"

        assert catalog.json()["providers"][0]["available"] is False


def test_a_chosen_model_reviews_and_the_review_records_which_one(tmp_path: Path) -> None:
    """The point of the whole change: a choice made here is what the next review runs on."""

    runtime = _unpinned(tmp_path)

    with TestClient(create_app(runtime)) as client:
        request = _load_the_example(client)
        client.put(
            "/api/models/selection",
            json={"provider": "fake", "model": DETERMINISTIC_MODEL},
        )

        review = client.post("/api/reviews", json=request)

        assert review.status_code == 201, review.text
        assert review.json()["model_identity"] == "fake:deterministic-architecture-v4"


def test_a_pinned_run_reports_its_model_and_refuses_to_change_it(tmp_path: Path) -> None:
    """`--provider` and `--model` decided which provider this process costs against."""

    runtime = build_runtime(tmp_path, pin=pinned_model("fake", DETERMINISTIC_MODEL))

    with TestClient(create_app(runtime)) as client:
        models = client.get("/api/workspace").json()["models"]
        assert models["pinned"] is True
        assert models["reasoning"]["provider"] == "fake"

        refused = client.put(
            "/api/models/selection",
            json={"provider": "ollama", "model": "gemma4:26b"},
        )

        assert refused.status_code == 400, refused.text
        assert "--provider" in refused.json()["message"]


def test_a_deployment_offers_only_the_providers_it_names(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A hosted server reaches no local Ollama, and a row saying so reads as a fault.

    Narrowing the registry is how a deployment says a provider is not on offer, which is a
    different statement from one that is on offer and not answering.
    """

    monkeypatch.setenv("ARCHCOMPASS_PROVIDERS", "fake")
    runtime = _unpinned(tmp_path)

    with TestClient(create_app(runtime)) as client:
        body = client.get("/api/models").json()

    assert [item["provider"] for item in body["providers"]] == ["fake"]


def test_a_provider_this_build_cannot_reach_is_refused_by_name(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A typo that silently narrowed the list would present itself as a missing provider."""

    monkeypatch.setenv("ARCHCOMPASS_PROVIDERS", "fake,gemini")

    with pytest.raises(ConfigurationError, match="gemini"):
        build_runtime(tmp_path)
