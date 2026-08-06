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

from archcompass.adapters.analysis import AnalysisLimits
from archcompass.adapters.sources.https_tarball import ARCHIVE_URLS
from archcompass.application.source_storage import SourceStorage
from archcompass.bootstrap import enabled_providers
from archcompass.domain.errors import ConfigurationError
from archcompass.presentation.web.app import create_app
from archcompass.presentation.web.restrictions import FetchBudget, RunBudget
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

#: Runs per day, sized against the free tier rather than against a guess. Cloud Run gives
#: 180,000 vCPU-seconds a month, which is 6,000 a day; a review holds its stream open for
#: roughly two minutes between indexing and the model, so 6,000 / 120 is where 50 comes
#: from. The 250 this used to be was five times the budget.
SESSION_DAILY_RUNS_VARIABLE: Final = "ARCHCOMPASS_SESSION_DAILY_RUNS"
DEFAULT_SESSION_DAILY_RUNS: Final = 10

GLOBAL_DAILY_RUNS_VARIABLE: Final = "ARCHCOMPASS_GLOBAL_DAILY_RUNS"
DEFAULT_GLOBAL_DAILY_RUNS: Final = 50

#: The one switch. Read only here, at startup: hosted-ness reaches the routes as an argument
#: to `create_app`, so nothing decides what it is by reading the environment mid-request and
#: a local run cannot be turned into a hosted one by a stray variable.
#:
#: Required rather than defaulted either way. This entry point cannot serve a local
#: workspace, so treating an absent variable as "not hosted" would mean a public server with
#: the folder picker on; and inventing hosted-ness from the entry point alone would leave the
#: variable the deployment sets doing nothing.
HOSTED_VARIABLE: Final = "ARCHCOMPASS_HOSTED"

#: Which hosts a visitor may name a repository on. Empty by default, and empty means the demo
#: reviews only the examples it ships with — the behaviour every deployment had before this
#: existed, so turning it on is a decision somebody makes rather than one they inherit.
#:
#: The variable narrows `SUPPORTED_SOURCE_HOSTS`; it cannot widen it. A host reaches the
#: fetcher only by being written into `ARCHIVE_URLS` in the adapter, because a host is not
#: just a name to allow — it is a URL shape to ask for — and the two have to be decided
#: together, in code, by someone who can see both.
SOURCE_HOSTS_VARIABLE: Final = "ARCHCOMPASS_SOURCE_HOSTS"
SUPPORTED_SOURCE_HOSTS: Final = tuple(sorted(ARCHIVE_URLS))

#: How large one repository may be, counted while it arrives and again over what its archive
#: says it unpacks to. Sized from what repositories actually weigh rather than from a round
#: number: a large Python project is tens of megabytes of source once the history is left
#: behind, and something far past this is not a repository somebody wants reviewed.
MAX_SOURCE_MB_VARIABLE: Final = "ARCHCOMPASS_MAX_SOURCE_MB"
DEFAULT_MAX_SOURCE_MB: Final = 64

#: How much every visitor's fetched code may occupy at once. The number that actually has to
#: fit, and the one the per-repository cap above does not bound: a container's `/tmp` is
#: memory, so this is spent from the same allowance the server runs in, and exhausting it
#: kills the process rather than the fetch — taking every session on the instance with it.
#:
#: Against a 1 GiB container whose application measures around 200 MB with an analysis in
#: flight, this leaves room to spare. Raise it with the container's memory, not on its own.
MAX_TOTAL_SOURCE_MB_VARIABLE: Final = "ARCHCOMPASS_MAX_TOTAL_SOURCE_MB"
DEFAULT_MAX_TOTAL_SOURCE_MB: Final = 250

#: How long the fetch may take. Shorter than a clone's budget, because there is no history to
#: transfer and a repository that cannot arrive inside two minutes is not one a demo is for.
SOURCE_TIMEOUT_VARIABLE: Final = "ARCHCOMPASS_SOURCE_TIMEOUT"
DEFAULT_SOURCE_TIMEOUT: Final = 120

#: What one file and one repository may be, for an analysis that holds every file it reads
#: in memory at once. Applied to every workspace on the instance, not only to fetched ones:
#: the bundled examples are small and unaffected, and a ceiling that only existed on some
#: repositories would be a ceiling somebody could step around.
MAX_FILE_KB_VARIABLE: Final = "ARCHCOMPASS_MAX_FILE_KB"
DEFAULT_MAX_FILE_KB: Final = 2048

