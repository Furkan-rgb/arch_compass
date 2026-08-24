"""One workspace per session: which one a request gets, and what eviction costs."""

from __future__ import annotations

import threading
from collections.abc import Callable
from pathlib import Path

from starlette.requests import Request

from archcompass.bootstrap import Runtime
from archcompass.domain import PolicyContext
from archcompass.presentation.web.runtimes import (
    SESSION_COOKIE,
    SessionRuntimeProvider,
    SingleRuntimeProvider,
)

TOKEN = "aaaaaaaaaaaaaaaaaaaa"
OTHER_TOKEN = "bbbbbbbbbbbbbbbbbbbb"


def _request(cookie: str | None = None) -> Request:
    headers = (
        [(b"cookie", f"{SESSION_COOKIE}={cookie}".encode())] if cookie is not None else []
    )
    return Request({"type": "http", "method": "GET", "path": "/", "headers": headers})


def _write_case(provider: SessionRuntimeProvider, cookie: str, title: str) -> str:
    created = provider.acquire(_request(cookie)).case_service.create(
        policy_context=PolicyContext(organisation=title)
    )
    return created.id


def _workspace_for(base: Path, cookie: str) -> Path:
    return SessionRuntimeProvider(base).acquire(_request(cookie)).workspace


def test_each_session_gets_its_own_workspace_directory(tmp_path: Path) -> None:
    provider = SessionRuntimeProvider(tmp_path)

    mine = provider.acquire(_request(TOKEN))
    theirs = provider.acquire(_request(OTHER_TOKEN))

    assert mine.workspace == tmp_path / TOKEN
    assert theirs.workspace == tmp_path / OTHER_TOKEN


def test_the_same_cookie_comes_back_to_the_same_runtime(tmp_path: Path) -> None:
    provider = SessionRuntimeProvider(tmp_path)

    assert provider.acquire(_request(TOKEN)) is provider.acquire(_request(TOKEN))


def test_an_evicted_session_loses_nothing_but_its_handle(tmp_path: Path) -> None:
    provider = SessionRuntimeProvider(tmp_path, limit=1)
    case_id = _write_case(provider, TOKEN, "Written before eviction")

    # Opening a second session over a cache of one evicts the first.
    provider.acquire(_request(OTHER_TOKEN))
    returning = provider.acquire(_request(TOKEN))

    assert returning.workspace == tmp_path / TOKEN
    assert [item.id for item in returning.case_service.list()] == [case_id]


def test_a_cookie_that_could_name_a_directory_is_replaced(tmp_path: Path) -> None:
    """A value that is not a token is not repaired into one — it is simply not a session."""

    escaping = _workspace_for(tmp_path, "../elsewhere")
    short = _workspace_for(tmp_path, "tiny")

    for workspace in (escaping, short):
        assert workspace.parent == tmp_path.resolve()
        assert workspace.name not in {"..", "elsewhere", "tiny"}


def test_a_local_provider_serves_every_request_the_one_workspace(runtime) -> None:
    provider = SingleRuntimeProvider(runtime)

    assert provider.acquire(_request()) is runtime
    assert provider.acquire(_request(TOKEN)) is runtime


def _running_review(runtime: Runtime) -> tuple[str, threading.Event]:
    """A durable execution row with a thread that is provably alive against it.

    No model and no graph: `ReviewRunner.start` takes any callable, which is the seam this
    needs. The handshake is an Event rather than a sleep, so the test asserts on a thread
    that is running rather than on one that probably is.
    """

    service = runtime.review_workflow_service
    thread_id = service._begin("repo-1", "branch-1", "case-1")
    started, release = threading.Event(), threading.Event()

    def work(report: Callable[[str], None]) -> None:
        started.set()
        release.wait(timeout=30)

    service._runner.start(run_id=thread_id, work=work)
    assert started.wait(timeout=10), "the run never started"
    return thread_id, release


def test_a_session_in_the_middle_of_a_review_is_not_evicted(tmp_path: Path) -> None:
    """The eviction above loses a handle. This one used to lose the review.

    A background run lives on a thread inside the runtime's `ReviewWorkflowService`, and
    dropping the cache entry does not stop it. When the session came back, `_open` called
    `_abandon_interrupted_reviews` — which marks every row still `running` as failed and
    releases its checkpoints — against a review that was at that moment still executing.
    Reproduced before the fix: the durable row read `failed` while `is_running` on the same
    thread id read `True`.
    """

    provider = SessionRuntimeProvider(tmp_path, limit=1)
    runtime = provider.acquire(_request(TOKEN))
    thread_id, release = _running_review(runtime)

    try:
        provider.acquire(_request(OTHER_TOKEN))
        returning = provider.acquire(_request(TOKEN))

        assert returning.review_workflow_service.run_state(thread_id).status == "running"
        assert returning is runtime, "a busy session was rebuilt over its own live run"
    finally:
        release.set()


def test_a_cache_full_of_busy_sessions_grows_rather_than_corrupting_one(
    tmp_path: Path,
) -> None:
    """When nothing is evictable, going over the limit is the answer.

    The alternatives are refusing the request or failing somebody's review, and both are
    worse than holding one more directory handle. So `limit` is how many *idle* workspaces
    stay open; the ceiling is that plus however many reviews are running at once.
    """

    provider = SessionRuntimeProvider(tmp_path, limit=1)
    first = provider.acquire(_request(TOKEN))
    first_id, first_release = _running_review(first)
    second = provider.acquire(_request(OTHER_TOKEN))
    second_id, second_release = _running_review(second)

    try:
        provider.acquire(_request("cccccccccccccccccccc"))

        assert len(provider._runtimes) == 3, "a busy session was evicted to make room"
        assert first.review_workflow_service.run_state(first_id).status == "running"
        assert second.review_workflow_service.run_state(second_id).status == "running"
    finally:
        first_release.set()
        second_release.set()


def test_the_cache_trims_back_once_the_work_is_done(tmp_path: Path) -> None:
    """Pinning is for the length of the run, not for the length of the process."""

    provider = SessionRuntimeProvider(tmp_path, limit=1)
    runtime = provider.acquire(_request(TOKEN))
    thread_id, release = _running_review(runtime)
    provider.acquire(_request(OTHER_TOKEN))
    assert len(provider._runtimes) == 2

    release.set()
    runtime.review_workflow_service._runner._threads[thread_id].join(timeout=10)

    provider.acquire(_request("cccccccccccccccccccc"))

    assert len(provider._runtimes) == 1, "an idle session stayed pinned after its run ended"
