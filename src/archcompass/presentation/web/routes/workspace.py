"""What this workspace is, and what folders it can see.

Two routes that answer the questions a page asks before it can show anything: which
workspace am I in and which model does it reason with, and — on a local run only — what is
on this machine to point at.
"""

# Pyright cannot see FastAPI's decorator registration as a function reference.
# pyright: reportUnusedFunction=false

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter
from pydantic import Field

from archcompass.bootstrap import Runtime
from archcompass.domain.errors import PathValidationError
from archcompass.presentation.web.dependencies import RestrictionsDep, RuntimeDep
from archcompass.presentation.web.restrictions import HostedRestrictions
from archcompass.presentation.web.schemas import APIModel
from archcompass.records import ThinkingMode


class ModelIdentity(APIModel):
    provider: str
    model: str
    #: Whether this model reasons before answering: `true` required, `false` forbidden,
    #: absent left to the model. Part of what was chosen, so part of what is reported.
    thinking: ThinkingMode = None


class EmbeddingIdentity(APIModel):
    provider: str
    model: str
    dimensions: int


class WorkspaceModels(APIModel):
    """The selected reasoning model and its current health.

    Embedding identity is recorded with each review's retrieval provenance because it is a
    retriever concern configured independently from the reasoning model.
    """

    #: Absent where this workspace has not chosen a model and nothing configured one for it.
    #: A state to display rather than an error to raise: everything a review does not need a
    #: model for still works, and the interface asks for one where it is actually required.
    reasoning: ModelIdentity | None = None
    embedding: EmbeddingIdentity | None = None
    #: What the last run against this model said when it failed. Empty when the last run
    #: succeeded, when none has run, or once a probe has since found the provider healthy.
    #: The half of a model's health no probe can see: a spent quota lists perfectly well.
    failure: str = ""
    #: This process was told which model to use on its command line, so the model is not the
    #: workspace's to change while it lasts. The chooser says so instead of offering a
    #: choice that would be ignored.
    pinned: bool = False
    embedding_pinned: bool = False


class WorkspaceSummaryResponse(APIModel):
    #: Where this workspace's state lives, for a reader who may want to open it. A hosted
    #: workspace says what it is instead of where it is: its directory is named after the
    #: session cookie, and that cookie is HttpOnly precisely so a page cannot read it.
    workspace: str
    models: WorkspaceModels
    #: Whether this is the hosted demo, where the folder picker is off and only the bundled
    #: examples can be reviewed. Defaults to false, so a client written against a local
    #: workspace reads the same document it always did.
    hosted: bool = False
    #: The hosts this workspace will fetch a repository from, when it fetches rather than
    #: clones. Empty on a local workspace, which clones from anywhere its git can reach.
    #: Sent so the start step can name them in the field rather than leave a reader to find
    #: the list one refusal at a time.
    source_hosts: list[str] = Field(default_factory=list)


class DirectoryEntry(APIModel):
    """One subdirectory of the directory being browsed."""

    name: str
    path: str


class DirectoryListing(APIModel):
    """One local directory as a folder picker reads it: where it is, and what is under it."""

    path: str
    #: Null at the filesystem root, which is where climbing stops.
    parent: str | None
    directories: list[DirectoryEntry]


def routes() -> APIRouter:
    """The workspace summary and the folder picker."""

    router = APIRouter()

    @router.get("/api/workspace")
    def workspace_summary(
        runtime: RuntimeDep, hosted_mode: RestrictionsDep
    ) -> WorkspaceSummaryResponse:
        return describe_workspace(runtime, hosted_mode)

    @router.get("/api/filesystem/directories")
    def list_directories(
        hosted_mode: RestrictionsDep, path: str | None = None
    ) -> DirectoryListing:
        """Browse this machine's folders, so a repository root can be chosen rather than typed.

        With no `path`, the home directory. Read-only, one directory per request: only the
        names immediately inside it. Safe because the workspace binds 127.0.0.1 and serves the
        one person whose files these already are — which is exactly why the hosted demo, where
        neither half of that sentence holds, refuses it.
        """

        hosted_mode.browsing()
        return _directory_listing(Path(path) if path else Path.home())

    return router


def describe_workspace(
    runtime: Runtime, restrictions: HostedRestrictions
) -> WorkspaceSummaryResponse:
    """What this workspace is pointed at, without asking any provider anything.

    Read on every page load, which is why it costs one row and no network. Whether a
    model is reachable is a different question with a different price, and it is asked
    by the chooser at the moment someone is waiting to choose.
    """

    status = runtime.model_catalog_service.status()
    selection = status.selection
    embedding_status = runtime.embedding_model_service.status()
    embedding = embedding_status.selection
    return WorkspaceSummaryResponse(
        # The path is withheld on the hosted demo rather than shortened: it ends in the
        # session token, and a page that could read it could hand another visitor's
        # workspace to anyone.
        workspace="Hosted demo workspace" if restrictions.hosted else str(runtime.workspace),
        models=WorkspaceModels(
            reasoning=(
                ModelIdentity(
                    provider=status.provider,
                    model=status.model,
                    thinking=status.thinking,
                )
                if status.provider and status.model
                else None
            ),
            embedding=(
                EmbeddingIdentity(
                    provider=embedding.provider,
                    model=embedding.model,
                    dimensions=embedding.dimensions,
                )
                if embedding is not None
                else None
            ),
            failure=selection.failure_detail if selection else "",
            pinned=status.pinned,
            embedding_pinned=embedding_status.pinned,
        ),
        hosted=restrictions.hosted,
        source_hosts=sorted(runtime.source_service.hosts) if runtime.source_service else [],
    )


def _directory_listing(requested: Path) -> DirectoryListing:
    """One directory read for the picker, or a `PathValidationError` naming what went wrong.

    Read here rather than behind an application service: a listing holds no workspace state
    and is asked for by exactly one screen.

    Dot-directories are left out — `.git`, `.venv` and `.mypy_cache` are most of what sits in
    a project root and none is a repository anyone means to index. The picker keeps a path
    field for the reader who does.
    """

    try:
        directory = requested.expanduser().resolve(strict=True)
    except OSError as error:
        raise PathValidationError(f"There is nothing at {requested}.") from error
    if not directory.is_dir():
        raise PathValidationError(f"{directory} is a file, not a folder.")
    try:
        children = sorted(
            (child for child in directory.iterdir() if not child.name.startswith(".")),
            key=lambda child: child.name.casefold(),
        )
    except OSError as error:
        raise PathValidationError(f"{directory} cannot be read.") from error
    return DirectoryListing(
        path=str(directory),
        # A root is its own parent, which is how the filesystem says there is nowhere above it.
        parent=None if directory.parent == directory else str(directory.parent),
        directories=[
            DirectoryEntry(name=child.name, path=str(child))
            for child in children
            if child.is_dir()
        ],
    )
