"""One workspace per session: which one a request gets, and what eviction costs."""

from __future__ import annotations

from pathlib import Path

from starlette.requests import Request

from archcompass.domain import CaseConstraint, CaseFacet
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
        constraints=(CaseConstraint(title, CaseFacet.CONSTRAINT),)
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
