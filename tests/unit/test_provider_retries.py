"""Waiting out a provider that is refusing for the moment, and not waiting for anything else."""

from __future__ import annotations

import pytest

from archcompass.domain.errors import ProviderError
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
    assert sleep.waits == [4.0, 8.0]


def test_the_provider_is_asked_at_most_six_times() -> None:
    calls: list[int] = []
    sleep = Recorder()

    def operation() -> str:
        calls.append(1)
        raise RateLimited(429)

    with pytest.raises(ProviderError) as failure:
        call_with_retry(operation, subject="A finding", sleep=sleep)

    assert len(calls) == 6
    assert sleep.waits == [4.0, 8.0, 16.0, 32.0, 60.0]
    # The report says it was temporary, so a caller reading it knows to try again rather
    # than to change the request.
    assert "refused 6 times" in str(failure.value)


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


class _Wrapped(Exception):
    """What an SDK raises over whatever the transport threw. No status of its own."""


def _chained(cause: BaseException) -> _Wrapped:
    outer = _Wrapped("Connection error.")
    outer.__cause__ = cause
    return outer


def test_a_status_survives_being_re_raised_by_an_sdk() -> None:
    """The wrapper does not change what the provider said.

    An in-body error is raised from inside the HTTP client, and the OpenAI SDK catches that
    and re-raises `APIConnectionError("Connection error.")` over it — no status, no phrase.
    Read only at the surface, a 429 that should cost four seconds ends the review instead.
    """

    rate_limited = ProviderError("The provider answered 200 with an error in the body: busy")
    rate_limited.status_code = 429  # type: ignore[attr-defined]

    assert is_transient(_chained(rate_limited))


def test_a_permanent_status_survives_the_same_trip() -> None:
    """Looking through the chain must not make everything look temporary."""

    broke = ProviderError("Insufficient credits")
    broke.status_code = 402  # type: ignore[attr-defined]

    assert not is_transient(_chained(broke))


def test_a_phrase_is_read_through_the_chain_too() -> None:
    """A provider that names no status still says what happened, one layer down."""

    assert is_transient(_chained(ProviderError("upstream is overloaded, try later")))


def test_the_delay_a_provider_asks_for_survives_the_chain() -> None:
    """The wait the quota is actually keeping is better than any schedule of ours."""

    asked = ProviderError("429 RESOURCE_EXHAUSTED {'retryDelay': '36s'}")

    assert suggested_delay(_chained(asked)) == 36.0


def test_an_unrelated_exception_two_layers_down_is_not_read_as_a_rate_limit() -> None:
    """The chain is walked because a status gets buried, not so that anything counts."""

    assert not is_transient(_chained(ValueError("a candidate id was malformed")))
