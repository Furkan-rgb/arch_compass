from __future__ import annotations

from pathlib import Path

import pytest

from archcompass.adapters.persistence.database import SQLiteDatabase
from archcompass.adapters.reporting import SafeWorkspaceReportWriter
from archcompass.bootstrap import build_runtime
from archcompass.domain.errors import PathValidationError, PersistenceError


def test_report_writer_rejects_symlink_and_traversal_escapes(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    outside = tmp_path / "outside"
    workspace.mkdir()
    outside.mkdir()
    (workspace / "reports").symlink_to(outside, target_is_directory=True)
    writer = SafeWorkspaceReportWriter(workspace)

    with pytest.raises(PathValidationError, match="symlink"):
        writer.write(
            report_id="run_safe",
            structured_json="{}",
            markdown="# report\n",
        )
    with pytest.raises(PathValidationError, match="safe file name"):
        writer.write(
            report_id="../escape",
            structured_json="{}",
            markdown="# report\n",
        )


def test_state_database_rejects_workspace_symlink_escape(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    outside = tmp_path / "outside"
    workspace.mkdir()
    outside.mkdir()
    (workspace / ".archcompass").symlink_to(outside, target_is_directory=True)

    with pytest.raises(PersistenceError, match=r"escapes workspace|uses symlink"):
        SQLiteDatabase(
            workspace / ".archcompass" / "archcompass.db",
            workspace=workspace,
        )


def test_repository_overlap_is_rejected_before_sqlite_is_opened(
    tmp_path: Path,
    fake_config_text: str,
) -> None:
    repository = tmp_path / "repository"
    workspace = repository / "workspace"
    config = workspace / "config" / "models.yaml"
    config.parent.mkdir(parents=True)
    config.write_text(fake_config_text, encoding="utf-8")

    with pytest.raises(PathValidationError, match="must not equal or be contained"):
        build_runtime(workspace, repository=repository)

    assert not (workspace / ".archcompass" / "archcompass.db").exists()
