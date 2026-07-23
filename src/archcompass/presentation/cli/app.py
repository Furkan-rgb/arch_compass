"""ArchCompass command-line presentation adapter."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated

import typer
import yaml
from pydantic import ValidationError

from archcompass.bootstrap import Runtime, build_runtime
from archcompass.configuration import DEFAULT_CONFIG_TEXT
from archcompass.domain.atlas import HotspotsQuery, NodeDetailsQuery, RepositorySummaryQuery
from archcompass.domain.case import ArchitectureCase, CaseUpdate
from archcompass.domain.errors import (
    ArchCompassError,
    CaseNotFoundError,
    ConfigurationError,
)

app = typer.Typer(
    name="archcompass",
    help="Evidence-grounded, local-first software architecture advice.",
    no_args_is_help=True,
)
policies_app = typer.Typer(help="Build and inspect architectural policies.")
repo_app = typer.Typer(help="Index a Python repository.")
atlas_app = typer.Typer(help="Query repository atlases.")
case_app = typer.Typer(help="Create and revise architecture cases.")
run_app = typer.Typer(help="Inspect immutable consultation runs.")
app.add_typer(policies_app, name="policies")
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
    config_path = state.models_config or state.workspace / "config" / "models.yaml"
    created: list[Path] = []
    if not config_path.exists():
        config_path.parent.mkdir(parents=True, exist_ok=True)
        config_path.write_text(DEFAULT_CONFIG_TEXT, encoding="utf-8")
        created.append(config_path)
    runtime = build_runtime(state.workspace, models_config=config_path)
    typer.echo(f"Workspace ready: {runtime.workspace}")
    for path in created:
        typer.echo(f"Created {path}")


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
    sources = [*runtime.policy_sources, *(source or [])]
    if repo is not None:
        sources.append(repo.expanduser().resolve() / ".archcompass" / "policies")
    version = runtime.policy_store.rebuild(sources)
    typer.echo(version.model_dump_json(indent=2))


@policies_app.command("list")
def policies_list(context: typer.Context) -> None:
    for policy in _state(context).runtime.policy_store.list_policies():
        typer.echo(f"{policy.id}\t{policy.scope}\t{policy.strength}\t{policy.title}")


@policies_app.command("show")
def policies_show(context: typer.Context, policy_id: str) -> None:
    policy = _state(context).runtime.policy_store.get_policy(policy_id)
    typer.echo(policy.model_dump_json(indent=2))


@repo_app.command("index")
def repo_index(context: typer.Context, path: Path) -> None:
    runtime = _state(context).runtime
    atlas = runtime.analyzer.analyze(path)
    runtime.atlas_repository.save(atlas)
    typer.echo(atlas.version.model_dump_json(indent=2))


@atlas_app.command("summary")
def atlas_summary(context: typer.Context, path: Path) -> None:
    runtime = _state(context).runtime
    atlas = runtime.atlas_repository.latest_for_path(path)
    if atlas is None:
        raise typer.BadParameter(f"No indexed atlas exists for {path}")
    result = runtime.query_service.execute(
        atlas, RepositorySummaryQuery(kind="repository_summary", limit=30)
    )
    typer.echo(result.model_dump_json(indent=2))


@atlas_app.command("inspect")
def atlas_inspect(
    context: typer.Context,
    path: Path,
    node: Annotated[str, typer.Option("--node", help="Stable atlas node ID.")],
) -> None:
    runtime = _state(context).runtime
    atlas = runtime.atlas_repository.latest_for_path(path)
    if atlas is None:
        raise typer.BadParameter(f"No indexed atlas exists for {path}")
    result = runtime.query_service.execute(
        atlas, NodeDetailsQuery(kind="node_details", node_id=node)
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
    runtime = _state(context).runtime
    atlas = runtime.atlas_repository.latest_for_path(path)
    if atlas is None:
        raise typer.BadParameter(f"No indexed atlas exists for {path}")
    result = runtime.query_service.execute(
        atlas, HotspotsQuery(kind="hotspots", metric=metric, limit=20)
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
    runtime = _state(context).runtime
    atlas = None
    if repo is not None:
        atlas = runtime.atlas_repository.latest_for_path(repo)
        if atlas is None:
            raise typer.BadParameter(f"No indexed atlas exists for {repo}")
    run = runtime.workflow.advise(case_id, atlas=atlas)
    reports = runtime.workspace / "reports"
    reports.mkdir(parents=True, exist_ok=True)
    if run.report is None or run.markdown_report is None:
        raise RuntimeError("Successful consultation did not produce a report")
    (reports / f"{run.run_id}.json").write_text(
        run.report.model_dump_json(indent=2) + "\n", encoding="utf-8"
    )
    (reports / f"{run.run_id}.md").write_text(run.markdown_report, encoding="utf-8")
    typer.echo(run.report.model_dump_json(indent=2) if as_json else run.markdown_report)


@run_app.command("show")
def run_show(context: typer.Context, run_id: str) -> None:
    run = _state(context).runtime.run_repository.get(run_id)
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
    except (ValidationError, ArchCompassError, ConfigurationError, CaseNotFoundError) as error:
        typer.echo(f"Error: {error}", err=True)
        raise typer.Exit(code=2) from error
