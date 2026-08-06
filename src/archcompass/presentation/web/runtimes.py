"""Which workspace a request is served from.

A local run has one workspace and one runtime, built before the server starts. A hosted
run has one per visitor, built on first sight of their cookie. Both are the same shape to
the routes, which take the runtime they were handed and know nothing about how it was
chosen.
"""

from __future__ import annotations

import re
import secrets
from collections import OrderedDict
from collections.abc import MutableMapping
from pathlib import Path
from threading import Lock
from typing import Any, Protocol

from starlette.datastructures import Headers, MutableHeaders
from starlette.requests import Request
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from archcompass.adapters.analysis import UNLIMITED_ANALYSIS, AnalysisLimits
from archcompass.application.source_storage import SourceStorage
from archcompass.bootstrap import Runtime, build_runtime

#: The name a browser holds a session under. Opaque, and the only thing tying a visitor to
#: their workspace: there is no account, and nothing else about the request is stable.
SESSION_COOKIE = "archcompass_session"

#: What a cookie value may contain before it is allowed to name a directory. The token this
#: process issues is `token_urlsafe`, which is exactly this alphabet — so this is not about
#: what we write, it is about what comes back: a cookie is client-controlled input, and this
#: one is concatenated onto a path. A value that fails is replaced rather than corrected.
_SESSION_TOKEN = re.compile(r"^[A-Za-z0-9_-]{16,64}$")

#: 24 bytes, well past the 128 bits a guess would have to beat to land in someone else's
#: workspace.
_TOKEN_BYTES = 24

#: Where the middleware leaves the token it settled on, for the provider to read. Carried in
#: the request rather than re-derived, so the cookie is validated once per request and the
#: token a response sets is the token that request was served under.
_SCOPE_STATE_KEY = "archcompass_session_token"

#: How long a browser keeps the cookie. Long enough that a visitor returning the next day
#: finds their cases, short enough that an abandoned workspace stops being addressable.
_COOKIE_MAX_AGE = 60 * 60 * 24 * 30

#: What a run left running by a process that is gone is told it was. A hosted instance is
#: recycled between visits, so this is the ordinary end of any review that was mid-flight
#: when an instance went away — not an exceptional case.
_ABANDONED = "The workspace stopped while this review was running, so nothing was judged."


class RuntimeProvider(Protocol):
    """Where a request's workspace comes from."""

    def acquire(self, request: Request) -> Runtime: ...


class SingleRuntimeProvider:
    """One workspace for every request, which is what a local run is.

    The request is ignored on purpose: a local server binds loopback and serves the one
    person whose files these are, so there is nobody to tell apart.
    """

    def __init__(self, runtime: Runtime) -> None:
        self._runtime = runtime
        _abandon_interrupted_reviews(runtime)

    def acquire(self, request: Request) -> Runtime:
        return self._runtime


class SessionRuntimeProvider:
    """One workspace per browser session, under a shared root.

    The token is the directory name, so two visitors to a hosted instance share nothing:
    not cases, not atlases, not which model they chose. Nothing is shared deliberately
    either — there is no way to name another session's workspace, because naming it would
    mean knowing its token.
    """

    def __init__(
        self,
        base_directory: Path,
        limit: int = 32,
        *,
        source_hosts: frozenset[str] = frozenset(),
        max_source_bytes: int = 0,
        source_timeout: int = 0,
        source_storage: SourceStorage | None = None,
        analysis_limits: AnalysisLimits = UNLIMITED_ANALYSIS,
    ) -> None:
        self._base_directory = base_directory.expanduser().resolve(strict=False)
        self._limit = limit
        # Carried rather than read here: every session's workspace fetches from the same
        # hosts under the same caps, because they are what the deployment is, not what a
        # visitor chose.
        self._source_hosts = source_hosts
        self._max_source_bytes = max_source_bytes
        self._source_timeout = source_timeout
        self._source_storage = source_storage
        self._analysis_limits = analysis_limits
        self._runtimes: OrderedDict[str, Runtime] = OrderedDict()
        # Held across the build of a new runtime, not only around the dictionary. Two
        # requests arriving together for the same new session would otherwise both open
        # the same database and run its migrations, and the loser of that race is a
        # visitor whose first page load fails.
        self._lock = Lock()

    def acquire(self, request: Request) -> Runtime:
        token = session_token(request)
        with self._lock:
            cached = self._runtimes.get(token)
            if cached is not None:
                self._runtimes.move_to_end(token)
                return cached
            runtime = self._open(token)
            self._runtimes[token] = runtime
            while len(self._runtimes) > self._limit:
                # Least recently used, and losing nothing: the workspace stays on disk and
                # the next request from that session rebuilds a runtime over it. What is
                # dropped is a handle. SQLite is not held open between operations here —
                # `SQLiteDatabase.connect` opens and closes a connection per call — so
                # there is no connection to close on the way out either.
                self._runtimes.popitem(last=False)
            return runtime

    def _open(self, token: str) -> Runtime:
        runtime = build_runtime(
            self._base_directory / token,
            source_hosts=self._source_hosts,
            max_source_bytes=self._max_source_bytes,
            source_timeout=self._source_timeout,
            source_storage=self._source_storage,
            analysis_limits=self._analysis_limits,
        )
        _abandon_interrupted_reviews(runtime)
        return runtime


