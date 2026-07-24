"""ArchCompass command-line presentation adapter."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated

import typer
import yaml
from pydantic import ValidationError

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
    help="Evidence-grounded, local-first software architecture advice.",
    no_args_is_help=True,
)
policies_app = typer.Typer(help="Build and inspect architectural policies.")
policy_sources_app = typer.Typer(help="Register persistent workspace policy sources.")
repo_app = typer.Typer(help="Index a Python repository.")
atlas_app = typer.Typer(help="Query repository atlases.")
case_app = typer.Typer(help="Create and revise architecture cases.")
run_app = typer.Typer(help="Inspect immutable consultation runs.")
app.add_typer(policies_app, name="policies")
policies_app.add_typer(policy_sources_app, name="sources")
app.add_typer(repo_app, name="repo")
app.add_typer(atlas_app, name="atlas")
app.add_typer(case_app, name="case")
app.add_typer(run_app, name="run")


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
            help="Workspace containing config, state, and reports.",
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


@policies_app.command("rebuild")
def policies_rebuild(
    context: typer.Context,
    source: Annotated[
        list[Path] | None,
        typer.Option("--source", help="Additional policy file or directory."),
    ] = None,
    repo: Annotated[
        Path | None,
        typer.Option("--repo", help="Load <repo>/.archcompass/policies."),
    ] = None,
) -> None:
    runtime = _state(context).runtime
    version = runtime.policy_service.rebuild(
        sources=source,
        repository_root=repo,
    )
    typer.echo(version.model_dump_json(indent=2))


@policies_app.command("list")
def policies_list(context: typer.Context) -> None:
    for policy in _state(context).runtime.policy_service.list_policies():
        typer.echo(f"{policy.id}\t{policy.scope}\t{policy.strength}\t{policy.title}")


@policies_app.command("show")
def policies_show(context: typer.Context, policy_id: str) -> None:
    policy = _state(context).runtime.policy_service.get_policy(policy_id)
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


@app.command("advise")
def advise(
    context: typer.Context,
    case_id: str,
    repo: Annotated[
        Path | None,
        typer.Option("--repo", help="Use the latest indexed atlas for this repository."),
    ] = None,
    as_json: Annotated[
        bool, typer.Option("--json", help="Print the structured report.")
    ] = False,
) -> None:
    state = _state(context)
    runtime = (
        state.runtime_for_repository(repo)
        if repo is not None
        else state.runtime
    )
    run = runtime.advice_service.advise(
        case_id,
        repository_root=repo,
    )
    if run.report is None or run.markdown_report is None:
        raise RuntimeError("Successful consultation did not produce a report")
    typer.echo(run.report.model_dump_json(indent=2) if as_json else run.markdown_report)


@run_app.command("show")
def run_show(context: typer.Context, run_id: str) -> None:
    run = _state(context).runtime.run_service.show(run_id)
    typer.echo(run.model_dump_json(indent=2))


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
