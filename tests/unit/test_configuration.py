from __future__ import annotations

import pytest
from pydantic import ValidationError

from archcompass.configuration import ConversationConfig, ReasoningModelConfig


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


def test_conversation_summary_batches_are_fixed_at_twelve_then_eight() -> None:
    assert ConversationConfig().summarize_after_messages == 12
    assert ConversationConfig().summarize_every_messages == 8

    with pytest.raises(ValidationError):
        ConversationConfig(summarize_after_messages=10)
    with pytest.raises(ValidationError):
        ConversationConfig(summarize_every_messages=6)
