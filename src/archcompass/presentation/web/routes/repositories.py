"""Getting code onto this machine, indexing it, and asking the atlas about it.

Everything upstream of a review. A repository arrives — cloned, fetched, or already lying
on disk — is analysed into an atlas, and is then queried: its shape, its hotspots, one
node, the neighbourhood around a review's boundaries. The queries are here rather than in a
module of their own because every one of them is a question about a repository, and
`/api/repositories/...` is the path a caller already holds.
"""

# Pyright cannot see FastAPI's decorator registration as a function reference.
# pyright: reportUnusedFunction=false

from __future__ import annotations

from pathlib import Path
from typing import Annotated, Literal, cast

from fastapi import APIRouter, Query
from pydantic import Field, model_validator

from archcompass.application.repository_tree import folder_tree
from archcompass.domain.atlas import AtlasQueryResult, AtlasVersion
from archcompass.domain.case import CaseRevision
from archcompass.domain.checkout import CheckoutRefresh, RepositoryCheckout
from archcompass.domain.lineage import RepositoryBranch
from archcompass.domain.scope import RepositoryFolderTree
from archcompass.domain.workspace import RepositorySummary
from archcompass.presentation.web.dependencies import (
    RestrictionsDep,
    RuntimeDep,
    SerialisesIndexing,
    SpendsFetchBudget,
)
from archcompass.presentation.web.schemas import APIModel, problem_responses


class RepositoryPathRequest(APIModel):
    root_path: str = Field(min_length=1)


class RepositoryIndexRequest(RepositoryPathRequest):
    """A repository to index, and optionally the folders to leave out of the analysis.

    The scope is optional and stays optional. A client that has never heard of it sends the
    payload it always sent and gets the scope this repository was last indexed under — which
    is what somebody who narrowed a review and then pressed re-index means, and is also why
    omitting the field cannot mean "all of it". Saying "all of it" is sending `[]`.
    """

    excluded_paths: list[str] | None = None


class RepositoryCheckoutRequest(APIModel):
    """A repository named by address, or by a path on this machine.

    One field for both because they are one question — "which repository" — and asking the
    caller to say which kind they are holding would only make them classify a string the
    service classifies better.
    """

    url: str = Field(min_length=1)
    #: The branch to review. Left out, the remote's own default is used, which is what
    #: someone pasting an address without further thought means.
    branch: str | None = None


class StartFromRepositoryRequest(APIModel):
    """Which repository to open, and whether to carry on from where it was left.

    Continuing is the default because a repeat visit almost always means the same
    conversation: the questions the last run asked and the answers the reader gave are on
    that case, and starting beside them would ask for them again. Starting clean is the
    stated exception — a different question about the same code — and it has to be stated
    rather than reached by deleting something.
    """

    root_path: str = Field(min_length=1)
    start_clean: bool = False


class AtlasExploreRequest(APIModel):
    root_path: str = Field(min_length=1)
    operation: Literal[
        "children",
        "dependencies",
        "dependants",
        "callers",
        "implementations",
        "tests",
        "forward_neighbourhood",
        "reverse_neighbourhood",
        "search",
        "shortest_path",
        "cycles",
        "signals",
    ]
    node_id: str | None = None
    target_id: str | None = None
    terms: list[str] = Field(default_factory=list, max_length=10)
    signal_codes: list[str] = Field(default_factory=list, max_length=10)
    depth: int = Field(default=1, ge=1, le=5)
    limit: int = Field(default=50, ge=1, le=100)

    @model_validator(mode="after")
    def validate_operation_fields(self) -> AtlasExploreRequest:
        if self.operation == "search" and not self.terms:
            raise ValueError("search requires at least one term")
        if self.operation not in {"search", "cycles", "signals"} and self.node_id is None:
            raise ValueError(f"{self.operation} requires node_id")
        if self.operation == "shortest_path" and self.target_id is None:
            raise ValueError("shortest_path requires target_id")
        return self


class ReviewContextRequest(APIModel):
    """The nodes a map is being drawn around, asked for together.

    Together rather than one at a time because a node's edges are only drawable once its
    neighbours are known, and a client that asked per node would be told about edges whose
    other end it never received.
    """

    root_path: str = Field(min_length=1)
    node_ids: list[str] = Field(min_length=1, max_length=40)
    limit: int = Field(default=25, ge=1, le=100)


