from __future__ import annotations

import os
from pathlib import Path

import pytest
from pydantic import ValidationError

from archcompass.configuration import (
    ReasoningModelConfig,
    load_environment_file,
    load_provider_environment,
    resolve_api_key,
    resolve_config_path,
)
from archcompass.domain.errors import ConfigurationError


def test_reasoning_model_config_accepts_explicit_context_window() -> None:
    config = ReasoningModelConfig(
        provider="ollama",
        model="reasoning-test",
        base_url="http://ollama.test/",
        timeout_seconds=10,
        context_window_tokens=65536,
        max_output_tokens=8192,
    )

    assert config.context_window_tokens == 65536


def test_thinking_has_three_states_and_defaults_to_the_models_own() -> None:
    """Required, forbidden, and left to the model are three different behaviours.

    Measured on gemma4:26b: requiring it cost twice the time and a point of score, and
    forbidding it cost three, while leaving it alone was best. A configuration written
    before the switch existed keeps that third behaviour, which is why absent is None
    rather than False.
    """

    absent = ReasoningModelConfig(provider="ollama", model="m", timeout_seconds=30)
    required = ReasoningModelConfig(
        provider="ollama", model="m", timeout_seconds=30, thinking=True
    )
    forbidden = ReasoningModelConfig(
        provider="ollama", model="m", timeout_seconds=30, thinking=False
    )

    assert absent.thinking is None
    assert required.thinking is True
    assert forbidden.thinking is False


def test_reasoning_model_config_rejects_output_larger_than_context_window() -> None:
    with pytest.raises(
        ValidationError,
        match="max_output_tokens must not exceed context_window_tokens",
    ):
        ReasoningModelConfig(
            provider="ollama",
            model="reasoning-test",
            base_url="http://ollama.test/",
            timeout_seconds=10,
            context_window_tokens=4096,
            max_output_tokens=8192,
        )


def test_environment_file_fills_only_unset_variables(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A real environment variable wins, so CI and a shell export override the file."""

    monkeypatch.setenv("ARCHCOMPASS_TEST_PRESET", "from-shell")
    monkeypatch.delenv("ARCHCOMPASS_TEST_PLAIN", raising=False)
    monkeypatch.delenv("ARCHCOMPASS_TEST_QUOTED", raising=False)
    monkeypatch.delenv("ARCHCOMPASS_TEST_EXPORTED", raising=False)
    env_file = tmp_path / ".env"
    env_file.write_text(
        "\n".join(
            [
                "# a comment",
                "",
                "ARCHCOMPASS_TEST_PLAIN=plain-value",
                'ARCHCOMPASS_TEST_QUOTED="quoted value"',
                "export ARCHCOMPASS_TEST_EXPORTED=exported-value",
                "ARCHCOMPASS_TEST_PRESET=from-file",
                "not-an-assignment",
            ]
        ),
        encoding="utf-8",
    )

    load_environment_file(env_file)

    assert os.environ["ARCHCOMPASS_TEST_PLAIN"] == "plain-value"
    assert os.environ["ARCHCOMPASS_TEST_QUOTED"] == "quoted value"
    assert os.environ["ARCHCOMPASS_TEST_EXPORTED"] == "exported-value"
    assert os.environ["ARCHCOMPASS_TEST_PRESET"] == "from-shell"


def test_a_missing_environment_file_is_not_an_error(tmp_path: Path) -> None:
    """Not every workspace uses a hosted provider."""

    load_environment_file(tmp_path / ".env")


def test_api_key_resolution_names_the_variable_and_the_file(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ARCHCOMPASS_TEST_KEY", "  secret  ")
    assert resolve_api_key("ARCHCOMPASS_TEST_KEY", provider="google") == "secret"

    monkeypatch.setenv("ARCHCOMPASS_TEST_KEY", "   ")
    with pytest.raises(ConfigurationError, match=r"ARCHCOMPASS_TEST_KEY.*\.env"):
        resolve_api_key("ARCHCOMPASS_TEST_KEY", provider="google")

    with pytest.raises(ConfigurationError, match="api_key_env"):
        resolve_api_key(None, provider="google")


def test_provider_environment_is_found_from_the_working_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A workspace is often not the directory the command was run from.

    `--workspace` points elsewhere, and under test it is a temporary directory, so
    reading only the workspace left a correctly configured project unable to find its
    own key.
    """

    monkeypatch.delenv("ARCHCOMPASS_TEST_CWD_KEY", raising=False)
    project = tmp_path / "project"
    project.mkdir()
    (project / ".env").write_text("ARCHCOMPASS_TEST_CWD_KEY=from-cwd\n", encoding="utf-8")
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    monkeypatch.chdir(project)

    load_provider_environment(workspace)

    assert os.environ["ARCHCOMPASS_TEST_CWD_KEY"] == "from-cwd"


def test_the_workspace_environment_file_wins_over_the_working_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("ARCHCOMPASS_TEST_SCOPED_KEY", raising=False)
    project = tmp_path / "project"
    project.mkdir()
    (project / ".env").write_text("ARCHCOMPASS_TEST_SCOPED_KEY=from-cwd\n", encoding="utf-8")
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / ".env").write_text(
        "ARCHCOMPASS_TEST_SCOPED_KEY=from-workspace\n", encoding="utf-8"
    )
    monkeypatch.chdir(project)

    load_provider_environment(workspace)

    assert os.environ["ARCHCOMPASS_TEST_SCOPED_KEY"] == "from-workspace"


