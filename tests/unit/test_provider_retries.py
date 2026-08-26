"""Waiting out a provider that is refusing for the moment, and not waiting for anything else."""

from __future__ import annotations

import pytest

from archcompass.domain.errors import NoEligibleProviderError, ProviderError
from archcompass.retrying import (
    RetryPolicy,
    call_with_retry,
    ineligible_reason,
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


class _NotFound(Exception):
    """What `langchain-openai` raises for any 404: a name that says the model is gone."""

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.status_code = 404


#: The three sentences OpenRouter was observed to refuse a well-formed request with, one per
#: filter that can empty the route set: the account's data policy, the parameters on the
#: request, and an explicit provider preference. All three are 404, and an unknown model is
#: a 400 reading "… is not a valid model ID" — so none of these is about the model.
INELIGIBLE = (
    "Error code: 404 - {'error': {'message': 'No endpoints available matching your "
    "guardrail restrictions and data policy. Configure: "
    "https://openrouter.ai/settings/privacy', 'code': 404}}",
    "Error code: 404 - {'error': {'message': 'No endpoints found that can handle the "
    "requested parameters.', 'code': 404}}",
    "Error code: 404 - {'error': {'message': 'No allowed providers are available for the "
    "selected model. Providers serving openai/gpt-5.6-luna-pro-20260709: azure, openai, "
    "but your request's provider.only preference permits only: cerebras.', 'code': 404}}",
)


@pytest.mark.parametrize("refusal", INELIGIBLE)
def test_a_route_that_was_filtered_away_is_not_a_missing_model(refusal: str) -> None:
    """The SDK's name for the status is wrong, and the name is what a reader acts on.

    A 404 here means the gateway had endpoints and was not allowed to use any of them.
    Reported as `OpenAIModelNotFoundError` it reads as "that model does not exist", which
    sends a person to the model picker to choose something else — when the model is fine and
    the thing to change is what their account permits.
    """

    calls: list[int] = []

    def operation() -> str:
        calls.append(1)
        raise _NotFound(refusal)

    with pytest.raises(NoEligibleProviderError) as failure:
        call_with_retry(operation, subject="Judging a candidate", sleep=Recorder())

    # Once. The filters that excluded every route exclude them again four seconds later.
    assert len(calls) == 1
    assert "Judging a candidate" in str(failure.value)
    # And it is not the type anything softens: two call sites turn a `ProviderError` into a
    # graceful end, and doing that here would send the same impossible request again.
    assert not isinstance(failure.value, ProviderError)


def test_the_gateway_s_own_reason_survives_the_renaming() -> None:
    """Which filter emptied the route set is the whole of the remedy.

    Nothing else can reconstruct it: "no eligible provider" alone does not say whether to
    change a data policy, a provider preference, or the request.
    """

    def operation() -> str:
        raise _NotFound(INELIGIBLE[2])

    with pytest.raises(NoEligibleProviderError) as failure:
        call_with_retry(operation, subject="A finding", sleep=Recorder())

    said = str(failure.value)
    assert "provider.only preference permits only: cerebras" in said
    assert "azure, openai" in said


def test_the_refusal_is_read_through_the_chain_like_every_other() -> None:
    """It reaches here under an SDK wrapper when it is raised inside the HTTP client."""

    assert ineligible_reason(_chained(_NotFound(INELIGIBLE[0]))) is not None
    assert ineligible_reason(_chained(ValueError("no endpoints were indexed"))) is None


def test_a_rate_limit_is_still_waited_out_and_not_renamed() -> None:
    """Transient is decided first, so a temporary refusal keeps its retries.

    The two are told apart by status, not by wording, which is what stops a 429 that happens
    to mention endpoints from being reported as permanent.
    """

    attempts: list[int] = []
    sleep = Recorder()

    def operation() -> str:
        attempts.append(1)
        if len(attempts) < 2:
            raise RateLimited(429, "no endpoints available right now")
        return "judged"

    assert call_with_retry(operation, subject="A finding", sleep=sleep) == "judged"
    assert len(attempts) == 2


def test_the_api_says_unavailable_without_saying_try_again() -> None:
    """503 like any other unavailability, and its own code, and not retryable.

    `provider_unavailable` promises a fleet that is recovering; this one is not. Nothing
    changes until somebody widens what the account permits, so a client that reads the flag
    and retries would spend the whole schedule learning that.
    """

    from archcompass.presentation.web.errors import classify_error

    status, code, retryable = classify_error(
        NoEligibleProviderError("no provider route was allowed to carry it")
    )

    assert (status, code, retryable) == (503, "no_eligible_provider", False)
    # And the plain provider failure is untouched: that one really is worth trying again.
    assert classify_error(ProviderError("503 from upstream")) == (
        503,
        "provider_unavailable",
        True,
    )
