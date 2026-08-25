"""Credentials from the environment, and the one shape a transport is handed.

Nothing here is read from a file any more. Which providers exist, where they are reached
and what their budgets are is stated in code, one descriptor per adapter module; the only
thing this process still reads off disk is a `.env`, and only ever for a secret.
"""

from __future__ import annotations

import os
from pathlib import Path

from pydantic import Field, model_validator

from archcompass.domain.errors import ConfigurationError
from archcompass.records import BoundaryDTO, ThinkingMode

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

    Both files are read whole. There was a variable a `.env` was allowed to set only for
    its own workspace — the one naming which model configuration to run against — and it
    exists no longer: a repository that is itself a workspace could otherwise decide the
    models for every other workspace driven from inside it, including the temporary ones a
    test suite builds. What is left is credentials, which travel with the person running the
    command and are the reason the working directory is consulted at all.
    """

    workspace_file = (workspace / ENVIRONMENT_FILE_NAME).resolve()
    load_environment_file(workspace_file)
    working_directory_file = (Path.cwd() / ENVIRONMENT_FILE_NAME).resolve()
    if working_directory_file != workspace_file:
        load_environment_file(working_directory_file)


def resolve_api_key(variable_name: str | None, *, provider: str) -> str:
    """Read a provider credential from the environment, naming the fix when absent.

    The key is referenced by variable name rather than carried in the provider's
    descriptor, because a descriptor is source code and a key is not something source code
    may hold. The value is read at call time so a rotated key takes effect without
    rebuilding anything.
    """

    if not variable_name:
        raise ConfigurationError(
            f"The {provider} provider names no api_key_env in its descriptor, so nothing "
            "says which environment variable holds the API key."
        )
    value = os.environ.get(variable_name, "").strip()
    if not value:
        raise ConfigurationError(
            f"The {provider} provider needs an API key: set {variable_name} in "
            f"{ENVIRONMENT_FILE_NAME} at the workspace root, or export it."
        )
    return value


class ReasoningModelConfig(BoundaryDTO):
    provider: str
    model: str
    #: Where the provider is reached. Required by a self-hosted provider such as
    #: Ollama; a hosted SDK that knows its own endpoint leaves it unset.
    base_url: str | None = None
    #: Names the environment variable holding this provider's API key - never the key.
    api_key_env: str | None = None
    timeout_seconds: float = Field(gt=0)
    context_window_tokens: int = Field(default=32768, ge=512)
    max_output_tokens: int = Field(default=16384, ge=512, le=65536)
    #: How many requests this provider is asked for at once — the bound on the candidate
    #: fan-out, which is otherwise as wide as the review has candidates. A property of the
    #: provider rather than of the review: see `ProviderDefaults.max_parallel_requests`.
    max_parallel_requests: int = Field(default=8, ge=1)
    #: Whether the model reasons before answering: `true` to require it, `false` to
    #: forbid it, absent to leave the model to its own default. Every stage here asks for
    #: one judgement about supplied evidence, so this is a property of the chosen model
    #: rather than of any stage.
    #:
    #: Three settings and three outcomes, and an adapter owes all three however its own API
    #: spells them. `true` in particular must reach the provider as an instruction and never
    #: decay into absence: a request that says nothing gets the model's default, and defaults
    #: are a property of the model rather than of the API — `gemini-3.6-flash` reasons
    #: without being asked and `gemini-3.5-flash-lite` does not. Where a provider takes a
    #: level rather than a flag, requiring it means naming one. Where a model cannot think at
    #: all, the honest answer is the provider's refusal, not a quiet run without it.
    #:
    #: Thinking tokens are spent from `max_output_tokens` on both providers, so requiring
    #: it on a tight output budget can leave the structured answer truncated — which
    #: surfaces as a validation failure rather than as a silently wrong answer.
    #: A level where the provider has levels: `minimal`, `low`, `medium` or `high`. Gemini
    #: 3 takes exactly these and has no boolean at all, so `true` there is read as `high` and
    #: `false` as `minimal` — the floor, because a Gemini 3 model cannot be told to stop
    #: thinking. That is an approximation and it is named here rather than hidden: where the
    #: distinction matters, name the level.
    thinking: ThinkingMode = None

    @model_validator(mode="after")
    def output_fits_context_window(self) -> ReasoningModelConfig:
        if self.max_output_tokens > self.context_window_tokens:
            raise ValueError(
                "max_output_tokens must not exceed context_window_tokens"
            )
        return self


class EmbeddingModelConfig(BoundaryDTO):
    provider: str
    model: str
    dimensions: int = Field(ge=1)
    base_url: str | None = None
    api_key_env: str | None = None
