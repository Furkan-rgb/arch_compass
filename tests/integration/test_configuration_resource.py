from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner

from archcompass.configuration import default_config_text
from archcompass.domain.errors import PathValidationError
from archcompass.presentation.cli.app import app


def test_init_copies_packaged_configuration_outside_checkout(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runner = CliRunner()
    workspace = tmp_path / "workspace"
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()

    monkeypatch.chdir(elsewhere)
    result = runner.invoke(app, ["--workspace", str(workspace), "init"])

    assert result.exit_code == 0, result.output
    config = workspace / "config" / "models.yaml"
    assert config.read_text(encoding="utf-8") == default_config_text()

    preserved = f"{default_config_text()}\n# local workspace customization\n"
    config.write_text(preserved, encoding="utf-8")

    repeated = runner.invoke(app, ["--workspace", str(workspace), "init"])

    assert repeated.exit_code == 0, repeated.output
    assert config.read_text(encoding="utf-8") == preserved


def test_init_preserves_existing_explicit_configuration(tmp_path: Path) -> None:
    runner = CliRunner()
    workspace = tmp_path / "workspace"
    config = workspace / "custom-models.yaml"
    config.parent.mkdir(parents=True)
    existing = default_config_text().replace("provider: ollama", "provider: fake")
    config.write_text(existing, encoding="utf-8")

    result = runner.invoke(
        app,
        [
            "--workspace",
            str(workspace),
            "--models-config",
            str(config),
            "init",
        ],
    )

    assert result.exit_code == 0, result.output
    assert config.read_text(encoding="utf-8") == existing


def test_init_rejects_a_default_configuration_symlink_escape(
    tmp_path: Path,
) -> None:
    runner = CliRunner()
    workspace = tmp_path / "workspace"
    outside = tmp_path / "outside"
    workspace.mkdir()
    outside.mkdir()
    (workspace / "config").symlink_to(outside, target_is_directory=True)

    result = runner.invoke(app, ["--workspace", str(workspace), "init"])

    assert result.exit_code != 0
    assert isinstance(result.exception, PathValidationError)
    assert not (outside / "models.yaml").exists()
