"""What every route is handed before it runs: a workspace, a deployment's rules, a budget.

Four dependencies and the annotations the routers spell them as. They are module-level
functions on purpose — a dependency named in an annotation is resolved against module
globals, so one defined inside `create_app` could not be referred to from a route's
signature at all, and everything they need is read off `app.state` instead.
"""

from __future__ import annotations

from collections.abc import Iterator
from threading import BoundedSemaphore
from typing import Annotated

from fastapi import Depends, Request

from archcompass.bootstrap import Runtime
from archcompass.presentation.web.restrictions import (
    FetchBudget,
    HostedRefusal,
    HostedRestrictions,
    RunBudget,
)
from archcompass.presentation.web.runtimes import RuntimeProvider, session_token


def acquire_runtime(request: Request) -> Runtime:
    """The workspace this request is served from.

    A dependency rather than something the routes close over, because which workspace that
    is stopped being a property of the process the moment one deployment served more than
    one visitor. Everything the provider decides — one workspace or one per session — it
    decides here, once per request.
    """

    provider: RuntimeProvider = request.app.state.runtimes
    return provider.acquire(request)


def acquire_restrictions(request: Request) -> HostedRestrictions:
    """What this deployment refuses, which is a property of the server and not the request."""

    restrictions: HostedRestrictions = request.app.state.restrictions
    return restrictions


def spend_model_budget(request: Request) -> None:
    """Admit one run against this session's and this instance's daily budget.

    Declared on the routes that make model calls rather than on all of them: reading a
    stored review costs nothing, and a demo that rationed reading would be measuring the
    wrong thing. Nothing is metered in local mode, where there is no budget object.
    """

    budget: RunBudget | None = request.app.state.budget
    if budget is not None:
        budget.admit(session_token(request))


def spend_fetch_budget(request: Request) -> None:
    """Admit one repository fetch against this session's and this instance's daily budget.

    Separate from the model budget because a fetch spends something else — bandwidth, and the
    room a container has left on a filesystem that is usually memory. Nothing is metered in
    local mode, where there is no budget object.
    """

    budget: FetchBudget | None = request.app.state.fetch_budget
    if budget is not None:
        budget.admit(session_token(request))


#: How long a request waits for the one indexing slot before giving up. Long enough that an
#: ordinary queue behind one repository clears, short enough that a caller is told rather
#: than left holding a connection open for the whole of somebody else's analysis.
INDEX_QUEUE_SECONDS = 90


def serialise_indexing(request: Request) -> Iterator[None]:
    """Let one analysis run at a time, where they share a machine.

    Analysis is the expensive thing this server does — a repository at the hosted size limit
    peaks in the hundreds of megabytes — and two of them overlapping is how a container sized
    for one of them dies. Cloud Run's own concurrency setting cannot express this: it cannot
    tell an index from somebody reading a stored review, and throttling both to protect one
    would make the demo feel broken for everybody who is only reading.

    Queued rather than refused, because the wait is seconds and the alternative is asking
    somebody to press the button again. Nothing is serialised where there is no lock, which
    is every local workspace: it has one user, who is not racing themselves.
    """

    lock: BoundedSemaphore | None = request.app.state.index_lock
    if lock is None:
        yield
        return
    if not lock.acquire(timeout=INDEX_QUEUE_SECONDS):
        raise HostedRefusal(
            503,
            "busy",
            "This demo is analysing another repository and only does one at a time. Try "
            "again in a moment.",
        )
    try:
        yield
    finally:
        lock.release()


RuntimeDep = Annotated[Runtime, Depends(acquire_runtime)]
RestrictionsDep = Annotated[HostedRestrictions, Depends(acquire_restrictions)]
#: What the routes that spend model tokens carry. A dependency with no value, so it is
#: declared beside the route's own decorator arguments rather than in its signature.
SpendsModelBudget = Depends(spend_model_budget)
#: The same, for the one route that puts a repository on this instance's disk.
SpendsFetchBudget = Depends(spend_fetch_budget)
#: What the routes that build an atlas carry, so two never build one at once.
SerialisesIndexing = Depends(serialise_indexing)
