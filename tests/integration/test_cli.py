from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from typer.testing import CliRunner

from archcompass.bootstrap import BUNDLED_POLICY_SOURCE
from archcompass.domain.errors import StaleAtlasError
from archcompass.presentation.cli import app as cli_module
from archcompass.presentation.cli.app import app

runner = CliRunner()


def test_web_accepts_workspace_after_command(tmp_path: Path) -> None:
    result = runner.invoke(
        app,
        ["web", "--workspace", str(tmp_path), "--help"],
    )

    assert result.exit_code == 0, result.output
    assert "--workspace" in result.output
    assert "Defaults to" in result.output
    assert "the current directory" in result.output
    assert "--no-open" in result.output


def test_web_defaults_workspace_to_current_directory(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    selected_workspaces: list[Path] = []

    def initialize_workspace(workspace: Path, **_: object) -> SimpleNamespace:
        selected_workspaces.append(workspace)
        return SimpleNamespace(
            runtime=SimpleNamespace(workspace=workspace),
            created_paths=(),
        )

    monkeypatch.setattr(
        cli_module,
        "initialize_workspace_runtime",
        initialize_workspace,
    )
    monkeypatch.setattr("archcompass.presentation.web.create_app", lambda runtime: runtime)
    monkeypatch.setattr("uvicorn.run", lambda *args, **kwargs: None)

    result = runner.invoke(app, ["web", "--no-open"])
    override = runner.invoke(
        app,
        ["web", "--workspace", str(tmp_path), "--no-open"],
    )

    assert result.exit_code == 0, result.output
    assert override.exit_code == 0, override.output
    assert selected_workspaces == [Path.cwd().resolve(), tmp_path.resolve()]


def test_console_entrypoint_reports_domain_errors_without_a_traceback(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    def fail() -> None:
        raise StaleAtlasError("atlas is stale")

    monkeypatch.setattr(cli_module, "app", fail)

    with pytest.raises(SystemExit) as raised:
        cli_module.main()

    assert raised.value.code == 2
    captured = capsys.readouterr()
    assert captured.err == "Error: atlas is stale\n"


def test_cli_commands_cover_local_workflow(tmp_path: Path, fake_config_text: str) -> None:
    workspace = tmp_path.resolve()
    initialized = runner.invoke(app, ["--workspace", str(workspace), "init"])
    assert initialized.exit_code == 0, initialized.output

    config_path = workspace / "config" / "models.yaml"
    config_path.write_text(fake_config_text, encoding="utf-8")
    common = ["--workspace", str(workspace)]

    rebuilt = runner.invoke(
        app,
        [
            *common,
            "policies",
            "rebuild",
        ],
    )
    assert rebuilt.exit_code == 0, rebuilt.output
    listed = runner.invoke(app, [*common, "policies", "list"])
    assert listed.exit_code == 0
    assert "hide-implementation-details" in listed.output
    shown = runner.invoke(
        app, [*common, "policies", "show", "hide-implementation-details"]
    )
    assert shown.exit_code == 0

    case_path = Path("eval/cases/audiobook-greenfield/case.yaml").resolve()
    created = runner.invoke(
        app, [*common, "case", "create", "--from", str(case_path)]
    )
    assert created.exit_code == 0, created.output
    case_id = json.loads(created.output)["case_id"]
    assert runner.invoke(app, [*common, "case", "show", case_id]).exit_code == 0
    assert runner.invoke(app, [*common, "case", "history", case_id]).exit_code == 0
    update_path = workspace / "case-update.yaml"
    update_path.write_text("title: Updated audiobook case\n", encoding="utf-8")
    updated = runner.invoke(
        app,
        [*common, "case", "update", case_id, "--from", str(update_path)],
    )
    assert updated.exit_code == 0

    fixture = Path("eval/cases/provider-leakage/repository").resolve()
    indexed = runner.invoke(app, [*common, "repo", "index", str(fixture)])
    assert indexed.exit_code == 0, indexed.output
    assert runner.invoke(
        app, [*common, "atlas", "summary", str(fixture)]
    ).exit_code == 0
    hotspots = runner.invoke(
        app,
        [
            *common,
            "atlas",
            "hotspots",
            str(fixture),
            "--metric",
            "reverse_dependency_reach",
        ],
    )
    assert hotspots.exit_code == 0
    node_id = json.loads(hotspots.output)["node_ids"][0]
    inspected = runner.invoke(
        app,
        [*common, "atlas", "inspect", str(fixture), "--node", node_id],
    )
    assert inspected.exit_code == 0

    advised = runner.invoke(app, [*common, "advise", case_id, "--json"])
    assert advised.exit_code == 0, advised.output
    assert "recommended_architecture" in advised.output
    reports = list((workspace / "reports").glob("*.json"))
    assert len(reports) == 1
    run_id = reports[0].stem
    shown_run = runner.invoke(app, [*common, "run", "show", run_id])
    assert shown_run.exit_code == 0
    created_conversation = runner.invoke(
        app,
        [*common, "conversation", "create", "--run", run_id],
    )
    assert created_conversation.exit_code == 0, created_conversation.output
    conversation_id = json.loads(created_conversation.output)["conversation_id"]
    assert runner.invoke(
        app,
        [*common, "conversation", "list", "--run", run_id],
    ).exit_code == 0
    assert runner.invoke(
        app,
        [*common, "conversation", "show", conversation_id],
    ).exit_code == 0
    asked = runner.invoke(
        app,
        [
            *common,
            "conversation",
            "ask",
            conversation_id,
            "What are the main findings?",
            "--json",
        ],
    )
    assert asked.exit_code == 0, asked.output
    assert json.loads(asked.output)["relevant_finding_ids"]
    assert runner.invoke(
        app,
        [*common, "conversation", "history", conversation_id],
    ).exit_code == 0
    markdown_export = runner.invoke(
        app,
        [
            *common,
            "conversation",
            "export",
            conversation_id,
            "--format",
            "markdown",
        ],
    )
    assert markdown_export.exit_code == 0
    assert f"Consultation run: `{run_id}`" in markdown_export.output
    json_export = runner.invoke(
        app,
        [
            *common,
            "conversation",
            "export",
            conversation_id,
            "--format",
            "json",
        ],
    )
    assert json_export.exit_code == 0
    assert json.loads(json_export.output)["conversation"]["conversation_id"] == conversation_id
    brownfield = runner.invoke(
        app,
        [*common, "advise", case_id, "--repo", str(fixture), "--json"],
    )
    assert brownfield.exit_code == 0, brownfield.output


def test_advise_prepares_missing_policy_index(
    tmp_path: Path,
    fake_config_text: str,
) -> None:
    workspace = tmp_path.resolve()
    config_path = workspace / "config" / "models.yaml"
    config_path.parent.mkdir(parents=True)
    config_path.write_text(fake_config_text, encoding="utf-8")
    common = ["--workspace", str(workspace)]
    case_path = Path("eval/cases/premature-abstraction/case.yaml").resolve()
    created = runner.invoke(app, [*common, "case", "create", "--from", str(case_path)])
    assert created.exit_code == 0, created.output
    case_id = json.loads(created.output)["case_id"]

    advised = runner.invoke(app, [*common, "advise", case_id, "--json"])

    assert advised.exit_code == 0, advised.output
    assert "recommended_architecture" in advised.output
    listed = runner.invoke(app, [*common, "policies", "list"])
    assert listed.exit_code == 0, listed.output
    assert "delay-premature-abstraction" in listed.output


def test_cli_policy_source_registry_is_persistent(
    tmp_path: Path,
    fake_config_text: str,
) -> None:
    workspace = tmp_path / "workspace"
    initialized = runner.invoke(app, ["--workspace", str(workspace), "init"])
    assert initialized.exit_code == 0, initialized.output
    (workspace / "config" / "models.yaml").write_text(
        fake_config_text,
        encoding="utf-8",
    )
    source = tmp_path / "team-policies"
    source.mkdir()
    template = (BUNDLED_POLICY_SOURCE / "contain-dependencies.md").read_text(
        encoding="utf-8"
    )
    (source / "team-containment.md").write_text(
        template.replace(
            "id: contain-dependencies",
            "id: team-containment",
            1,
        ).replace(
            "scope: general",
            "scope: organisation\napplies_to: example-organisation",
            1,
        ),
        encoding="utf-8",
    )
    common = ["--workspace", str(workspace)]

    rebuilt = runner.invoke(
        app,
        [*common, "policies", "rebuild", "--source", str(source)],
    )
    listed_sources = runner.invoke(
        app,
        [*common, "policies", "sources", "list"],
    )
    shown = runner.invoke(
        app,
        [*common, "policies", "show", "team-containment"],
    )
    removed = runner.invoke(
        app,
        [*common, "policies", "sources", "remove", str(source)],
    )
    listed_after_remove = runner.invoke(
        app,
        [*common, "policies", "sources", "list"],
    )

    assert rebuilt.exit_code == 0, rebuilt.output
    assert listed_sources.exit_code == 0, listed_sources.output
    assert str(source.resolve()) in listed_sources.output
    assert shown.exit_code == 0, shown.output
    assert '"scope": "organisation"' in shown.output
    assert removed.exit_code == 0, removed.output
    assert str(source.resolve()) not in listed_after_remove.output
