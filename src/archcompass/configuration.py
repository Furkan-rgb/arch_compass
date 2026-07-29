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


def load_environment_file(path: Path, *, skip: frozenset[str] = frozenset()) -> None:
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
        if not name or name in os.environ or name in skip:
            continue
        value = raw_value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        os.environ[name] = value


#: Settings a `.env` may only supply for its own workspace. A credential travels with the
#: person running the command, which is why the working directory's file is consulted at
#: all; which models a workspace uses does not. A repository that is itself a workspace
#: would otherwise decide the models for every other workspace driven from inside it —
#: including the temporary ones a test suite builds, which is how this was found.
WORKSPACE_ONLY_VARIABLES: frozenset[str] = frozenset({"ARCHCOMPASS_MODELS_CONFIG"})


def load_provider_environment(workspace: Path) -> None:
    """Load provider credentials for a run, from the workspace and then the caller's cwd.

    A workspace is not always the directory the command was run from - it is a `--workspace`
    argument, and under test it is a temporary directory - so reading only the workspace
    would leave a correctly configured project unable to find its own key. Both locations
    are consulted and neither is required.

    The workspace file is read first and so wins, because it is the more specific of the
    two; a variable already exported wins over both. The working directory's file is read
    for credentials only: see `WORKSPACE_ONLY_VARIABLES`.
    """

    workspace_file = (workspace / ENVIRONMENT_FILE_NAME).resolve()
    load_environment_file(workspace_file)
    working_directory_file = (Path.cwd() / ENVIRONMENT_FILE_NAME).resolve()
    if working_directory_file != workspace_file:
        load_environment_file(working_directory_file, skip=WORKSPACE_ONLY_VARIABLES)


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
    #: Whether the model reasons before answering: `true` to require it, `false` to
    #: forbid it, absent to leave the model to its own default. Every stage here asks for
    #: one judgement about supplied evidence, so this is a property of the configured model
    #: rather than of any stage.
    #:
    #: The third state is not decoration. Measured on `gemma4:26b` against the scored
    #: example, the three settings differ in every direction: `true` took 510s and scored
    #: 4/6, `false` took 40s and scored 3/6, and leaving it to the model took ~250s and
    #: scored 5-6/6. A boolean alone could not express the best of those.
    #:
    #: Thinking tokens are spent from `max_output_tokens` on both providers, so requiring
    #: it on a tight output budget can leave the structured answer truncated — which
    #: surfaces as a validation failure rather than as a silently wrong answer.
    thinking: bool | None = None

    @model_validator(mode="after")
    def output_fits_context_window(self) -> ReasoningModelConfig:
        if self.max_output_tokens > self.context_window_tokens:
            raise ValueError(
                "max_output_tokens must not exceed context_window_tokens"
            )
        return self


class ModelsConfig(DomainModel):
    """The one model a workspace configures.

    An embedding model was configured here too, for a policy index that ranked the corpus
    against a query. Nothing ranks it: every policy is presented to the judging stage in one
    request and the conversation carries the corpus whole (ADR 0013), so the setting asked a
    user to choose a model that decided nothing.

    `extra="forbid"` is inherited and deliberate here. A workspace `models.yaml` still
    carrying `embedding:` or `retrieval:` is refused by name rather than quietly ignored —
    ADR 0002 — so the message says which block to delete instead of leaving a reader to
    wonder why a setting stopped mattering.
    """

    reasoning: ReasoningModelConfig


class AppConfig(DomainModel):
    models: ModelsConfig

    @property
    def identity_hash(self) -> str:
        return stable_id("cfg", canonical_json(self))


#: Where a workspace keeps model configurations, and the name of the one written for a
#: workspace that has none.
CONFIG_DIRECTORY = "config"
DEFAULT_CONFIG_NAME = "models.yaml"
#: `models.ollama.yaml`, `models.google.yaml` — a configuration named for what it points
#: at. A workspace that keeps several is choosing between providers, not accumulating
#: leftovers, so one of them is what it means by "the configuration".
NAMED_CONFIG_PATTERN = "models.*.yaml"


def resolve_config_path(workspace: Path, explicit: Path | None = None) -> Path:
    """The configuration this run was pointed at, or the one its workspace holds.

    Being pointed at one comes first and settles it, whatever the file is called:
    `--models-config`, or `ARCHCOMPASS_MODELS_CONFIG` — exported, or in the workspace's own
    `.env`, where a relative path is read against the workspace rather than against wherever
    the command was typed.

    Only when nothing points anywhere does the name matter, and then only to find what is
    already there: `models.yaml` if the workspace has one, otherwise the single
    `models.<provider>.yaml` it keeps. `models.yaml` is what gets written into a workspace
    that has no configuration at all — a default to create, not a file to require.

    Several configurations and nothing choosing between them is not something to guess at:
    which provider a review runs against decides what it costs and how long it takes. That
    case says so and names the files.

    Callers must load the workspace's `.env` first. Resolving before that is how this
    silently ignored a workspace that had said exactly which configuration it wanted.
    """

    if explicit is not None:
        return explicit.expanduser().resolve()
    directory = (workspace / CONFIG_DIRECTORY).resolve()
    from_env = os.environ.get("ARCHCOMPASS_MODELS_CONFIG")
    if from_env:
        chosen = Path(from_env).expanduser()
        return chosen.resolve() if chosen.is_absolute() else (workspace / chosen).resolve()
    default = directory / DEFAULT_CONFIG_NAME
    if default.is_file():
        return default
    named = sorted(path for path in directory.glob(NAMED_CONFIG_PATTERN) if path.is_file())
    if len(named) == 1:
        return named[0].resolve()
    if named:
        offered = ", ".join(path.name for path in named)
        raise ConfigurationError(
            f"{directory} holds more than one model configuration ({offered}) and nothing "
            "says which to run against. Name one with --models-config, or with "
            f"ARCHCOMPASS_MODELS_CONFIG in {workspace / ENVIRONMENT_FILE_NAME} — any path "
            "will do; the file does not have to be called anything in particular."
        )
    return default


def load_config(path: Path) -> AppConfig:
    if not path.is_file():
        raise ConfigurationError(f"Model configuration does not exist: {path}")
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
        return AppConfig.model_validate(raw)
    except (OSError, yaml.YAMLError, ValidationError) as error:
        raise ConfigurationError(f"Invalid model configuration {path}: {error}") from error
