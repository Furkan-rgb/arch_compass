"""The public demo's entry point: one instance, one workspace per visitor.

Separate from `archcompass web` rather than a flag on it. The CLI opens the directory
someone is standing in and serves it to them; this opens a directory per session under a
root nobody owns, refuses the things a stranger must not be able to do, and rations the
model calls it will make. Nothing here changes what a local run does, because a local run
never reaches this module.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Final

from fastapi import FastAPI

from archcompass.bootstrap import enabled_providers
from archcompass.domain.errors import ConfigurationError
from archcompass.presentation.web.app import create_app
from archcompass.presentation.web.restrictions import RunBudget
from archcompass.presentation.web.runtimes import (
    SessionCookieMiddleware,
    SessionRuntimeProvider,
)

#: Where session workspaces are written. A container's own filesystem by default, which is
#: ephemeral and is the right lifetime for a demo: an instance that scales to zero takes the
#: workspaces with it, and a returning visitor starts again rather than finding a stale one.
SESSION_ROOT_VARIABLE: Final = "ARCHCOMPASS_SESSION_ROOT"
DEFAULT_SESSION_ROOT: Final = "/tmp/archcompass-sessions"

#: How many workspaces stay open at once. Each is a directory and a handful of objects, not
#: a connection, so this bounds memory rather than any external resource.
SESSION_CACHE_VARIABLE: Final = "ARCHCOMPASS_SESSION_CACHE"
DEFAULT_SESSION_CACHE: Final = 32

SESSION_DAILY_RUNS_VARIABLE: Final = "ARCHCOMPASS_SESSION_DAILY_RUNS"
DEFAULT_SESSION_DAILY_RUNS: Final = 25

GLOBAL_DAILY_RUNS_VARIABLE: Final = "ARCHCOMPASS_GLOBAL_DAILY_RUNS"
DEFAULT_GLOBAL_DAILY_RUNS: Final = 250

#: The one switch. Read only here, at startup: hosted-ness reaches the routes as an argument
#: to `create_app`, so nothing decides what it is by reading the environment mid-request and
#: a local run cannot be turned into a hosted one by a stray variable.
#:
#: Required rather than defaulted either way. This entry point cannot serve a local
#: workspace, so treating an absent variable as "not hosted" would mean a public server with
#: the folder picker on; and inventing hosted-ness from the entry point alone would leave the
#: variable the deployment sets doing nothing.
HOSTED_VARIABLE: Final = "ARCHCOMPASS_HOSTED"


def create_hosted_app() -> FastAPI:
    """The ASGI application a container serves. Fails at startup rather than at first use.

    A demo whose only provider has no credential is a picker full of rows that cannot be
    chosen — every visitor discovers the misconfiguration, one click each, and the logs say
    nothing until they do. Refusing to start says it once, to the person deploying.
    """

    if os.environ.get(HOSTED_VARIABLE, "").strip() in {"", "0"}:
        raise ConfigurationError(
            f"{HOSTED_VARIABLE}=1 is required to serve the hosted demo. Local workspaces "
            "are opened with `archcompass web`."
        )
    providers = enabled_providers()
    if "google" in providers and not os.environ.get("GOOGLE_API_KEY", "").strip():
        raise ConfigurationError(
            "This deployment offers the google provider but GOOGLE_API_KEY is unset, so "
            "nothing it lists could answer. Set the key, or narrow ARCHCOMPASS_PROVIDERS."
        )
    root = Path(os.environ.get(SESSION_ROOT_VARIABLE, "").strip() or DEFAULT_SESSION_ROOT)
    app = create_app(
        SessionRuntimeProvider(root, _positive_int(SESSION_CACHE_VARIABLE, DEFAULT_SESSION_CACHE)),
        hosted=True,
        budget=RunBudget(
            session_daily_runs=_positive_int(
                SESSION_DAILY_RUNS_VARIABLE, DEFAULT_SESSION_DAILY_RUNS
            ),
            global_daily_runs=_positive_int(
                GLOBAL_DAILY_RUNS_VARIABLE, DEFAULT_GLOBAL_DAILY_RUNS
            ),
        ),
    )
    app.add_middleware(SessionCookieMiddleware)
    return app


def _positive_int(variable: str, default: int) -> int:
    raw = os.environ.get(variable, "").strip()
    if not raw:
        return default
    try:
        value = int(raw)
    except ValueError as error:
        raise ConfigurationError(f"{variable} must be a whole number, not {raw!r}.") from error
    if value < 1:
        raise ConfigurationError(f"{variable} must be at least 1, not {value}.")
    return value
