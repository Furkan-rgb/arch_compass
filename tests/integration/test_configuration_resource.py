from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner

from archcompass.bootstrap import initialize_workspace
from archcompass.configuration import default_config_text
from archcompass.domain.errors import PathValidationError
from archcompass.presentation.cli.app import app

FAKE_CONFIG = """models:
  reasoning:
    provider: fake
    model: chosen-by-dot-env
    base_url: http://127.0.0.1:11434
    timeout_seconds: 5
    context_window_tokens: 32768
    max_output_tokens: 8192
  embedding:
    provider: fake
    model: deterministic-token-hash-v1
    base_url: http://127.0.0.1:11434
    dimensions: 64
    timeout_seconds: 5
"""


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


def test_a_workspace_env_file_chooses_the_configuration_for_init_and_web(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`.env` has to be read before the configuration is resolved, not after.

    It was not: `initialize_workspace` resolved first and only loaded the environment on the
    way into `build_runtime`, so a workspace that had said exactly which configuration it
    wanted was ignored by the two commands a person actually runs. Nothing failed loudly —
    it fell through to discovery and complained that the choice had not been made.
    """

    workspace = tmp_path / "workspace"
    (workspace / "config").mkdir(parents=True)
    for name in ("models.ollama.yaml", "models.google.yaml"):
        (workspace / "config" / name).write_text(FAKE_CONFIG, encoding="utf-8")
    (workspace / ".env").write_text(
        "ARCHCOMPASS_MODELS_CONFIG=config/models.google.yaml\n", encoding="utf-8"
    )
    monkeypatch.delenv("ARCHCOMPASS_MODELS_CONFIG", raising=False)

    result = initialize_workspace(workspace)

    # The named file, and no third one invented beside the two already there.
    assert result.created_paths == ()
    assert not (workspace / "config" / "models.yaml").exists()
    assert result.runtime.config.models.reasoning.model == "chosen-by-dot-env"


def test_a_configuration_does_not_have_to_be_called_models_anything(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Being pointed at a file settles it, whatever the file is called."""

    workspace = tmp_path / "workspace"
    workspace.mkdir(parents=True)
    (workspace / "whatever.yaml").write_text(FAKE_CONFIG, encoding="utf-8")
    (workspace / ".env").write_text(
        "ARCHCOMPASS_MODELS_CONFIG=whatever.yaml\n", encoding="utf-8"
    )
    monkeypatch.delenv("ARCHCOMPASS_MODELS_CONFIG", raising=False)

    result = initialize_workspace(workspace)

    assert result.runtime.config.models.reasoning.model == "chosen-by-dot-env"
    assert not (workspace / "config").exists()
