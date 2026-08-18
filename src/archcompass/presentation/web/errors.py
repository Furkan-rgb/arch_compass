"""How a raised error becomes a status code and a sentence somebody can act on.

One classifier and three handlers. `classify_error` is the single table mapping the
domain's exceptions onto HTTP, and it is used twice: by the handler that turns a raised
error into a response, and by the streams, which are already a 200 by the time they fail
and so have to write the same verdict into the body instead.
"""

# Pyright cannot see FastAPI's decorator registration as a function reference.
# pyright: reportUnusedFunction=false

from __future__ import annotations

import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from archcompass.domain.errors import (
    ArchCompassError,
    AtlasNotFoundError,
    BranchNotFoundError,
    CaseNotFoundError,
    CaseRevisionConflictError,
    CaseValidationError,
    ConversationNotFoundError,
    ConversationRetrievalError,
    ConversationRevisionConflictError,
    ConversationValidationError,
    ExampleNotFoundError,
    LegacySchemaError,
    ModelOutputValidationError,
    NoReasoningModelSelectedError,
    NothingToReviewError,
    PathValidationError,
    PersistenceError,
    PolicyConflictError,
    PolicyFormatError,
    PolicyNotFoundError,
    ProviderError,
    RepositoryCheckoutError,
    ReviewHasNoReportError,
    ReviewNotCancellableError,
    ReviewNotFoundError,
    ReviewStillRunningError,
    StaleAtlasError,
)
from archcompass.presentation.web.restrictions import HostedRefusal
from archcompass.presentation.web.schemas import ProblemDetail

#: What a deployment learns from, which is not the same as what it shows a visitor. A demo
#: that only ever answers "this repository is more than I will analyse" tells the person in
#: front of it something useful and tells the people running it nothing: not how often it
#: happens, not by how much, and so not whether the limit is in the right place or the
#: analyser is in the wrong shape.
#:
#: One line per refusal, to standard output, which is where a container's logs are read from.
#: No counters, no metrics endpoint, no store: the question is "is this limit the thing
#: standing between visitors and a review", and a week of lines answers it.
_refusals = logging.getLogger("archcompass.refusals")


def log_refusal(request: Request, code: str, message: str) -> None:
    """Say what was declined and why, in the words the visitor was given.

    The message carries the numbers — how many megabytes, how many modules, which address —
    because they were written for a reader and are the same facts a deployment wants. Logged
    rather than parsed into fields for the same reason nothing here is counted: a line is
    enough to answer the question this exists to answer.
    """

    _refusals.info(
        "refused %s %s: %s — %s", request.method, request.url.path, code, message
    )


def install_error_handlers(app: FastAPI) -> None:
    """Teach one app to answer every raised error with a `ProblemDetail`.

    Three handlers, because there are three kinds of refusal: what this deployment will not
    do, what the workspace's state will not allow, and what the request itself failed to be.
    """

    @app.exception_handler(HostedRefusal)
    async def hosted_refusal(request: Request, error: HostedRefusal) -> JSONResponse:
        log_refusal(request, error.code, error.message)
        return JSONResponse(
            status_code=error.status_code,
            content=ProblemDetail(
                code=error.code,
                message=error.message,
            ).model_dump(mode="json"),
        )

    @app.exception_handler(ArchCompassError)
    async def archcompass_error(
        request: Request, error: ArchCompassError
    ) -> JSONResponse:
        status, code, retryable = classify_error(error)
        # 4xx only. A 500 is this program being wrong and belongs in a traceback; a 422 or a
        # 409 is the workspace declining on purpose, which is the thing worth counting.
        if 400 <= status < 500:
            log_refusal(request, code, str(error))
        return JSONResponse(
            status_code=status,
            content=ProblemDetail(
                code=code,
                message=str(error),
                retryable=retryable,
            ).model_dump(mode="json"),
        )

    @app.exception_handler(RequestValidationError)
    async def request_validation_error(
        _request: Request, error: RequestValidationError
    ) -> JSONResponse:
        fields = [
            ".".join(str(item) for item in detail["loc"])
            + ": "
            + str(detail["msg"])
            for detail in error.errors()
        ]
        # Include field paths in the message so a caller can immediately distinguish a
        # stale client contract from a malformed value.
        detail = f" ({'; '.join(fields)})" if fields else ""
        return JSONResponse(
            status_code=422,
            content=ProblemDetail(
                code="validation_error",
                message=f"The request did not match the API contract{detail}.",
                field_errors=fields,
            ).model_dump(mode="json"),
        )


def classify_error(error: ArchCompassError) -> tuple[int, str, bool]:
    """One domain error as a status code, a stable code string, and whether retrying helps."""

    if isinstance(error, NothingToReviewError):
        # Its own code, because it is not a fault to fix: the request was understood and
        # the answer is that there is nothing to do. A client can tell it apart from every
        # conflict that asks the caller to change something.
        return 409, "nothing_changed", False
    if isinstance(
        error,
        (
            CaseNotFoundError,
            ExampleNotFoundError,
            AtlasNotFoundError,
            ReviewNotFoundError,
            PolicyNotFoundError,
            ConversationNotFoundError,
            BranchNotFoundError,
        ),
    ):
        return 404, "not_found", False
    if isinstance(
        error,
        (
            CaseRevisionConflictError,
            ConversationRevisionConflictError,
            PolicyConflictError,
            ReviewHasNoReportError,
            ReviewNotCancellableError,
            ReviewStillRunningError,
            StaleAtlasError,
        ),
    ):
        # Retryable only where repeating the request could succeed. A review that has
        # already finished will not start running again, so cancelling it never will.
        return 409, "state_conflict", isinstance(
            error,
            (ConversationRevisionConflictError, ReviewStillRunningError, StaleAtlasError),
        )
    if isinstance(
        error,
        (
            CaseValidationError,
            PathValidationError,
            PolicyFormatError,
            ModelOutputValidationError,
            ConversationValidationError,
            ConversationRetrievalError,
        ),
    ):
        return 422, "validation_error", False
    if isinstance(error, RepositoryCheckoutError):
        # Not 422: the request is well formed and this is a true statement about the
        # repository. Retryable, because most of what reaches here is a remote that was
        # unreachable at the moment it was asked.
        return 409, "checkout_failed", True
    if isinstance(error, NoReasoningModelSelectedError):
        # 409 rather than 503: nothing is unavailable, and nothing about the request is
        # malformed — the workspace simply has not chosen yet.
        return 409, "no_model_selected", False
    if isinstance(error, ProviderError):
        return 503, "provider_unavailable", True
    if isinstance(error, LegacySchemaError):
        return 409, "legacy_schema", False
    if isinstance(error, PersistenceError):
        return 500, "persistence_error", False
    return 400, "archcompass_error", False
