"""The hosted demo: a workspace per visitor, three refusals, and a daily budget."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

pytest.importorskip("fastapi")

from fastapi.testclient import TestClient

from archcompass.adapters.models.catalog import DETERMINISTIC_MODEL
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
        assert started.status_code == 200, started.text

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
def test_the_folder_listing_reaches_only_what_indexing_reaches(tmp_path: Path) -> None:
    """A route that lists any folder on the server is the picker this demo already refuses.

    It reads the same directories indexing reads, so it is narrowed by the same rule rather
    than by one of its own — a second rule is a second thing to get wrong.
    """

    elsewhere = tmp_path / "somebody-elses-code"
    elsewhere.mkdir()
    with _client() as client:
        bundled = {item["name"]: item for item in client.get("/api/examples").json()}

        refused = client.post(
            "/api/repositories/tree", json={"root_path": str(elsewhere)}
        )
        assert refused.status_code == 403
        assert refused.json()["code"] == "hosted_restriction"

        allowed = client.post(
            "/api/repositories/tree",
            json={"root_path": bundled[FIXTURE]["repository_root"]},
        )
        assert allowed.status_code == 200, allowed.text
        assert allowed.json()["total_python_files"] > 0


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
        assert started.status_code == 200, started.text
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


@pytest.mark.usefixtures("hosted_environment")
def test_the_hosted_demo_will_not_clone_a_repository_a_visitor_names() -> None:
    """A URL a visitor chooses is a request this server would make on their behalf."""

    with _client() as client:
        refused = client.post(
            "/api/repositories/checkout",
            json={"url": "https://example.invalid/somebody/code.git"},
        )

        assert refused.status_code == 403
        assert refused.json()["code"] == "hosted_restriction"
        assert "will not clone" in refused.json()["message"]

        # And will not fetch into one either. There are no managed checkouts here for it to
        # be about, so the refusal costs a visitor nothing and needs no second explanation.
        stale = client.post(
            "/api/repositories/refresh", json={"root_path": "/tmp/somebody/code"}
        )

        assert stale.status_code == 403
        assert stale.json()["code"] == "hosted_restriction"


@pytest.fixture
def fetching_environment(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """A demo that was given hosts to fetch from, which is off unless a deployment says so."""

    monkeypatch.setenv("ARCHCOMPASS_SOURCE_HOSTS", "github.com")
    yield


@pytest.mark.usefixtures("hosted_environment", "fetching_environment")
def test_a_demo_that_fetches_says_which_hosts_it_will_fetch_from() -> None:
    """The page offers the field only where the server named hosts, so it has to say them."""

    with _client() as client:
        summary = client.get("/api/workspace").json()

        assert summary["hosted"] is True
        assert summary["source_hosts"] == ["github.com"]


@pytest.mark.usefixtures("hosted_environment")
def test_a_demo_that_was_given_no_hosts_offers_none() -> None:
    with _client() as client:
        assert client.get("/api/workspace").json()["source_hosts"] == []


@pytest.mark.usefixtures("hosted_environment", "fetching_environment")
@pytest.mark.parametrize(
    "address",
    [
        "file:///tmp/archcompass-sessions/somebody-else/repository",
        "git@github.com:owner/repository",
        "http://github.com/owner/repository",
        "https://github.com@169.254.169.254/owner/repository",
        "https://169.254.169.254/owner/repository",
        "https://github.com.evil.test/owner/repository",
        "https://github.com:8080/owner/repository",
        "https://gitlab.com/owner/repository",
        "/etc",
    ],
)
def test_a_demo_that_fetches_still_fetches_only_from_the_hosts_it_named(
    address: str,
) -> None:
    """The metadata address is the one that matters: on a cloud instance it serves tokens."""

    with _client() as client:
        refused = client.post("/api/repositories/checkout", json={"url": address})

        assert refused.status_code == 409, refused.text
        assert "not an address this workspace will fetch" in refused.json()["message"]


@pytest.mark.usefixtures("hosted_environment", "fetching_environment")
def test_a_repository_a_visitor_did_not_fetch_is_still_not_indexable() -> None:
    """Allowing a fetch does not allow naming a folder — including another session's."""

    with _client() as client:
        refused = client.post(
            "/api/repositories/index", json={"root_path": "/etc"}
        )

        assert refused.status_code == 403
        assert refused.json()["code"] == "hosted_restriction"


@pytest.mark.usefixtures("hosted_environment", "fetching_environment")
def test_a_demo_that_fetches_answers_refresh_rather_than_refusing_it() -> None:
    """Every run begins by asking for this, so refusing would fail every review."""

    with _client() as client:
        answered = client.post(
            "/api/repositories/refresh", json={"root_path": "/tmp/somewhere"}
        )

        assert answered.status_code == 200, answered.text
        assert answered.json()["managed"] is False
        assert answered.json()["updated"] is False