def _workspace_with(tmp_path: Path, *names: str) -> Path:
    (tmp_path / "config").mkdir()
    for name in names:
        (tmp_path / "config" / name).write_text("models: {}\n", encoding="utf-8")
    return tmp_path


def test_a_workspace_with_one_named_configuration_uses_it(tmp_path: Path) -> None:
    """No second, unnamed configuration is invented beside the one that is already there.

    A workspace naming its configuration for the provider it points at used to get
    `models.yaml` written from the packaged template — pointing at a model that may not be
    installed, and silently preferred over the one the user wrote.
    """

    workspace = _workspace_with(tmp_path, "models.ollama.yaml")

    assert resolve_config_path(workspace).name == "models.ollama.yaml"


def test_an_unnamed_configuration_still_wins_when_a_workspace_has_one(
    tmp_path: Path,
) -> None:
    workspace = _workspace_with(tmp_path, "models.ollama.yaml", "models.yaml")

    assert resolve_config_path(workspace).name == "models.yaml"


def test_several_named_configurations_are_a_choice_rather_than_a_guess(
    tmp_path: Path,
) -> None:
    """Which provider a review runs against decides its cost and its duration."""

    workspace = _workspace_with(tmp_path, "models.google.yaml", "models.ollama.yaml")

    with pytest.raises(ConfigurationError) as failure:
        resolve_config_path(workspace)

    message = str(failure.value)
    assert "models.google.yaml" in message and "models.ollama.yaml" in message
    assert "--models-config" in message


def test_an_empty_workspace_is_pointed_at_the_default_name(tmp_path: Path) -> None:
    """Which is what initialization then creates, so a new workspace still just works."""

    assert resolve_config_path(tmp_path).name == "models.yaml"


def test_an_explicit_path_beats_everything_a_workspace_holds(tmp_path: Path) -> None:
    workspace = _workspace_with(tmp_path, "models.google.yaml", "models.ollama.yaml")
    chosen = workspace / "config" / "models.google.yaml"

    assert resolve_config_path(workspace, chosen) == chosen.resolve()


def test_the_environment_variable_is_read_against_the_workspace(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """It usually arrives from the workspace's own `.env`, not from a shell in that tree."""

    workspace = _workspace_with(tmp_path, "models.ollama.yaml")
    monkeypatch.setenv("ARCHCOMPASS_MODELS_CONFIG", "config/models.ollama.yaml")
    monkeypatch.chdir(tmp_path.parent)

    assert resolve_config_path(workspace) == (
        workspace / "config" / "models.ollama.yaml"
    ).resolve()


def test_a_working_directory_env_file_supplies_credentials_but_not_the_configuration(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A key travels with whoever runs the command; a workspace's models do not.

    Found by a repository that is itself a workspace: its `.env` was deciding the models
    for every other workspace driven from inside it, including the temporary ones this
    suite builds.
    """

    working_directory = tmp_path / "somewhere"
    working_directory.mkdir()
    (working_directory / ".env").write_text(
        "GOOGLE_API_KEY=from-the-working-directory\n"
        "ARCHCOMPASS_MODELS_CONFIG=config/models.google.yaml\n",
        encoding="utf-8",
    )
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    monkeypatch.chdir(working_directory)
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    monkeypatch.delenv("ARCHCOMPASS_MODELS_CONFIG", raising=False)

    load_provider_environment(workspace)

    assert os.environ["GOOGLE_API_KEY"] == "from-the-working-directory"
    assert "ARCHCOMPASS_MODELS_CONFIG" not in os.environ


def test_a_workspace_env_file_may_name_its_own_configuration(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workspace = _workspace_with(tmp_path, "models.ollama.yaml")
    (workspace / ".env").write_text(
        "ARCHCOMPASS_MODELS_CONFIG=config/models.ollama.yaml\n", encoding="utf-8"
    )
    monkeypatch.delenv("ARCHCOMPASS_MODELS_CONFIG", raising=False)

    load_provider_environment(workspace)

    assert os.environ["ARCHCOMPASS_MODELS_CONFIG"] == "config/models.ollama.yaml"