MAX_FILES_VARIABLE: Final = "ARCHCOMPASS_MAX_FILES"
DEFAULT_MAX_FILES: Final = 1_200

#: How much Python one repository may bring. The binding limit, and the reason the two above
#: exist mostly to catch shapes it does not: see `AnalysisLimits.max_python_bytes` for where
#: the number comes from and what it is protecting against.
MAX_PYTHON_MB_VARIABLE: Final = "ARCHCOMPASS_MAX_PYTHON_MB"
DEFAULT_MAX_PYTHON_MB: Final = 5

SESSION_DAILY_FETCHES_VARIABLE: Final = "ARCHCOMPASS_SESSION_DAILY_FETCHES"
DEFAULT_SESSION_DAILY_FETCHES: Final = 5

GLOBAL_DAILY_FETCHES_VARIABLE: Final = "ARCHCOMPASS_GLOBAL_DAILY_FETCHES"
DEFAULT_GLOBAL_DAILY_FETCHES: Final = 100


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
    source_hosts = _source_hosts()
    max_source_bytes = _positive_int(MAX_SOURCE_MB_VARIABLE, DEFAULT_MAX_SOURCE_MB) << 20
    app = create_app(
        SessionRuntimeProvider(
            root,
            _positive_int(SESSION_CACHE_VARIABLE, DEFAULT_SESSION_CACHE),
            source_hosts=source_hosts,
            max_source_bytes=max_source_bytes,
            source_timeout=_positive_int(SOURCE_TIMEOUT_VARIABLE, DEFAULT_SOURCE_TIMEOUT),
            # One ceiling object, shared by every session: what it bounds is the instance,
            # which is the thing that runs out.
            source_storage=SourceStorage(
                root=root,
                max_total_bytes=_positive_int(
                    MAX_TOTAL_SOURCE_MB_VARIABLE, DEFAULT_MAX_TOTAL_SOURCE_MB
                )
                << 20,
            )
            if source_hosts
            else None,
            analysis_limits=AnalysisLimits(
                max_file_bytes=_positive_int(MAX_FILE_KB_VARIABLE, DEFAULT_MAX_FILE_KB) * 1024,
                max_files=_positive_int(MAX_FILES_VARIABLE, DEFAULT_MAX_FILES),
                max_python_bytes=_positive_int(MAX_PYTHON_MB_VARIABLE, DEFAULT_MAX_PYTHON_MB)
                << 20,
                # Never on the demo, whoever the repository belongs to. A bundled example
                # has no secrets to leak and a visitor's repository is not ours to forward.
                include_environment_files=False,
            ),
        ),
        hosted=True,
        budget=RunBudget(
            session_daily_runs=_positive_int(
                SESSION_DAILY_RUNS_VARIABLE, DEFAULT_SESSION_DAILY_RUNS
            ),
            global_daily_runs=_positive_int(
                GLOBAL_DAILY_RUNS_VARIABLE, DEFAULT_GLOBAL_DAILY_RUNS
            ),
        ),
        # Only where there is something to fetch. A budget on a route that always refuses
        # would be counting refusals.
        fetch_budget=FetchBudget(
            session_daily_fetches=_positive_int(
                SESSION_DAILY_FETCHES_VARIABLE, DEFAULT_SESSION_DAILY_FETCHES
            ),
            global_daily_fetches=_positive_int(
                GLOBAL_DAILY_FETCHES_VARIABLE, DEFAULT_GLOBAL_DAILY_FETCHES
            ),
        )
        if source_hosts
        else None,
    )
    app.add_middleware(SessionCookieMiddleware)
    return app


def _source_hosts() -> frozenset[str]:
    """The hosts named by the deployment, refusing any this build cannot ask for.

    Refused at startup rather than at the first visitor who pastes an address on a host that
    was allowed and has no archive URL: the deployment named it, and the deployment is who
    can fix it.
    """

    raw = os.environ.get(SOURCE_HOSTS_VARIABLE, "").strip()
    if not raw:
        return frozenset()
    named = frozenset(part.strip().lower() for part in raw.split(",") if part.strip())
    unsupported = sorted(named - set(SUPPORTED_SOURCE_HOSTS))
    if unsupported:
        raise ConfigurationError(
            f"{SOURCE_HOSTS_VARIABLE} names {', '.join(unsupported)}, which this build does "
            f"not know how to fetch from. It knows {', '.join(SUPPORTED_SOURCE_HOSTS)}."
        )
    return named


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