@pytest.mark.usefixtures("hosted_environment", "fetching_environment")
def test_the_hosted_demo_stops_fetching_past_the_daily_cap(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ARCHCOMPASS_SESSION_DAILY_FETCHES", "1")
    with _client() as client:
        # Refused for what it is, but counted: a fetch that fails has already been asked for.
        first = client.post(
            "/api/repositories/checkout", json={"url": "https://evil.test/o/r"}
        )
        assert first.status_code == 409

        second = client.post(
            "/api/repositories/checkout", json={"url": "https://github.com/o/r"}
        )

        assert second.status_code == 429
        assert second.json()["code"] == "budget_exhausted"
        assert "as many repositories as this demo allows" in second.json()["message"]


def test_a_deployment_cannot_allow_a_host_this_build_cannot_fetch_from(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Said once, to whoever deployed it, rather than to every visitor who pastes a URL."""

    monkeypatch.setenv("ARCHCOMPASS_HOSTED", "1")
    monkeypatch.setenv("ARCHCOMPASS_PROVIDERS", "fake")
    monkeypatch.setenv("ARCHCOMPASS_SESSION_ROOT", str(tmp_path / "sessions"))
    monkeypatch.setenv("ARCHCOMPASS_SOURCE_HOSTS", "github.com,evil.test")

    with pytest.raises(Exception, match=r"evil\.test"):
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
        # No hosts to fetch from, because a local workspace does not fetch: it clones,
        # from wherever the git on this machine can reach.
        assert summary.json()["source_hosts"] == []


@pytest.mark.usefixtures("hosted_environment", "fetching_environment")
def test_the_demo_analyses_one_repository_at_a_time(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Two overlapping analyses is how a container sized for one of them dies."""

    from archcompass.presentation.web import dependencies as web_dependencies

    monkeypatch.setattr(web_dependencies, "INDEX_QUEUE_SECONDS", 0.1)
    application = create_hosted_app()
    assert application.state.index_lock is not None

    # Held by somebody else's analysis: the next caller is told, not left waiting forever.
    application.state.index_lock.acquire()
    try:
        with TestClient(application, base_url=HOSTED_URL) as client:
            refused = client.post("/api/repositories/index", json={"root_path": "/etc"})

            assert refused.status_code == 503
            assert refused.json()["code"] == "busy"
            assert "one at a time" in refused.json()["message"]
    finally:
        application.state.index_lock.release()


@pytest.mark.usefixtures("hosted_environment", "fetching_environment")
def test_the_slot_is_given_back_even_when_the_route_refuses() -> None:
    """A guard that leaked its permit would serialise the demo down to one index, ever."""

    application = create_hosted_app()
    with TestClient(application, base_url=HOSTED_URL) as client:
        for _ in range(3):
            assert client.post(
                "/api/repositories/index", json={"root_path": "/etc"}
            ).status_code == 403

    # The slot is free, so it can be taken: three refusals in a row each gave theirs back.
    assert application.state.index_lock.acquire(blocking=False)
    application.state.index_lock.release()


@pytest.mark.usefixtures("hosted_environment", "fetching_environment")
def test_a_swept_repository_comes_back_when_the_next_run_asks_for_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The dead end this closes: a repository listed on the start page whose code has gone.

    The instance deletes the least recently used source to stay inside its memory, and the
    atlas outlives the directory — so without this, a visitor returning to their own
    repository met "repository does not exist" and had nothing to do about it.
    """

    import io
    import shutil
    import tarfile
    from pathlib import Path

    import httpx

    import archcompass.adapters.sources.https_tarball as tarball

    def archive() -> bytes:
        raw = io.BytesIO()
        with tarfile.open(fileobj=raw, mode="w:gz") as tar:
            body = b"class Thing:\n    def run(self):\n        return 1\n"
            info = tarfile.TarInfo("repository-abc123/pkg.py")
            info.size = len(body)
            tar.addfile(info, io.BytesIO(body))
        return raw.getvalue()

    served = archive()
    monkeypatch.setattr(
        tarball.httpx,
        "stream",
        lambda method, url, **kwargs: httpx.Client(
            transport=httpx.MockTransport(lambda _r: httpx.Response(200, content=served))
        ).stream(method, url),
    )

    with _client() as client:
        fetched = client.post(
            "/api/repositories/checkout",
            json={"url": "https://github.com/owner/repository"},
        )
        assert fetched.status_code == 201, fetched.text
        root = fetched.json()["root_path"]
        assert client.post("/api/repositories/index", json={"root_path": root}).status_code == 201

        # Swept, exactly as the instance would sweep it to make room for somebody else.
        shutil.rmtree(root)
        assert not Path(root).is_dir()

        # What every run begins with, and what a reader never sees.
        refreshed = client.post("/api/repositories/refresh", json={"root_path": root})
        assert refreshed.status_code == 200, refreshed.text
        assert refreshed.json()["managed"] is True
        assert Path(root).is_dir()

        # And the run that follows it works, rather than meeting a path that is not there.
        assert client.post("/api/repositories/index", json={"root_path": root}).status_code == 201
