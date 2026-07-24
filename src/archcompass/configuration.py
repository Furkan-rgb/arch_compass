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


# Backwards-compatible import for callers that previously consumed the template.
DEFAULT_CONFIG_TEXT = default_config_text()


class ReasoningModelConfig(DomainModel):
    provider: str
    model: str
    base_url: str
    timeout_seconds: float = Field(gt=0)
    context_window_tokens: int = Field(default=32768, ge=512)
    max_output_tokens: int = Field(default=16384, ge=512, le=32768)

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
    max_actions_per_question: int = Field(default=8, ge=1, le=8)
    max_findings: int = Field(default=12, ge=1, le=12)
    max_atlas_nodes: int = Field(default=24, ge=1, le=24)
    max_policies: int = Field(default=8, ge=1, le=8)
    max_neighbourhood_depth: int = Field(default=2, ge=1, le=2)
    max_excerpt_lines: int = Field(default=120, ge=1, le=120)
    max_total_excerpt_lines: int = Field(default=180, ge=1, le=180)
    max_retrieved_text_characters: int = Field(default=24_000, ge=1000, le=24_000)
    recent_message_limit: int = Field(default=8, ge=1, le=8)
    summarize_after_messages: int = Field(default=12, ge=12, le=12)
    summarize_every_messages: int = Field(default=8, ge=8, le=8)
    max_summary_characters: int = Field(default=6000, ge=500, le=6000)


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
