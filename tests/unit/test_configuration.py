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


def test_a_working_directory_env_file_supplies_credentials(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A key travels with whoever runs the command, so the file beside them is read too.

    `--workspace` points elsewhere, and under test it is a temporary directory, so reading
    only the workspace left a correctly configured project unable to find its own key.

    Nothing else travels that way any more. The variable a working directory was once
    forbidden to supply named which model configuration to run against, and a repository
    that is itself a workspace was deciding the models for every other workspace driven
    from inside it — including the temporary ones this suite builds. There are no
    configurations left to name.
    """

    working_directory = tmp_path / "somewhere"
    working_directory.mkdir()
    (working_directory / ".env").write_text(
        "GOOGLE_API_KEY=from-the-working-directory\n", encoding="utf-8"
    )
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    monkeypatch.chdir(working_directory)
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)

    load_provider_environment(workspace)

    assert os.environ["GOOGLE_API_KEY"] == "from-the-working-directory"