class SessionCookieMiddleware:
    """Give every request a session token, and hand a new one back in a cookie.

    Plain ASGI rather than `BaseHTTPMiddleware` because two of these routes stream
    newline-delimited JSON for as long as a review takes, and a middleware that owns the
    response body is the wrong thing to put in front of them. This one reads the request
    headers and appends one response header; it never touches the body.
    """

    def __init__(self, app: ASGIApp, *, secure: bool = True) -> None:
        self.app = app
        self._secure = secure

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        presented = _presented_token(Headers(scope=scope))
        token = presented if presented is not None else new_session_token()
        state: MutableMapping[str, Any] = scope.setdefault("state", {})
        state[_SCOPE_STATE_KEY] = token
        if presented is not None:
            await self.app(scope, receive, send)
            return
        await self.app(scope, receive, _sending_cookie(send, self._cookie(token)))

    def _cookie(self, token: str) -> str:
        attributes = [
            f"{SESSION_COOKIE}={token}",
            "Path=/",
            f"Max-Age={_COOKIE_MAX_AGE}",
            "HttpOnly",
            "SameSite=Lax",
        ]
        # Https-only, because the deployment is. Off only where a test drives the app over
        # plain http; a hosted instance behind anything but TLS is a misconfiguration, not
        # a mode.
        if self._secure:
            attributes.append("Secure")
        return "; ".join(attributes)


def _sending_cookie(send: Send, cookie: str) -> Send:
    async def send_with_cookie(message: Message) -> None:
        if message["type"] == "http.response.start":
            MutableHeaders(scope=message).append("set-cookie", cookie)
        await send(message)

    return send_with_cookie


def new_session_token() -> str:
    return secrets.token_urlsafe(_TOKEN_BYTES)


def session_token(request: Request) -> str:
    """The token this request is served under.

    Settled by the middleware, which is also what sets the cookie; read from the request
    here so that a token issued to a request and the workspace that request is served from
    cannot disagree. Falling back to the cookie keeps the provider usable without the
    middleware, which is what a unit test does.
    """

    carried = request.scope.get("state", {}).get(_SCOPE_STATE_KEY)
    if isinstance(carried, str):
        return carried
    presented = _presented_token(request.headers)
    return presented if presented is not None else new_session_token()


def _presented_token(headers: Headers) -> str | None:
    """The valid token this request presented, or `None` — including for an invalid one.

    An invalid value is not repaired and not reported: it is simply not a session, so the
    request is served as a new one. Nothing a client sends reaches the filesystem.
    """

    cookie = headers.get("cookie")
    if not cookie:
        return None
    for entry in cookie.split(";"):
        name, separator, value = entry.strip().partition("=")
        if separator and name == SESSION_COOKIE and _SESSION_TOKEN.match(value):
            return value
    return None


def _abandon_interrupted_reviews(runtime: Runtime) -> None:
    """Close out any review a previous process was in the middle of.

    A run cannot outlive the process holding its request, so a row still marked running
    when a runtime is opened over that workspace belongs to a process that is gone, and
    leaving it saying "in progress" for ever would be the one thing worse than reporting it
    failed.
    """

    runtime.review_repository.abandon_running(reason=_ABANDONED)


