"""The two shapes every route shares: the strict base model, and a refusal.

Everything else a route accepts or returns is declared beside the route itself, in its
module under `routes/`, because a request body is part of what that route is. What lives
here is only what more than one of them needs — and what the error handlers need, which is
why this module imports nothing from the rest of the package.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class APIModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ProblemDetail(APIModel):
    code: str
    message: str
    retryable: bool = False
    field_errors: list[str] = Field(default_factory=list[str])


_PROBLEM_RESPONSE_DESCRIPTIONS = {
    404: "The requested pinned resource was not found.",
    409: "The request conflicts with the current persisted revision or pinned state.",
    422: "The request or generated evidence did not satisfy the validated contract.",
    503: "A configured model provider is temporarily unavailable.",
}


def problem_responses(
    *statuses: Literal[404, 409, 422, 503],
) -> dict[int | str, dict[str, Any]]:
    """The `responses=` entry that documents which refusals a route can answer with."""

    return {
        status: {
            "model": ProblemDetail,
            "description": _PROBLEM_RESPONSE_DESCRIPTIONS[status],
        }
        for status in statuses
    }
