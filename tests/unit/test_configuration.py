from __future__ import annotations

from typing import cast

import pytest
from pydantic import ValidationError

from archcompass.application.conversation_retrieval import (
    ConversationEvidenceRetriever,
)
from archcompass.configuration import ConversationConfig, ReasoningModelConfig
from archcompass.domain import budgets
from archcompass.ports.atlas import AtlasQueryService
from archcompass.ports.repositories import AtlasRepository


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


def test_conversation_summary_batches_are_constants_not_configuration() -> None:
    """Summary coverage admits exactly one setting, so it is not a config field."""

    assert budgets.SUMMARIZE_AFTER_MESSAGES == 12
    assert budgets.SUMMARIZE_EVERY_MESSAGES == 8

    with pytest.raises(ValidationError):
        ConversationConfig(summarize_after_messages=10)
    with pytest.raises(ValidationError):
        ConversationConfig(summarize_every_messages=6)


def test_conversation_budgets_may_be_lowered_but_never_raised() -> None:
    assert ConversationConfig(max_findings=2).max_findings == 2
    assert ConversationConfig().max_findings == budgets.MAX_FINDINGS

    with pytest.raises(ValidationError):
        ConversationConfig(max_findings=budgets.MAX_FINDINGS + 1)
    with pytest.raises(ValidationError):
        ConversationConfig(max_atlas_nodes=budgets.MAX_ATLAS_NODES + 1)


def test_retrieved_character_budget_tracks_the_model_window() -> None:
    """The evidence budget is derived from the configured window, not frozen.

    The former fixed 24,000-character ceiling could not fit one projected finding of
    the project's own evaluation fixture; a bigger window must mean a bigger budget,
    and an explicit configuration value may only narrow it.
    """

    small = budgets.retrieved_character_budget(
        context_window_tokens=8_192, max_output_tokens=4_096, chars_per_token=4.0
    )
    default = budgets.retrieved_character_budget(
        context_window_tokens=32_768, max_output_tokens=16_384, chars_per_token=4.0
    )
    large = budgets.retrieved_character_budget(
        context_window_tokens=131_072, max_output_tokens=16_384, chars_per_token=4.0
    )

    assert small < default < large
    assert default > 24_000, "the derived default must exceed the old frozen ceiling"
    assert (
        budgets.retrieved_character_budget(
            context_window_tokens=512, max_output_tokens=512, chars_per_token=4.0
        )
        == budgets.MIN_RETRIEVED_TEXT_CHARACTERS
    )

    assert ConversationConfig().max_retrieved_text_characters is None
    assert ConversationConfig(max_retrieved_text_characters=1_000)
    with pytest.raises(ValidationError):
        ConversationConfig(max_retrieved_text_characters=100)


def test_an_explicit_evidence_budget_can_only_narrow_the_derived_one() -> None:
    """Configuration may lower a derived budget, never raise it past the window."""

    reasoning = ReasoningModelConfig(
        provider="fake",
        model="deterministic",
        base_url="http://ollama.test",
        timeout_seconds=1,
    )
    derived = budgets.retrieved_character_budget(
        context_window_tokens=reasoning.context_window_tokens,
        max_output_tokens=reasoning.max_output_tokens,
        chars_per_token=reasoning.chars_per_token,
    )
    retriever = ConversationEvidenceRetriever(
        reasoning=reasoning,
        atlases=cast("AtlasRepository", object()),
        queries=cast("AtlasQueryService", object()),
        config=ConversationConfig(max_retrieved_text_characters=derived * 10),
    )

    assert retriever._character_budget == derived  # pyright: ignore[reportPrivateUsage]

    narrowed = ConversationEvidenceRetriever(
        reasoning=reasoning,
        atlases=cast("AtlasRepository", object()),
        queries=cast("AtlasQueryService", object()),
        config=ConversationConfig(max_retrieved_text_characters=1_000),
    )
    assert narrowed._character_budget == 1_000  # pyright: ignore[reportPrivateUsage]
