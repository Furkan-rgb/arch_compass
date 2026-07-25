"""Single-source runtime configuration loading."""

from __future__ import annotations

import os
from importlib.resources import files
from pathlib import Path

import yaml
from pydantic import Field, ValidationError, model_validator

from archcompass.domain import budgets
from archcompass.domain.base import DomainModel, canonical_json, stable_id
from archcompass.domain.errors import ConfigurationError


def default_config_text() -> str:
    """Return the packaged default model configuration."""
    return files("archcompass.resources").joinpath("models.yaml").read_text(encoding="utf-8")



class ReasoningModelConfig(DomainModel):
    provider: str
    model: str
    base_url: str
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
    base_url: str
    dimensions: int = Field(gt=0)
    timeout_seconds: float = Field(gt=0)


class ModelsConfig(DomainModel):
    reasoning: ReasoningModelConfig
    embedding: EmbeddingModelConfig


class RetrievalConfig(DomainModel):
    top_k: int = Field(default=6, ge=1, le=100)
    max_sections_per_policy: int = Field(default=3, ge=1, le=3)


class ConsultationConfig(DomainModel):
    max_zoom_iterations: int = Field(default=3, ge=0, le=10)
    max_queries_per_iteration: int = Field(default=8, ge=1, le=20)
    max_query_results: int = Field(default=30, ge=1, le=100)
    max_excerpt_lines: int = Field(default=80, ge=1, le=200)


class ConversationConfig(DomainModel):
    """Per-turn budgets, bounded above by the mandated ceilings in `domain.budgets`.

    A workspace may lower any of these to tighten a run; none may be raised. Values
    that admit exactly one setting live in `domain.budgets` instead of here.
    """

    max_actions_per_question: int = Field(
        default=budgets.MAX_ACTIONS_PER_QUESTION, ge=1, le=budgets.MAX_ACTIONS_PER_QUESTION
    )
    max_findings: int = Field(default=budgets.MAX_FINDINGS, ge=1, le=budgets.MAX_FINDINGS)
    max_atlas_nodes: int = Field(
        default=budgets.MAX_ATLAS_NODES, ge=1, le=budgets.MAX_ATLAS_NODES
    )
    max_policies: int = Field(default=budgets.MAX_POLICIES, ge=1, le=budgets.MAX_POLICIES)
    max_neighbourhood_depth: int = Field(
        default=budgets.MAX_NEIGHBOURHOOD_DEPTH, ge=1, le=budgets.MAX_NEIGHBOURHOOD_DEPTH
    )
    max_excerpt_lines: int = Field(
        default=budgets.MAX_EXCERPT_LINES, ge=1, le=budgets.MAX_EXCERPT_LINES
    )
    max_total_excerpt_lines: int = Field(
        default=budgets.MAX_TOTAL_EXCERPT_LINES, ge=1, le=budgets.MAX_TOTAL_EXCERPT_LINES
    )
    #: None derives the budget from the reasoning model's context window; a value
    #: lowers it explicitly (useful in tests and for deliberately terse turns).
    max_retrieved_text_characters: int | None = Field(
        default=None,
        ge=budgets.MIN_RETRIEVED_TEXT_CHARACTERS,
    )
    recent_message_limit: int = Field(
        default=budgets.RECENT_MESSAGE_LIMIT, ge=1, le=budgets.RECENT_MESSAGE_LIMIT
    )
    max_summary_characters: int = Field(
        default=budgets.MAX_SUMMARY_CHARACTERS, ge=500, le=budgets.MAX_SUMMARY_CHARACTERS
    )


class AppConfig(DomainModel):
    models: ModelsConfig
    retrieval: RetrievalConfig = Field(default_factory=RetrievalConfig)
    consultation: ConsultationConfig = Field(default_factory=ConsultationConfig)
    conversation: ConversationConfig = Field(default_factory=ConversationConfig)

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
