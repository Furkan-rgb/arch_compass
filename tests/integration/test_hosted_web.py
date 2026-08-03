"""The hosted demo: a workspace per visitor, three refusals, and a daily budget."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

pytest.importorskip("fastapi")

from fastapi.testclient import TestClient

from archcompass.adapters.models.deterministic import DETERMINISTIC_MODEL
from archcompass.bootstrap import Runtime
from archcompass.presentation.web import create_app
from archcompass.presentation.web.hosted import create_hosted_app
from archcompass.presentation.web.runtimes import SESSION_COOKIE

FIXTURE = "boundary-review"

#: The cookie is issued `Secure`, so a client driving the app over plain http would be given
#: one and never send it back. Https here is what a deployment actually serves.
HOSTED_URL = "https://testserver"

#: The nine headings `parse_policy` requires. A policy written on the hosted demo goes
#: through the same parser as every other one; what is being checked is that it is allowed
#: at all, so the sections carry the least text that satisfies it.
_POLICY_BODY = "\n".join(
    f"## {heading}\nWhat this policy says about {heading.lower()}."
    for heading in (
        "Intent",
        "Guidance",
        "Signals",
        "Diagnostic questions",
        "Likely consequences",
        "Exceptions",
        "Positive example",
        "Counterexample",
        "Related policies",
    )
)


@pytest.fixture
def hosted_environment(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.setenv("ARCHCOMPASS_HOSTED", "1")
    # The deterministic substitute, so nothing here reaches a network. It also keeps the
    # startup check quiet about GOOGLE_API_KEY, which is its own test below.
    monkeypatch.setenv("ARCHCOMPASS_PROVIDERS", "fake")
    monkeypatch.setenv("ARCHCOMPASS_SESSION_ROOT", str(tmp_path / "sessions"))
    yield


def _client() -> TestClient:
    return TestClient(create_hosted_app(), base_url=HOSTED_URL)


def _choose_the_deterministic_model(client: TestClient) -> None:
    chosen = client.put(
        "/api/models/selection",
        json={"provider": "fake", "model": DETERMINISTIC_MODEL, "thinking": None},
    )
    assert chosen.status_code == 200, chosen.text


@pytest.mark.usefixtures("hosted_environment")
def test_a_first_visit_is_given_a_session_and_says_it_is_hosted() -> None:
    with _client() as client:
        summary = client.get("/api/workspace")

        assert summary.status_code == 200
        assert summary.json()["hosted"] is True
        # The workspace directory is named after the session token, and the token is in an
        # HttpOnly cookie precisely so no page can read it.
        assert "sessions" not in summary.json()["workspace"]
        cookie = summary.cookies[SESSION_COOKIE]
        assert len(cookie) >= 16
        header = summary.headers["set-cookie"]
        assert "HttpOnly" in header
        assert "SameSite=Lax" in header
        assert "Secure" in header


@pytest.mark.usefixtures("hosted_environment")
def test_two_visitors_share_nothing() -> None:
    with _client() as mine, _client() as theirs:
        _choose_the_deterministic_model(mine)
        loaded = mine.post(f"/api/examples/{FIXTURE}/load")
        assert loaded.status_code == 201, loaded.text
        started = mine.post(
            "/api/repositories/start", json={"root_path": loaded.json()["root_path"]}
        )
        assert started.status_code == 201, started.text

        assert [item["case_id"] for item in mine.get("/api/cases").json()] == [
            started.json()["case_id"]
        ]
        assert theirs.get("/api/cases").json() == []
        assert theirs.get("/api/workspace").json()["models"]["reasoning"] is None
        assert mine.cookies[SESSION_COOKIE] != theirs.cookies[SESSION_COOKIE]


@pytest.mark.usefixtures("hosted_environment")
def test_the_hosted_demo_refuses_to_show_the_server_it_runs_on() -> None:
    with _client() as client:
        browsed = client.get("/api/filesystem/directories")

        assert browsed.status_code == 403
        assert browsed.json()["code"] == "hosted_restriction"
        assert "hosted demo" in browsed.json()["message"]


@pytest.mark.usefixtures("hosted_environment")
def test_only_the_repositories_the_demo_ships_with_can_be_indexed(tmp_path: Path) -> None:
    elsewhere = tmp_path / "somebody-elses-code"
    elsewhere.mkdir()
    with _client() as client:
        bundled = {item["name"]: item for item in client.get("/api/examples").json()}

        refused = client.post(
            "/api/repositories/index", json={"root_path": str(elsewhere)}
        )
        assert refused.status_code == 403
        assert refused.json()["code"] == "hosted_restriction"

        allowed = client.post(
            "/api/repositories/index",
            json={"root_path": bundled[FIXTURE]["repository_root"]},
        )
        assert allowed.status_code == 201, allowed.text


@pytest.mark.usefixtures("hosted_environment")
def test_a_folder_on_the_server_cannot_become_a_policy_source_but_writing_one_can(
    tmp_path: Path,
) -> None:
    with _client() as client:
        refused = client.post("/api/policies/sources", json={"source": str(tmp_path)})
        assert refused.status_code == 403
        assert refused.json()["code"] == "hosted_restriction"

        written = client.post(
            "/api/policies",
            json={
                "title": "Modules own their data",
                "description": "A module reads its own store and nobody else's.",
                "body": _POLICY_BODY,
                "tags": ["data"],
                "strength": "preferred",
            },
        )
        assert written.status_code == 201, written.text


@pytest.mark.usefixtures("hosted_environment")
def test_the_daily_budget_refuses_the_run_past_the_cap(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ARCHCOMPASS_SESSION_DAILY_RUNS", "1")
    with _client() as client:
        _choose_the_deterministic_model(client)
        loaded = client.post(f"/api/examples/{FIXTURE}/load")
        assert loaded.status_code == 201, loaded.text
        root = loaded.json()["root_path"]
        started = client.post("/api/repositories/start", json={"root_path": root})
        assert started.status_code == 201, started.text
        request = {"case_id": started.json()["case_id"], "repository_root": root}

        assert client.post("/api/reviews", json=request).status_code == 201
        refused = client.post("/api/reviews", json=request)

        assert refused.status_code == 429
        problem = refused.json()
        assert problem["code"] == "budget_exhausted"
        assert "free-tier demo" in problem["message"]
        reset = datetime.combine(
            (datetime.now(UTC) + timedelta(days=1)).date(),
            datetime.min.time(),
            tzinfo=UTC,
        )
        assert reset.isoformat() in problem["message"]
        # Reading is not rationed: what the cap protects is the model quota.
        assert client.get("/api/reviews").status_code == 200


@pytest.mark.usefixtures("hosted_environment")
def test_the_budget_is_counted_per_session(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ARCHCOMPASS_SESSION_DAILY_RUNS", "1")
    application = create_hosted_app()
    request = {"case_id": "case-nobody-has", "repository_root": "/nowhere"}
    with (
        TestClient(application, base_url=HOSTED_URL) as mine,
        TestClient(application, base_url=HOSTED_URL) as theirs,
    ):
        # Admission is counted before the route runs, so a run refused for any other reason
        # still spends from the budget: the tokens are spent by starting, not by finishing.
        assert mine.post("/api/reviews", json=request).status_code == 404
        assert mine.post("/api/reviews", json=request).status_code == 429

        assert theirs.post("/api/reviews", json=request).status_code == 404


@pytest.mark.usefixtures("hosted_environment")
def test_a_hosted_instance_with_no_reachable_provider_refuses_to_start(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ARCHCOMPASS_PROVIDERS", "google")
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)

    with pytest.raises(Exception, match="GOOGLE_API_KEY"):
        create_hosted_app()


def test_a_local_workspace_is_untouched_by_any_of_it(runtime: Runtime) -> None:
    """The same app object, built the way the CLI builds it: no session, no restrictions."""

    with TestClient(create_app(runtime)) as client:
        summary = client.get("/api/workspace")

        assert summary.status_code == 200
        assert summary.json()["hosted"] is False
        assert summary.json()["workspace"] == str(runtime.workspace)
        assert SESSION_COOKIE not in client.cookies
        assert "set-cookie" not in summary.headers
        assert client.get("/api/filesystem/directories").status_code == 200
