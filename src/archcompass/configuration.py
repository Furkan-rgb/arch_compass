"""Single-source runtime configuration loading."""

from __future__ import annotations

import os
from importlib.resources import files
from pathlib import Path

import yaml
from pydantic import Field, ValidationError, model_validator

from archcompass.domain.base import DomainModel, canonical_json, stable_id
from archcompass.domain.errors import ConfigurationError


def default_config_text() -> str:
    """Return the packaged default model configuration."""
    return files("archcompass.resources").joinpath("models.yaml").read_text(encoding="utf-8")


ENVIRONMENT_FILE_NAME = ".env"


def load_environment_file(path: Path) -> None:
    """Read `KEY=value` lines into the environment, without overwriting what is set.

    Deliberately small: comments, blank lines, an optional `export` prefix, and
    surrounding quotes are all it understands. There is no interpolation and no
    multi-line value, because a credential does not need them and a parser that
    silently half-supports them is worse than one that plainly does not.

    A real environment variable always wins, so CI and a shell export override the
    file rather than the other way round. A missing file is not an error: not every
    workspace uses a hosted provider.
    """

    if not path.is_file():
        return
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as error:
        raise ConfigurationError(f"Could not read {path}: {error}") from error
    for line in lines:
        entry = line.strip()
        if not entry or entry.startswith("#"):
            continue
        entry = entry.removeprefix("export ").lstrip()
        name, separator, raw_value = entry.partition("=")
        if not separator:
            continue
        name = name.strip()
        if not name or name in os.environ:
            continue
        value = raw_value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        os.environ[name] = value


def load_provider_environment(workspace: Path) -> None:
    """Load provider credentials for a run, from the workspace and then the caller's cwd.

    A workspace is not always the directory the command was run from - it is a `--workspace`
    argument, and under test it is a temporary directory - so reading only the workspace
    would leave a correctly configured project unable to find its own key. Both locations
    are consulted and neither is required.

    The workspace file is read first and so wins, because it is the more specific of the
    two; a variable already exported wins over both.
    """

    seen: set[Path] = set()
    for directory in (workspace, Path.cwd()):
        candidate = (directory / ENVIRONMENT_FILE_NAME).resolve()
        if candidate in seen:
            continue
        seen.add(candidate)
        load_environment_file(candidate)


def resolve_api_key(variable_name: str | None, *, provider: str) -> str:
    """Read a provider credential from the environment, naming the fix when absent.

    The key is referenced by variable name rather than stored in `models.yaml`, because
    that file is committed and a workspace copy of it is shared. The value is read at
    call time so a rotated key takes effect without rebuilding configuration.
    """

    if not variable_name:
        raise ConfigurationError(
            f"The {provider} provider needs api_key_env in models.yaml, naming the "
            "environment variable that holds the API key."
        )
    value = os.environ.get(variable_name, "").strip()
    if not value:
        raise ConfigurationError(
            f"The {provider} provider needs an API key: set {variable_name} in "
            f"{ENVIRONMENT_FILE_NAME} at the workspace root, or export it."
        )
    return value


class ReasoningModelConfig(DomainModel):
    provider: str
    model: str
    #: Where the provider is reached. Required by a self-hosted provider such as
    #: Ollama; a hosted SDK that knows its own endpoint leaves it unset.
    base_url: str | None = None
    #: Names the environment variable holding this provider's API key - never the key.
    api_key_env: str | None = None
    timeout_seconds: float = Field(gt=0)
    #: Applied to short, low-token stages; falls back to `timeout_seconds` when unset,
    #: so a workspace configuration written before this existed behaves as it did.
    fast_timeout_seconds: float | None = Field(default=None, gt=0)
    #: Applied to stages that produce a full structured artifact.
    deep_timeout_seconds: float | None = Field(default=None, gt=0)
    context_window_tokens: int = Field(default=32768, ge=512)
    max_output_tokens: int = Field(default=16384, ge=512, le=32768)
    #: Characters per token used to estimate a request against the context window.
    #: Deliberately generous: over-estimating refuses a borderline request explicitly,
    #: while under-estimating lets the model silently truncate it.
    chars_per_token: float = Field(default=4.0, gt=0)

    @model_validator(mode="after")
    def output_fits_context_window(self) -> ReasoningModelConfig:
        if self.max_output_tokens > self.context_window_tokens:
            raise ValueError(
                "max_output_tokens must not exceed context_window_tokens"
            )
        return self


class EmbeddingModelConfig(DomainModel):
    provider: str
    model: str
    base_url: str | None = None
    api_key_env: str | None = None
    dimensions: int = Field(gt=0)
    timeout_seconds: float = Field(gt=0)


class ModelsConfig(DomainModel):
    reasoning: ReasoningModelConfig
    embedding: EmbeddingModelConfig


class RetrievalConfig(DomainModel):
    top_k: int = Field(default=6, ge=1, le=100)
    max_sections_per_policy: int = Field(default=3, ge=1, le=3)


class AppConfig(DomainModel):
    models: ModelsConfig
    retrieval: RetrievalConfig = Field(default_factory=RetrievalConfig)

    @property
    def identity_hash(self) -> str:
        return stable_id("cfg", canonical_json(self))


def resolve_config_path(workspace: Path, explicit: Path | None = None) -> Path:
    if explicit is not None:
        return explicit.expanduser().resolve()
    from_env = os.environ.get("ARCHCOMPASS_MODELS_CONFIG")
    if from_env:
        return Path(from_env).expanduser().resolve()
    return (workspace / "config" / "models.yaml").resolve()


def load_config(path: Path) -> AppConfig:
    if not path.is_file():
        raise ConfigurationError(f"Model configuration does not exist: {path}")
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
        return AppConfig.model_validate(raw)
    except (OSError, yaml.YAMLError, ValidationError) as error:
        raise ConfigurationError(f"Invalid model configuration {path}: {error}") from error
