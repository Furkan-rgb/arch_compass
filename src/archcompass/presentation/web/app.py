"""Assembly: one FastAPI app, built from the routers under `routes/`.

Nothing here decides what a route does. This module makes the app, puts on it the four
things every request is served through — the runtime provider, this deployment's
restrictions, its budgets, and its one indexing slot — installs the error handlers, includes
each router, and serves the built frontend. To find a route, open the module named after
what it is about.
"""

# Pyright cannot see FastAPI's decorator registration as a function reference.
# pyright: reportUnusedFunction=false

from __future__ import annotations

from pathlib import Path
from threading import BoundedSemaphore

from fastapi import FastAPI
from fastapi.responses import FileResponse, JSONResponse

from archcompass.bootstrap import Runtime
from archcompass.presentation.web.errors import install_error_handlers
from archcompass.presentation.web.restrictions import (
    FetchBudget,
    HostedRestrictions,
    RunBudget,
)
from archcompass.presentation.web.routes import (
    cases,
    decisions,
    examples,
    models,
    policies,
    repositories,
    review_conversations,
    reviews,
    workspace,
)
from archcompass.presentation.web.runtimes import (
    RuntimeProvider,
    SingleRuntimeProvider,
)
from archcompass.presentation.web.schemas import ProblemDetail, problem_responses

STATIC_DIR = Path(__file__).resolve().parent / "static"


def create_app(
    runtime: Runtime | RuntimeProvider,
    *,
    hosted: bool = False,
    budget: RunBudget | None = None,
    fetch_budget: FetchBudget | None = None,
) -> FastAPI:
    """The HTTP surface over one workspace, or over a provider that chooses one per request.

    A bare `Runtime` is still accepted because that is what a local run has: the CLI opens
    one workspace before the server starts, and wrapping it in a provider at every call site
    would be ceremony around a thing that never varies.
    """

    runtimes = (
        SingleRuntimeProvider(runtime) if isinstance(runtime, Runtime) else runtime
    )
    app = FastAPI(
        title="Arch Compass Local API",
        version="0.1.0",
        docs_url="/api/docs",
        openapi_url="/api/openapi.json",
        responses=problem_responses(422),
    )
    # On the app rather than in a closure so the dependencies can be module-level functions:
    # a dependency named in an annotation is resolved against module globals, and one
    # defined inside `create_app` cannot be referred to from a route's signature at all.
    app.state.runtimes = runtimes
    app.state.restrictions = HostedRestrictions(hosted=hosted)
    app.state.budget = budget
    app.state.fetch_budget = fetch_budget
    # One slot, and only where a machine is shared. `BoundedSemaphore` rather than a plain
    # one so a release that was never acquired is an error here rather than a slow leak of
    # permits that quietly stops serialising anything.
    app.state.index_lock = BoundedSemaphore(1) if hosted else None

    install_error_handlers(app)

    app.include_router(workspace.routes())
    app.include_router(models.routes())
    app.include_router(cases.routes())
    app.include_router(repositories.routes())
    app.include_router(examples.routes())
    app.include_router(reviews.routes())
    app.include_router(review_conversations.routes())
    app.include_router(decisions.routes())
    app.include_router(policies.routes())

    # Last, and in this order. Both are catch-alls, and Starlette matches in registration
    # order: anything under `/api` that no router claimed is a 404 about the API rather than
    # a page, and everything else is the single-page app.
    @app.api_route(
        "/api/{api_path:path}",
        methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        include_in_schema=False,
    )
    def unknown_api_route(api_path: str) -> JSONResponse:
        return JSONResponse(
            status_code=404,
            content=ProblemDetail(
                code="not_found",
                message=f"API route /api/{api_path} was not found",
            ).model_dump(mode="json"),
        )

    @app.get("/{path:path}", include_in_schema=False, response_model=None)
    def spa(path: str) -> FileResponse | JSONResponse:
        candidate = (STATIC_DIR / path).resolve()
        if path and candidate.is_file() and candidate.is_relative_to(STATIC_DIR.resolve()):
            return FileResponse(candidate, headers=_static_cache_headers(candidate))
        # A build asset that is not there is a 404, not the application.
        #
        # Falling through to `index.html` is right for `/reviews/abc`, which is a screen this
        # single-page app draws, and wrong for `/assets/run-page-CNwucsBs.js`, which is a
        # file. A tab open across a build asks for the chunk names it remembers, and a name
        # the build has removed is not there: answering it with 200 and a page of HTML is a
        # false statement about a resource, and it is the statement every cache, proxy and
        # access log downstream then reasons from.
        #
        # It is not what makes the reader's recovery work, which is what this comment used to
        # claim. Driven with this branch taken out: the browser writes `Failed to load module
        # script: Expected a JavaScript-or-Wasm module script but the server responded with a
        # MIME type of "text/html"` to the *console*, and the promise React sees still rejects
        # with `TypeError: Failed to fetch dynamically imported module: <url>` — which
        # `isChunkLoadError` in `frontend/src/app/error-boundary.tsx` matches either way, so
        # the same screen comes up offering the same "Reload the page" with the branch or
        # without it. What the 404 changes is the console: it names the file that is missing,
        # where the MIME complaint sends whoever is reading it after a content type instead.
        if path.startswith("assets/"):
            return JSONResponse(
                status_code=404,
                content=ProblemDetail(
                    code="not_found",
                    message=f"Build asset /{path} was not found",
                ).model_dump(mode="json"),
            )
        index = STATIC_DIR / "index.html"
        if index.is_file():
            return FileResponse(index, headers=_static_cache_headers(index))
        return JSONResponse(
            status_code=503,
            content=ProblemDetail(
                code="frontend_not_built",
                message="The Arch Compass frontend assets have not been built.",
            ).model_dump(mode="json"),
        )

    return app


def _static_cache_headers(served: Path) -> dict[str, str]:
    """How long a browser may keep a built file.

    The build gives every asset a content hash, so an asset's name changes the moment its
    bytes do and two builds' outputs can never collide. That is what makes the assets safe
    to keep forever — and makes `index.html`, which is the only file that knows the current
    names, the one file that must never be kept: a stale copy asks for hashed names the
    build has since removed, so the app half-loads from a cache the user cannot see and a
    plain reload does not clear.

    The hash is doing the work here on its own; the output directory is no longer emptied
    wholesale. `graceWindow` in `frontend/vite-plugins/grace-window.ts` keeps the previous build's
    chunks beside the new ones so a tab open across a build can still fetch what it asks
    for, which the content hash is precisely what permits.
    """

    if served.parent.name == "assets":
        return {"cache-control": "public, max-age=31536000, immutable"}
    return {"cache-control": "no-cache"}
