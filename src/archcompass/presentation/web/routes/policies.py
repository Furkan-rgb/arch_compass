"""The rules a review judges against: what is in the corpus, and where it came from.

Two kinds of policy meet here. A source is a folder of Markdown on this machine, registered
so every review reads it; a written policy is one this workspace owns, saved as a real file
in the same format so nothing about it is second-class. Rewriting anything read from
elsewhere is a conflict, not an edit.
"""

# Pyright cannot see FastAPI's decorator registration as a function reference.
# pyright: reportUnusedFunction=false

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Response
from pydantic import Field

from archcompass.boundary.policy import (
    PolicyDocument,
    PolicyDraft,
    PolicySourceRegistration,
)
from archcompass.presentation.web.dependencies import RestrictionsDep, RuntimeDep
from archcompass.presentation.web.schemas import APIModel, problem_responses


class PolicySourceRequest(APIModel):
    source: str = Field(min_length=1)


class PolicySourceRemovalResponse(APIModel):
    removed: bool


def routes() -> APIRouter:
    """Reading the corpus, registering folders it is read from, and authoring policies."""

    router = APIRouter()

    @router.get("/api/policies")
    def list_policies(
        runtime: RuntimeDep, repository_root: str | None = None
    ) -> list[PolicyDocument]:
        return runtime.policy_service.catalog(
            repository_root=(
                Path(repository_root) if repository_root is not None else None
            )
        )

    @router.get("/api/policies/sources")
    def list_policy_sources(runtime: RuntimeDep) -> list[PolicySourceRegistration]:
        return runtime.policy_service.list_sources()

    @router.post("/api/policies/sources", status_code=201)
    def add_policy_source(
        runtime: RuntimeDep,
        hosted_mode: RestrictionsDep,
        request: PolicySourceRequest,
    ) -> PolicySourceRegistration:
        """Read a folder of Markdown policies from this machine into every review.

        Refused on the hosted demo: the folder named would be one of the server's. Writing
        policies here is not — those live in the session's own workspace, and `POST
        /api/policies` still answers.
        """

        hosted_mode.policy_source()
        return runtime.policy_service.add_source(Path(request.source))

    @router.delete("/api/policies/sources")
    def remove_policy_source(runtime: RuntimeDep, source: str) -> PolicySourceRemovalResponse:
        return PolicySourceRemovalResponse(
            removed=runtime.policy_service.remove_source(Path(source))
        )

    @router.post("/api/policies", status_code=201, responses=problem_responses(409, 422))
    def create_policy(runtime: RuntimeDep, draft: PolicyDraft) -> PolicyDocument:
        """Write a policy of this workspace's own into `<workspace>/.archcompass/policies`.

        A real Markdown file in the format every other policy is in, so nothing about it is
        second-class: the next review reads it from disk with the rest of the corpus, and it
        remains editable in an editor after this page has forgotten about it.
        """

        return runtime.policy_service.create(draft)

    @router.put(
        "/api/policies/{policy_id}",
        responses=problem_responses(404, 409, 422),
    )
    def update_policy(runtime: RuntimeDep, policy_id: str, draft: PolicyDraft) -> PolicyDocument:
        """Rewrite one of this workspace's policies. Anything read from elsewhere is a 409."""

        return runtime.policy_service.update(policy_id, draft)

    @router.delete(
        "/api/policies/{policy_id}",
        status_code=204,
        responses=problem_responses(404, 409),
    )
    def delete_policy(runtime: RuntimeDep, policy_id: str) -> Response:
        runtime.policy_service.delete(policy_id)
        return Response(status_code=204)

    @router.get("/api/policies/{policy_id}", responses=problem_responses(404))
    def get_policy(
        runtime: RuntimeDep,
        policy_id: str, repository_root: str | None = None
    ) -> PolicyDocument:
        return runtime.policy_service.get(
            policy_id,
            repository_root=(
                Path(repository_root) if repository_root is not None else None
            ),
        )

    return router
