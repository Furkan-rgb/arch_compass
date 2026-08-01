"""ArchCompass command-line presentation adapter."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated

import typer
import yaml
from pydantic import ValidationError

from archcompass.application.review_rendering import render_review
from archcompass.application.safety import (
    validate_workspace_repository_separation,
)
from archcompass.bootstrap import (
    Runtime,
    build_runtime,
)
from archcompass.bootstrap import (
    initialize_workspace as initialize_workspace_runtime,
)
from archcompass.domain.case import ArchitectureCase, CaseUpdate
from archcompass.domain.errors import ArchCompassError

app = typer.Typer(
    name="archcompass",
    help="Evidence-grounded software architecture advice.",
    no_args_is_help=True,
)
policies_app = typer.Typer(help="Build and inspect architectural policies.")
policy_sources_app = typer.Typer(help="Register persistent workspace policy sources.")
repo_app = typer.Typer(help="Index a Python repository.")
atlas_app = typer.Typer(help="Query repository atlases.")
case_app = typer.Typer(help="Create and revise architecture cases.")
reviews_app = typer.Typer(help="Inspect immutable boundary reviews.")
app.add_typer(policies_app, name="policies")
policies_app.add_typer(policy_sources_app, name="sources")
app.add_typer(repo_app, name="repo")
app.add_typer(atlas_app, name="atlas")
app.add_typer(case_app, name="case")
app.add_typer(reviews_app, name="reviews")


class CLIState:
    def __init__(self, workspace: Path, models_config: Path | None) -> None:
        self.workspace = workspace
        self.models_config = models_config
        self._runtime: Runtime | None = None

    @property
    def runtime(self) -> Runtime:
        if self._runtime is None:
            self._runtime = build_runtime(
                self.workspace, models_config=self.models_config
            )
        return self._runtime

    def runtime_for_repository(self, repository: Path) -> Runtime:
        if self._runtime is None:
            self._runtime = build_runtime(
                self.workspace,
                models_config=self.models_config,
                repository=repository,
            )
        else:
            validate_workspace_repository_separation(self.workspace, repository)
        return self._runtime

    def set_runtime(self, runtime: Runtime) -> None:
        self._runtime = runtime


@app.callback()
def root_callback(
    context: typer.Context,
    workspace: Annotated[
        Path,
        typer.Option(
            "--workspace",
            help="Workspace containing config, state, and reports.",
            file_okay=False,
        ),
    ] = Path("."),
    models_config: Annotated[
        Path | None,
        typer.Option("--models-config", help="Explicit model configuration path."),
    ] = None,
) -> None:
    context.obj = CLIState(workspace.expanduser().resolve(), models_config)


@app.command("init")
def initialize(context: typer.Context) -> None:
    """Create missing workspace configuration and database without overwriting files."""
    state = _state(context)
    result = initialize_workspace_runtime(
        state.workspace,
        models_config=state.models_config,
    )
    state.set_runtime(result.runtime)
    typer.echo(f"Workspace ready: {result.runtime.workspace}")
    for path in result.created_paths:
        typer.echo(f"Created {path}")


@app.command("web")
def web(
    context: typer.Context,
    workspace: Annotated[
        Path | None,
        typer.Option(
            "--workspace",
            help=(
                "Workspace containing config, state, and reports. "
                "Defaults to the current directory (.)."
            ),
            file_okay=False,
        ),
    ] = None,
    port: Annotated[
        int,
        typer.Option(
            "--port",
            min=1,
            max=65535,
            help="Loopback port for the local web workspace.",
        ),
    ] = 8765,
    open_browser: Annotated[
        bool,
        typer.Option(
            "--open/--no-open",
            help="Open the local workspace in the default browser.",
        ),
    ] = True,
) -> None:
    """Launch the local Arch Compass browser workspace."""
    import threading
    import webbrowser

    import uvicorn

    from archcompass.presentation.web import create_app

    state = _state(context)
    selected_workspace = (
        workspace.expanduser().resolve() if workspace is not None else state.workspace
    )
    result = initialize_workspace_runtime(
        selected_workspace,
        models_config=state.models_config,
        # No configuration is written for a workspace that has none. The interface asks for
        # a model where one is actually needed and offers only models a reachable provider
        # has, so a seeded file would put a provider in the chip that is not there — which
        # is the ordinary case for anything hosted. `archcompass init` still writes one.
        write_default_config=False,
    )
    state.set_runtime(result.runtime)
    url = f"http://127.0.0.1:{port}"
    typer.echo(f"Arch Compass web workspace: {url}")
    for path in result.created_paths:
        typer.echo(f"Created {path}")
    if open_browser:
        threading.Timer(0.75, lambda: webbrowser.open(url)).start()
    uvicorn.run(
        create_app(result.runtime),
        host="127.0.0.1",
        port=port,
        access_log=False,
    )


# No `rebuild`. Policies are read from their sources whenever they are asked for, so there
# is no index to bring up to date and a command to do it would be a step that changes
# nothing (ADR 0013). Editing a policy on disk is enough.


@policies_app.command("list")
def policies_list(
    context: typer.Context,
    repo: Annotated[
        Path | None,
        typer.Option("--repo", help="Also read <repo>/.archcompass/policies."),
    ] = None,
) -> None:
    catalog = _state(context).runtime.policy_service.catalog(repository_root=repo)
    for policy in catalog:
        typer.echo(f"{policy.id}\t{policy.scope}\t{policy.strength}\t{policy.title}")


@policies_app.command("show")
def policies_show(
    context: typer.Context,
    policy_id: str,
    repo: Annotated[
        Path | None,
        typer.Option("--repo", help="Also read <repo>/.archcompass/policies."),
    ] = None,
) -> None:
    policy = _state(context).runtime.policy_service.get(policy_id, repository_root=repo)
    typer.echo(policy.model_dump_json(indent=2))


@policy_sources_app.command("add")
def policy_sources_add(context: typer.Context, source: Path) -> None:
    registration = _state(context).runtime.policy_service.add_source(source)
    typer.echo(registration.model_dump_json(indent=2))


@policy_sources_app.command("remove")
def policy_sources_remove(context: typer.Context, source: Path) -> None:
    removed = _state(context).runtime.policy_service.remove_source(source)
    if not removed:
        raise typer.BadParameter(f"Policy source is not registered: {source}")
    typer.echo(f"Removed {source.expanduser().resolve(strict=False)}")


@policy_sources_app.command("list")
def policy_sources_list(context: typer.Context) -> None:
    registrations = _state(context).runtime.policy_service.list_sources()
    typer.echo(
        json.dumps(
            [item.model_dump(mode="json") for item in registrations],
            indent=2,
        )
    )


@repo_app.command("index")
def repo_index(context: typer.Context, path: Path) -> None:
    version = _state(context).runtime_for_repository(path).repository_service.index(path)
    typer.echo(version.model_dump_json(indent=2))


@atlas_app.command("summary")
def atlas_summary(context: typer.Context, path: Path) -> None:
    result = _state(context).runtime_for_repository(path).atlas_service.summary(path)
    typer.echo(result.model_dump_json(indent=2))


@atlas_app.command("inspect")
def atlas_inspect(
    context: typer.Context,
    path: Path,
    node: Annotated[str, typer.Option("--node", help="Stable atlas node ID.")],
) -> None:
    result = _state(context).runtime_for_repository(path).atlas_service.inspect(
        path,
        node,
    )
    typer.echo(result.model_dump_json(indent=2))


@atlas_app.command("hotspots")
def atlas_hotspots(
    context: typer.Context,
    path: Path,
    metric: Annotated[
        str, typer.Option("--metric", help="One documented metric field name.")
    ] = "reverse_dependency_reach",
) -> None:
    result = _state(context).runtime_for_repository(path).atlas_service.hotspots(
        path,
        metric,
    )
    typer.echo(result.model_dump_json(indent=2))


@case_app.command("create")
def case_create(
    context: typer.Context,
    source: Annotated[Path, typer.Option("--from", help="ArchitectureCase YAML file.")],
) -> None:
    case = ArchitectureCase.model_validate(_read_yaml(source))
    revision = _state(context).runtime.case_service.create(case)
    typer.echo(revision.model_dump_json(indent=2))


@case_app.command("show")
def case_show(context: typer.Context, case_id: str) -> None:
    revision = _state(context).runtime.case_service.show(case_id)
    typer.echo(revision.model_dump_json(indent=2))


@case_app.command("update")
def case_update(
    context: typer.Context,
    case_id: str,
    source: Annotated[Path, typer.Option("--from", help="Partial case update YAML file.")],
) -> None:
    update = CaseUpdate.model_validate(_read_yaml(source))
    revision = _state(context).runtime.case_service.update(case_id, update)
    typer.echo(revision.model_dump_json(indent=2))


@case_app.command("history")
def case_history(context: typer.Context, case_id: str) -> None:
    revisions = _state(context).runtime.case_service.history(case_id)
    typer.echo(
        json.dumps(
            [revision.model_dump(mode="json") for revision in revisions],
            indent=2,
        )
    )


@app.command("review")
def review(
    context: typer.Context,
    case_id: str,
    repo: Annotated[
        Path,
        typer.Option("--repo", help="Repository whose indexed atlas should be reviewed."),
    ],
    answers: Annotated[
        str | None,
        typer.Option(
            "--answers",
            help=(
                "The review this run answers. Judges and concludes without asking again, "
                "against the case revision your answers created."
            ),
        ),
    ] = None,
    as_json: Annotated[
        bool, typer.Option("--json", help="Print the stored review instead of its Markdown.")
    ] = False,
) -> None:
    """Judge every boundary the detector finds in a repository against one case."""

    state = _state(context)
    stored = state.runtime_for_repository(repo).review_service.review(
        case_id,
        repository_root=repo,
        elicited_from=answers,
    )
    typer.echo(stored.model_dump_json(indent=2) if as_json else render_review(stored))
    # A run that stopped to ask has to say what closes it, or the questions read as a report
    # that happens to end in a list. The two steps are the same ones the page walks: the
    # answer becomes a revision of the case, then the boundaries are judged again against it.
    if stored.awaiting_answers and not as_json:
        typer.echo(
            f"\nThis review is waiting on answers. Write each into the field its question "
            f"names, apply them with `archcompass case update {case_id} --from answers.yaml`, "
            f"then carry the review on with `archcompass review {case_id} --repo {repo} "
            f"--answers {stored.review_id}`."
        )


@reviews_app.command("show")
def review_show(context: typer.Context, review_id: str) -> None:
    stored = _state(context).runtime.review_repository.get(review_id)
    typer.echo(render_review(stored))


@reviews_app.command("ask")
def review_ask(
    context: typer.Context,
    review_id: str,
    question: str,
) -> None:
    """Ask a question about one review, continuing its conversation."""

    service = _state(context).runtime.review_conversation_service
    existing = service.list(review_id)
    conversation = existing[0] if existing else service.create(review_id)
    message = service.ask(conversation.conversation_id, question)
    if message.answer is None:
        raise RuntimeError(message.failure)
    typer.echo(message.answer.answer)
    grounding = message.answer.supporting_references
    typer.echo("")
    typer.echo(
        f"Grounded on {', '.join(grounding)}"
        if grounding
        else "Not grounded on any reviewed boundary."
    )


@reviews_app.command("history")
def review_history(context: typer.Context, review_id: str) -> None:
    conversations = _state(context).runtime.review_conversation_service.list(review_id)
    typer.echo(
        json.dumps([item.model_dump(mode="json") for item in conversations], indent=2)
    )


@reviews_app.command("list")
def review_list(
    context: typer.Context,
    case: Annotated[str | None, typer.Option("--case", help="Filter by case ID.")] = None,
) -> None:
    summaries = _state(context).runtime.review_repository.list(case_id=case)
    typer.echo(
        json.dumps([item.model_dump(mode="json") for item in summaries], indent=2)
    )


def _state(context: typer.Context) -> CLIState:
    if not isinstance(context.obj, CLIState):
        raise RuntimeError("CLI state was not initialized")
    return context.obj


def _read_yaml(path: Path) -> object:
    try:
        return yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as error:
        raise typer.BadParameter(f"Could not read YAML {path}: {error}") from error


def main() -> None:
    try:
        app()
    except (ValidationError, ArchCompassError) as error:
        typer.echo(f"Error: {error}", err=True)
        raise SystemExit(2) from None
