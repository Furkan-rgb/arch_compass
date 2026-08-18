from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
from typer.testing import CliRunner

from archcompass.adapters.persistence.schema_epoch import WorkspaceSchemaEpoch
from archcompass.domain.errors import LegacySchemaError
from archcompass.presentation.cli.app import app


def test_legacy_workspace_is_refused_until_explicitly_exported_and_reset(
    tmp_path: Path,
) -> None:
    state = tmp_path / ".archcompass"
    state.mkdir()
    epoch = WorkspaceSchemaEpoch(state)
    with sqlite3.connect(epoch.legacy_database) as connection:
        connection.execute("CREATE TABLE cases(case_id TEXT PRIMARY KEY)")
        connection.execute("INSERT INTO cases VALUES ('case-1')")

    with pytest.raises(LegacySchemaError):
        epoch.require_current_or_empty()

    exported = epoch.export_legacy(tmp_path / "legacy-export.sqlite3")
    archive = epoch.reset()

    assert exported.is_file()
    assert archive is not None
    assert (archive / "archcompass.db").is_file()
    assert epoch.database.is_file()


def test_cli_can_export_a_legacy_workspace_without_opening_the_new_runtime(
    tmp_path: Path,
) -> None:
    state = tmp_path / ".archcompass"
    state.mkdir()
    legacy = state / "archcompass.db"
    with sqlite3.connect(legacy) as connection:
        connection.execute("CREATE TABLE marker(value TEXT)")
    destination = tmp_path / "export.sqlite3"

    result = CliRunner().invoke(
        app,
        [
            "--workspace",
            str(tmp_path),
            "workspace",
            "export-legacy",
            str(destination),
        ],
    )

    assert result.exit_code == 0, result.output
    assert destination.is_file()
    assert not (state / "archcompass-v2.db").exists()