def routes() -> APIRouter:
    """Checkout, indexing, and every atlas query a page can ask."""

    router = APIRouter()

    @router.get("/api/repositories")
    def list_repositories(
        runtime: RuntimeDep,
        limit: Annotated[int, Query(ge=1, le=500)] = 100,
    ) -> list[RepositorySummary]:
        return runtime.repository_service.list(limit=limit)

    @router.get("/api/branches")
    def list_branches(runtime: RuntimeDep) -> list[RepositoryBranch]:
        """Every branch lineage this workspace has seen, with the repository it belongs to.

        The listing above answers "which checkouts have been indexed", which is a question
        about this machine. This one answers "which repositories and lines of work does this
        workspace know about", which is the question that survives the checkout moving.
        """

        return runtime.repository_service.branches()

    @router.post(
        "/api/repositories/index",
        status_code=201,
        dependencies=[SerialisesIndexing],
    )
    def index_repository(
        runtime: RuntimeDep,
        hosted_mode: RestrictionsDep,
        request: RepositoryIndexRequest,
    ) -> AtlasVersion:
        return runtime.repository_service.index(
            hosted_mode.repository_root(Path(request.root_path), runtime),
            excluded_paths=request.excluded_paths,
        )

    @router.post("/api/repositories/tree", responses=problem_responses(422))
    def repository_tree(
        runtime: RuntimeDep,
        hosted_mode: RestrictionsDep,
        request: RepositoryPathRequest,
    ) -> RepositoryFolderTree:
        """What is in this repository, two levels deep, so a caller can choose what to skip.

        Validated through the same restriction as indexing, because it reads the same
        directories: a route that would list any folder on the server is the folder picker
        this deployment already refuses, wearing a different name.

        Spends no budget. Walking a directory costs neither model tokens nor disk, and the
        listing exists to make a *smaller* analysis possible — rationing it would ration the
        cheap step that avoids the expensive one.
        """

        return folder_tree(hosted_mode.repository_root(Path(request.root_path), runtime))

    # 201 for both halves of what this does. A repeat visit refreshes a checkout rather than
    # cloning one, but it still materialises the state the response names — the folder is on
    # disk because this call put it there — and `created` on the body is what distinguishes
    # the two. Narrowing the status to 200 for the refresh would break every client for the
    # sake of a distinction the payload already carries.
    @router.post(
        "/api/repositories/checkout",
        status_code=201,
        responses=problem_responses(409, 422),
        dependencies=[SpendsFetchBudget],
    )
    def checkout_repository(
        runtime: RuntimeDep,
        hosted_mode: RestrictionsDep,
        request: RepositoryCheckoutRequest,
    ) -> RepositoryCheckout:
        """Make the named repository available on this machine, and say where it landed.

        Nothing is indexed here. The answer is a folder, which is what `/api/repositories/index`
        and `/api/repositories/start` have always taken — so a repository pasted as a URL joins
        the existing flow at exactly the point a repository chosen with the picker does.

        201 for a checkout that was updated as much as for one that was cloned: something was
        written to disk either way, and `created` says which of the two happened.
        """

        # A workspace that was given hosts to fetch from has no business running git: the
        # whole reason it exists is that an extracted archive cannot carry hooks, submodules,
        # filters, credentials or a transport nobody asked for. Checked here rather than
        # inside the checkout service, because which of the two ways a repository arrives is
        # a property of the deployment, and the deployment is what this layer knows.
        source_service = runtime.source_service
        if source_service is not None:
            return source_service.fetch(request.url, branch=request.branch)
        hosted_mode.checkout()
        return runtime.checkout_service.checkout(request.url, branch=request.branch)

    @router.post(
        "/api/repositories/refresh",
        responses=problem_responses(409, 422),
    )
    def refresh_repository(
        runtime: RuntimeDep,
        hosted_mode: RestrictionsDep,
        request: RepositoryPathRequest,
    ) -> CheckoutRefresh:
        """Pull whatever has landed on the remote since, for a folder Arch Compass cloned.

        Takes a path rather than an address because a path is what a page reviewing a
        repository has: the URL was typed once, at the start, and nothing downstream of that
        carries it. The address is read back out of the checkout instead.

        A folder that is not one of ours answers rather than refuses — `managed: false`, and
        nothing written. That is the ordinary case for a repository reviewed where it lies,
        and the caller is meant to carry on and run its review against what is on disk.

        The hosted restriction is the checkout one, unchanged: a demo that will not clone a
        repository will not fetch into one either, and it has no managed checkouts for this
        to be about in the first place.
        """

        # Nothing to bring up to date, and that is an answer rather than a refusal. Every run
        # begins by asking for this unconditionally — it is how a managed checkout is made
        # current before it is reviewed — so a workspace whose repositories are extracted
        # archives has to say "nothing was touched" here, exactly as it does for somebody
        # else's working copy. Refusing would fail every review on the way to its first
        # model call. Asking for it again is what re-fetches: paste the address.
        source_service = runtime.source_service
        if source_service is not None:
            # The one place a run can notice that its code is gone, and the one place that
            # can do something about it. This workspace deletes the least recently used
            # source to stay inside its memory, so a repository reviewed an hour ago may
            # have been swept since — and every run begins by asking for this, which makes
            # it exactly where "bring the code up to date" should mean "and bring it back
            # if it is not there". Fetched again at the revision it was served the first
            # time, so the line numbers the atlas holds still point at the same code.
            restored = source_service.restore(Path(request.root_path))
            return CheckoutRefresh(
                root_path=request.root_path, managed=restored, updated=False
            )
        hosted_mode.checkout()
        return runtime.checkout_service.refresh(request.root_path)

    @router.post(
        "/api/repositories/start",
        responses=problem_responses(404, 422),
        dependencies=[SerialisesIndexing],
    )
    def start_from_repository(
        runtime: RuntimeDep,
        hosted_mode: RestrictionsDep,
        request: StartFromRepositoryRequest,
    ) -> CaseRevision:
        """Index a repository and answer with the case to review it against.

        The whole of the first step for someone who has not authored a case. Both halves
        happen here so the flow either produces something reviewable or fails outright,
        rather than leaving a case pointing at an atlas that was never built. A bundled
        example arrives here too, once its repository has been indexed.

        A first visit opens a case with nothing written in it yet. A repeat visit continues
        the newest case reviewed on this **branch**, so the answers the reader has already
        given are still there to be judged against — `start_clean: true` is how they say the
        next run is about a different question and should begin with an empty case again.

        The branch rather than the repository, because a branch is the scope everything
        durable lives in: its standings, its revisions, and its case. Two branches of one
        repository are two pieces of work, and a feature branch inheriting `main`'s case would
        be handed answers about code it has not written.

        Which case that is, is the application's to decide and not the client's: a browser
        that picked one would be reading the review history to guess at the case that history
        is about, and two clients would guess differently.
        """

        root = hosted_mode.repository_root(Path(request.root_path), runtime)
        version = runtime.repository_service.index(root)
        if request.start_clean:
            return runtime.case_service.start_from_repository(root)
        return runtime.case_service.continue_from_repository(
            root, branch_id=version.branch_id
        )

    @router.get("/api/repositories/summary")
    def repository_summary(runtime: RuntimeDep, root_path: str) -> AtlasQueryResult:
        return runtime.atlas_service.summary(Path(root_path))

    @router.get("/api/repositories/hotspots")
    def repository_hotspots(
        runtime: RuntimeDep,
        root_path: str,
        metric: str = "reverse_dependency_reach",
    ) -> AtlasQueryResult:
        return runtime.atlas_service.hotspots(Path(root_path), metric)

    @router.get("/api/repositories/inspect")
    def repository_inspect(runtime: RuntimeDep, root_path: str, node_id: str) -> AtlasQueryResult:
        return runtime.atlas_service.inspect(Path(root_path), node_id)

    @router.post("/api/repositories/review-context")
    def repository_review_context(
        runtime: RuntimeDep, request: ReviewContextRequest
    ) -> AtlasQueryResult:
        """The subgraph around a review's boundaries, for the map that opens beside it.

        Ids the atlas no longer holds are skipped rather than refused — the result names the
        ones it found, so a map drawn from a rebuilt atlas is short a node rather than absent.
        """

        return runtime.atlas_service.review_context(
            Path(request.root_path),
            request.node_ids,
            limit=request.limit,
        )

    @router.post("/api/repositories/explore")
    def repository_explore(runtime: RuntimeDep, request: AtlasExploreRequest) -> AtlasQueryResult:
        repository = Path(request.root_path)
        if request.operation == "search":
            return runtime.atlas_service.search(
                repository, request.terms, limit=request.limit
            )
        if request.operation == "cycles":
            return runtime.atlas_service.cycles(repository, limit=request.limit)
        if request.operation == "signals":
            return runtime.atlas_service.signals(
                repository,
                codes=request.signal_codes,
                limit=request.limit,
            )
        assert request.node_id is not None
        if request.operation == "children":
            return runtime.atlas_service.children(
                repository, request.node_id, limit=request.limit
            )
        if request.operation == "shortest_path":
            assert request.target_id is not None
            return runtime.atlas_service.shortest_path(
                repository, request.node_id, request.target_id
            )
        if request.operation in {"forward_neighbourhood", "reverse_neighbourhood"}:
            return runtime.atlas_service.neighbourhood(
                repository,
                request.node_id,
                direction=cast(
                    Literal["forward_neighbourhood", "reverse_neighbourhood"],
                    request.operation,
                ),
                depth=request.depth,
                limit=request.limit,
            )
        relation_kinds = {
            "dependencies": "direct_dependencies",
            "dependants": "direct_dependants",
            "callers": "known_callers",
            "implementations": "implementations",
            "tests": "related_tests",
        }
        return runtime.atlas_service.relationships(
            repository,
            request.node_id,
            kind=cast(
                Literal[
                    "direct_dependencies",
                    "direct_dependants",
                    "known_callers",
                    "implementations",
                    "related_tests",
                ],
                relation_kinds[request.operation],
            ),
            limit=request.limit,
        )

    return router
