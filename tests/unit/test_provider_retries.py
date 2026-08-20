"""Waiting out a provider that is refusing for the moment, and not waiting for anything else."""

from __future__ import annotations

import warnings

import pytest
from langchain_core.messages import HumanMessage

from archcompass.configuration import ReasoningModelConfig
from archcompass.domain.errors import ProviderError
from archcompass.reasoning.adapters.factory import build_chat_model
from archcompass.reasoning.adapters.providers import (
    GOOGLE_FIXED_SAMPLING_MODELS,
    GOOGLE_MODELS,
)
from archcompass.retrying import (
    RetryPolicy,
    call_with_retry,
    is_transient,
    suggested_delay,
)


class RateLimited(Exception):
    """What a hosted SDK raises: the status is on the exception, not in the text."""

    def __init__(self, code: int, message: str = "") -> None:
        super().__init__(message or f"{code} RESOURCE_EXHAUSTED")
        self.code = code


class Recorder:
    """A `sleep` that records instead of spending the time."""

    def __init__(self) -> None:
        self.waits: list[float] = []

    def __call__(self, seconds: float) -> None:
        self.waits.append(seconds)


def test_a_rate_limited_call_succeeds_on_a_later_attempt() -> None:
    attempts: list[int] = []
    sleep = Recorder()

    def operation() -> str:
        attempts.append(len(attempts) + 1)
        if len(attempts) < 3:
            raise RateLimited(429)
        return "judged"

    assert call_with_retry(operation, subject="A finding", sleep=sleep) == "judged"
    assert len(attempts) == 3
    # Growing rather than repeating: three waits four seconds apart would all land inside
    # the same exhausted minute the first one was refused in.
    assert sleep.waits == [4.0, 12.0]


def test_the_provider_is_asked_at_most_four_times() -> None:
    calls: list[int] = []
    sleep = Recorder()

    def operation() -> str:
        calls.append(1)
        raise RateLimited(429)

    with pytest.raises(ProviderError) as failure:
        call_with_retry(operation, subject="A finding", sleep=sleep)

    assert len(calls) == 4
    assert sleep.waits == [4.0, 12.0, 36.0]
    # The report says it was temporary, so a caller reading it knows to try again rather
    # than to change the request.
    assert "refused 4 times" in str(failure.value)


def test_a_refusal_about_the_request_is_raised_immediately() -> None:
    sleep = Recorder()

    def operation() -> str:
        raise RateLimited(400, "400 INVALID_ARGUMENT. The request is malformed.")

    # Not a ProviderError, and not retried: sending it again produces the same answer
    # three times more slowly.
    with pytest.raises(RateLimited):
        call_with_retry(operation, subject="A finding", sleep=sleep)
    assert sleep.waits == []


def test_the_delay_the_provider_asks_for_wins_over_the_schedule() -> None:
    sleep = Recorder()
    detail = (
        "429 RESOURCE_EXHAUSTED. {'error': {'code': 429, 'details': [{'@type': "
        "'type.googleapis.com/google.rpc.RetryInfo', 'retryDelay': '23s'}]}}"
    )
    calls: list[int] = []

    def operation() -> str:
        calls.append(1)
        if len(calls) == 1:
            raise RateLimited(429, detail)
        return "judged"

    assert call_with_retry(operation, subject="A finding", sleep=sleep) == "judged"
    assert sleep.waits == [23.0]


def test_a_wait_is_capped_however_long_the_provider_asks_for() -> None:
    sleep = Recorder()

    def operation() -> str:
        raise RateLimited(429, "429 RESOURCE_EXHAUSTED. 'retryDelay': '3600s'")

    with pytest.raises(ProviderError):
        call_with_retry(
            operation,
            subject="A finding",
            policy=RetryPolicy(retries=1),
            sleep=sleep,
        )
    assert sleep.waits == [60.0]


@pytest.mark.parametrize("status", [429, 500, 502, 503, 504])
def test_statuses_a_wait_can_fix(status: int) -> None:
    assert is_transient(RateLimited(status))


@pytest.mark.parametrize("status", [400, 401, 403, 404, 408, 422])
def test_statuses_a_wait_cannot_fix(status: int) -> None:
    assert not is_transient(RateLimited(status))


def test_a_provider_that_carries_no_status_is_read_from_its_words() -> None:
    assert is_transient(RuntimeError("model is overloaded, please try again"))
    assert not is_transient(RuntimeError("model 'gemma9' was not found"))


def test_no_delay_is_read_when_the_provider_names_none() -> None:
    assert suggested_delay(RuntimeError("429 RESOURCE_EXHAUSTED")) is None


def test_the_supported_google_models_are_the_only_ones_classified() -> None:
    """The sampling list is about models this workspace offers, so it cannot outlive them.

    If `GOOGLE_MODELS` gains a model, this fails until someone has said which of the two
    kinds it is — which is the moment to check, rather than the first time a run warns.
    """

    assert set(GOOGLE_MODELS) >= GOOGLE_FIXED_SAMPLING_MODELS


@pytest.mark.parametrize("model", sorted(GOOGLE_MODELS))
def test_a_google_model_is_sent_a_temperature_only_if_it_takes_one(
    model: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A discarded parameter warns on every call and buys no determinism.

    The assertion is on the request the SDK builds rather than on our own list, so the
    check is against the provider's behaviour and not against a restatement of the code.
    """

    monkeypatch.setenv("GOOGLE_API_KEY", "not-a-real-key")
    chat = build_chat_model(
        ReasoningModelConfig(
            provider="google",
            model=model,
            api_key_env="GOOGLE_API_KEY",
            timeout_seconds=30,
        )
    )
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        chat._prepare_request([HumanMessage("judge this")], tools=None)

    assert [str(item.message) for item in caught] == []
    fixed = model in GOOGLE_FIXED_SAMPLING_MODELS
    assert (chat.temperature is None) is fixed
