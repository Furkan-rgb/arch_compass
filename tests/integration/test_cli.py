from __future__ import annotations

import json
import re
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml
from typer.testing import CliRunner

from archcompass.bootstrap import BUNDLED_POLICY_SOURCE
from archcompass.domain.errors import StaleAtlasError
from archcompass.presentation.cli import app as cli_module
from archcompass.presentation.cli.app import app
from archcompass.reasoning.adapters.providers import DETERMINISTIC_MODEL

runner = CliRunner()

_STYLE_CODES = re.compile(r"\x1b\[[0-9;]*m")

#: What a CLI run reasons with here. Global options, so they precede the subcommand: after
#: it, Typer rejects the whole invocation with "No such option".
_SUBSTITUTE = ["--provider", "fake", "--model", DETERMINISTIC_MODEL]


def unstyled(output: str) -> str:
    """Typer styles help output whenever it detects a terminal, and CI counts as
    one. The styling splits option names across escape sequences, so assertions
    about the rendered text have to read it without them."""
    return _STYLE_CODES.sub("", output)


def test_web_accepts_workspace_after_command(tmp_path: Path) -> None:
    result = runner.invoke(
        app,
        ["web", "--workspace", str(tmp_path), "--help"],
    )

    assert result.exit_code == 0, result.output
    help_text = unstyled(result.output)
    assert "--workspace" in help_text
    # Read in pieces: Typer wraps the column to the terminal width, so the sentence this is
    # about is never contiguous in the rendered output.
    assert "Defaults to" in help_text
    assert "current" in help_text and "directory (.)" in help_text
    assert "--no-open" in help_text


def test_web_defaults_workspace_to_current_directory(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    selected_workspaces: list[Path] = []

    def initialize_workspace(workspace: Path, **_: object) -> SimpleNamespace:
        selected_workspaces.append(workspace)
        return SimpleNamespace(workspace=workspace)

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


def test_naming_a_provider_without_a_model_is_refused(tmp_path: Path) -> None:
    """Either alone would have to be completed by a guess, and which model a review runs
    against decides what it costs and how long it takes."""

    result = runner.invoke(
        app, ["--workspace", str(tmp_path), "--provider", "fake", "init"]
    )

    assert result.exit_code != 0
    assert "--provider and --model" in unstyled(result.output)


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


def test_cli_commands_cover_local_workflow(tmp_path: Path) -> None:
    """Init, policies, case, index, review, ask — the whole local loop through the CLI."""

    workspace = tmp_path.resolve()
    initialized = runner.invoke(app, ["--workspace", str(workspace), "init"])
    assert initialized.exit_code == 0, initialized.output

    # The model is named on the command line rather than chosen: a CLI run has no chip to
    # click, and every command here means to reason with the substitute.
    common = ["--workspace", str(workspace), *_SUBSTITUTE]

    # No rebuild step before listing. Policies are read from their sources when asked for,
    # so the bundled corpus is there from the first command.
    listed = runner.invoke(app, [*common, "policies", "list"])
    assert listed.exit_code == 0
    assert "hide-implementation-details" in listed.output
    assert (
        runner.invoke(
            app, [*common, "policies", "show", "hide-implementation-details"]
        ).exit_code
        == 0
    )

    repository = Path("eval/cases/boundary-review/repository").resolve()
    # Written here rather than taken from the example, which ships a repository and no case:
    # `case create --from` is for someone who has already authored one, and the file it
    # reads has to come from somewhere that is not the product's own flow.
    case_path = tmp_path / "case.yaml"
    case_path.write_text(
        yaml.safe_dump(
            {
                "goal": (
                    "A small task scheduler declares six boundaries and has exactly one "
                    "implementation behind each. Decide which are earning their place and "
                    "produce a verdict for every boundary."
                ),
                "constraints": [
                    {
                        "text": "Python with SQLite for storage and SMTP for delivery.",
                        "facet": "constraint",
                    },
                    {
                        "text": "SMS reminders are scheduled for the next release.",
                        "facet": "expected_change",
                    },
                    {
                        "text": "Alternative label formats are not in scope.",
                        "facet": "non_goal",
                    },
                ],
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    created = runner.invoke(app, [*common, "case", "create", "--from", str(case_path)])
    assert created.exit_code == 0, created.output
    case_id = json.loads(created.output)["case_id"]
    assert runner.invoke(app, [*common, "case", "show", case_id]).exit_code == 0
    assert runner.invoke(app, [*common, "case", "history", case_id]).exit_code == 0

    indexed = runner.invoke(app, [*common, "repo", "index", str(repository)])
    assert indexed.exit_code == 0, indexed.output
    assert runner.invoke(app, [*common, "atlas", "summary", str(repository)]).exit_code == 0

    reviewed = runner.invoke(
        app, [*common, "review", case_id, "--repo", str(repository)]
    )
    assert reviewed.exit_code == 0, reviewed.output
    assert "# Architecture review" in reviewed.output
    # Cleared boundaries appear too. A report of only problems reads the same whether the
    # advisor examined everything and cleared it or never ran.
    assert "**cleared**" in reviewed.output

    reviews = runner.invoke(app, [*common, "reviews", "list"])
    assert reviews.exit_code == 0, reviews.output
    review_id = json.loads(reviews.output)[0]["id"]
    assert runner.invoke(app, [*common, "reviews", "show", review_id]).exit_code == 0

    asked = runner.invoke(
        app, [*common, "reviews", "ask", review_id, "What did you make of the formatter?"]
    )
    assert asked.exit_code == 0, asked.output
    assert "Grounded on candidate_" in asked.output or "Not grounded" in asked.output
    history = runner.invoke(app, [*common, "reviews", "history", review_id])
    assert history.exit_code == 0
    assert json.loads(history.output)[0]["messages"]


def test_cli_policy_source_registry_is_persistent(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    initialized = runner.invoke(app, ["--workspace", str(workspace), "init"])
    assert initialized.exit_code == 0, initialized.output
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

    registered = runner.invoke(
        app,
        [*common, "policies", "sources", "add", str(source)],
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

    assert registered.exit_code == 0, registered.output
    assert listed_sources.exit_code == 0, listed_sources.output
    assert str(source.resolve()) in listed_sources.output
    assert shown.exit_code == 0, shown.output
    assert '"scope": "organisation"' in shown.output
    assert removed.exit_code == 0, removed.output
    assert str(source.resolve()) not in listed_after_remove.output
