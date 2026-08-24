"""What opening a workspace creates, and what it deliberately no longer creates."""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from typer.testing import CliRunner

from archcompass.bootstrap import initialize_workspace
from archcompass.presentation.cli.app import app

_DATABASE = Path(".archcompass") / "workspace.sqlite3"


def test_init_creates_the_workspace_and_its_database_and_nothing_else(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """No model configuration is written any more, and that is the point of the change.

    A seeded file named a provider the machine might not have — an Ollama that is not
    running, a key that was never set — and preferred it silently over anything the reader
    later chose. Which providers exist is stated in code now, and which model this workspace
    reasons with is asked for where a model is actually needed.
    """

    runner = CliRunner()
    workspace = tmp_path / "workspace"
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    monkeypatch.chdir(elsewhere)

    result = runner.invoke(app, ["--workspace", str(workspace), "init"])

    assert result.exit_code == 0, result.output
    assert (workspace / _DATABASE).is_file()
    assert not (workspace / "config").exists()
    assert sorted(item.name for item in workspace.iterdir()) == [".archcompass"]


def test_init_is_safe_to_repeat(tmp_path: Path) -> None:
    """It exists to create what is missing, so running it twice creates nothing twice."""

    runner = CliRunner()
    workspace = tmp_path / "workspace"

    assert runner.invoke(app, ["--workspace", str(workspace), "init"]).exit_code == 0
    written = (workspace / _DATABASE).stat().st_mtime_ns

    repeated = runner.invoke(app, ["--workspace", str(workspace), "init"])

    assert repeated.exit_code == 0, repeated.output
    assert (workspace / _DATABASE).stat().st_mtime_ns == written


def test_an_unrelated_database_file_does_not_block_startup(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    state = workspace / ".archcompass"
    state.mkdir(parents=True)
    unrelated = state / "archcompass.db"
    unrelated.write_bytes(b"not opened by the current runtime")

    runtime = initialize_workspace(workspace)

    assert runtime.database.path == (workspace / _DATABASE).resolve()
    assert unrelated.read_bytes() == b"not opened by the current runtime"


def test_opening_a_workspace_reads_its_own_credentials_first(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The `.env` has to be read before anything reaches a provider, not after.

    It was not, once: `initialize_workspace` resolved everything it needed and only loaded
    the environment on the way into `build_runtime`, so the two commands a person actually
    runs never saw what their workspace had said.
    """

    workspace = tmp_path / "workspace"
    workspace.mkdir(parents=True)
    (workspace / ".env").write_text("OPENROUTER_API_KEY=from-the-workspace\n", encoding="utf-8")
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)

    runtime = initialize_workspace(workspace)

    assert runtime.workspace == workspace.resolve()
    assert os.environ["OPENROUTER_API_KEY"] == "from-the-workspace"
