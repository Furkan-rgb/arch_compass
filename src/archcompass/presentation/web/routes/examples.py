"""The repositories shipped with Arch Compass, so a first visit has something to review.

Two routes: what is bundled, and index one of them. No case comes back from either,
because none is shipped — the caller carries on through `/api/repositories/start` with the
root it was given, which is the same path a repository chosen in the folder picker takes.
"""

# Pyright cannot see FastAPI's decorator registration as a function reference.
# pyright: reportUnusedFunction=false

from __future__ import annotations

from fastapi import APIRouter

from archcompass.domain.atlas import AtlasVersion
from archcompass.presentation.web.dependencies import RuntimeDep, SerialisesIndexing
from archcompass.presentation.web.schemas import APIModel, problem_responses


class BundledExample(APIModel):
    """One example repository shipped with ArchCompass, ready to review.

    A repository and a name for it, and deliberately no case: the review asks what it needs
    to know, and the answers write the case. The repository path is absolute and resolved
    on the server, because the browser cannot know where the package was installed.
    """

    name: str
    title: str
    description: str
    repository_root: str


def routes() -> APIRouter:
    """Listing the bundled examples and loading one."""

    router = APIRouter()

    @router.get("/api/examples")
    def list_examples(runtime: RuntimeDep) -> list[BundledExample]:
        return [
            BundledExample(
                name=item.name,
                title=item.title,
                description=item.description,
                repository_root=item.repository_root,
            )
            for item in runtime.bundled_example_service.list()
        ]

    @router.post(
        "/api/examples/{name}/load",
        dependencies=[SerialisesIndexing],
        status_code=201,
        responses=problem_responses(404, 422),
    )
    def load_example(runtime: RuntimeDep, name: str) -> AtlasVersion:
        """Index the example's repository so it can be started from like any other.

        No case comes back, because none is shipped. The caller continues through
        `/api/repositories/start` with the root this answers with, which is the same path a
        repository chosen in the folder picker takes.
        """

        return runtime.bundled_example_service.load(name)

    return router
