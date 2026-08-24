"""Retrying a provider call that failed for a reason waiting can fix.

A hosted model is a shared resource, and the free tiers say so: `gemini-3.5-flash-lite`
answers 429 several times during one review of a modest repository, and the policy corpus
is embedded in groups that reach the same limit. Every one of those refusals is a
statement about the next few seconds rather than about the request, so failing the whole
review on the first of them throws away minutes of work that a short wait would have saved.

Deliberately narrow. Only a refusal the provider itself describes as temporary is retried;
a malformed request, a missing key and a model that does not exist all fail immediately,
because sending them again produces the same answer three times more slowly. Timeouts are
not retried either: our own deadline arriving from the other side means the prompt took
longer than we allow, and waiting does not shorten it.
"""

from __future__ import annotations

import logging
import re
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Final

from archcompass.domain.errors import ProviderError

_log = logging.getLogger("archcompass.retries")

#: Statuses where the identical request, sent later, can succeed. 429 is the one that
#: matters in practice; the 5xx entries are a fleet briefly out of capacity, which Gemini
#: reports as 503 UNAVAILABLE and, under load, as 500 INTERNAL.
#:
#: Not here: 400, 401, 403 and 404, which describe the request rather than the moment, and
#: 408, which is a deadline that a wait cannot make more generous.
TRANSIENT_STATUSES: Final = frozenset({429, 500, 502, 503, 504})

#: Read only when an exception carries no status at all. Matching words is guesswork, and
#: guessing is worth it only where the alternative is no information — a provider that does
#: carry a status has already answered the question precisely.
_TRANSIENT_PHRASES: Final = (
    "resource_exhausted",
    "resource exhausted",
    "rate limit",
    "ratelimit",
    "too many requests",
    "overloaded",
)

#: Google puts a `RetryInfo` detail beside a 429 saying how long its own quota window has
#: left to run — `'retryDelay': '36s'`. It is a better number than any schedule of ours
#: because it is the one the quota is actually keeping, so it is used when it is offered.
#: Read out of the rendered exception rather than out of a parsed body: the detail reaches
#: us through several SDK layers that each re-wrap it, and the string survives all of them.
_RETRY_DELAY = re.compile(
    r"retry[_-]?delay['\"]?\s*[:=]\s*['\"]?(\d+(?:\.\d+)?)s",
    re.IGNORECASE,
)


#: How far down a chain to look. Three is the deepest any of the SDKs here nests: the
#: OpenAI client re-raises its own `APIConnectionError` over whatever the transport threw,
#: and LangChain occasionally puts one more layer over that.
_CHAIN_DEPTH: Final = 4


def _chain(error: BaseException) -> list[BaseException]:
    """An exception and the ones it was raised over.

    Needed because a status does not always survive the trip. An SDK that catches a
    transport failure and re-raises its own type keeps the original on `__cause__` and
    throws the status away from the surface — so an in-body 429, which arrives as an
    exception raised inside the HTTP client, reaches this module as
    `OpenAIConnectionError("Connection error.")`: no status, no phrase, and therefore read
    as permanent. It is the same rate limit either way.

    `__context__` as well as `__cause__`, because not every re-raise says `from`. That is
    the looser of the two and it can reach an exception this call had nothing to do with;
    the depth cap is what bounds how far a wrong guess can travel, and both checks below
    are specific enough that an unrelated exception rarely answers yes to either.
    """

    found: list[BaseException] = []
    current: BaseException | None = error
    while current is not None and len(found) < _CHAIN_DEPTH:
        found.append(current)
        current = current.__cause__ or current.__context__
    return found


def _status_of(error: BaseException) -> int | None:
    """The HTTP status an exception carries, whatever its SDK calls the attribute."""

    for link in _chain(error):
        for attribute in ("code", "status_code"):
            value = getattr(link, attribute, None)
            if isinstance(value, int):
                return value
        response = getattr(link, "response", None)
        status = getattr(response, "status_code", None)
        if isinstance(status, int):
            return status
    return None


def is_transient(error: BaseException) -> bool:
    """Whether the provider is saying "not now" rather than "not this"."""

    status = _status_of(error)
    if status is not None:
        return status in TRANSIENT_STATUSES
    text = " ".join(str(link) for link in _chain(error)).lower()
    return any(phrase in text for phrase in _TRANSIENT_PHRASES)


def suggested_delay(error: BaseException) -> float | None:
    """The wait the provider asked for, if it named one."""

    found = _RETRY_DELAY.search(" ".join(str(link) for link in _chain(error)))
    return float(found.group(1)) if found else None


@dataclass(frozen=True, slots=True)
class RetryPolicy:
    """How many times to wait, and for how long.

    The defaults add up to two minutes across 5 retries (6 attempts total), ensuring
    that a per-minute quota window has fully closed before giving up. Growing the wait
    rather than repeating it matters for the same reason — several rapid attempts all
    land inside the same exhausted minute and fail together.
    """

    #: Attempts after the first one, so the default sends the request at most six times.
    retries: int = 5
    first_delay_seconds: float = 4.0
    multiplier: float = 2.0
    #: A ceiling on any single wait, including one the provider asks for. A review that has
    #: paused for a minute is better reported as failed than left looking hung.
    maximum_delay_seconds: float = 60.0

    def delay_before(self, retry: int) -> float:
        """The wait before retry `retry`, counting the first retry as 1."""

        grown = self.first_delay_seconds * self.multiplier ** (retry - 1)
        return min(grown, self.maximum_delay_seconds)


DEFAULT_RETRY_POLICY: Final = RetryPolicy()


def call_with_retry[T](
    operation: Callable[[], T],
    *,
    subject: str,
    policy: RetryPolicy = DEFAULT_RETRY_POLICY,
    sleep: Callable[[float], None] = time.sleep,
) -> T:
    """Run `operation`, waiting and repeating it while the provider says "not now".

    Anything else is re-raised untouched, so the caller still sees a schema violation or a
    bad key as itself. Exhausting the retries raises `ProviderError`, which is the one
    thing the rest of the application already knows how to report: 503, and worth trying
    again.
    """

    waited = 0.0
    last: Exception | None = None
    for attempt in range(policy.retries + 1):
        try:
            return operation()
        except Exception as error:
            if not is_transient(error):
                raise
            last = error
            if attempt == policy.retries:
                break
            delay = min(
                suggested_delay(error) or policy.delay_before(attempt + 1),
                policy.maximum_delay_seconds,
            )
            waited += delay
            # At warning level because it is a pause a reader of the log needs explained:
            # a review that stops for thirty seconds is otherwise indistinguishable from
            # one that has hung.
            _log.warning(
                "%s was refused by the provider (%s); waiting %.0fs before retry %d of %d",
                subject,
                error,
                delay,
                attempt + 1,
                policy.retries,
            )
            sleep(delay)

    raise ProviderError(
        f"{subject} was refused {policy.retries + 1} times by the provider over "
        f"{waited:.0f}s of waiting, and the refusals were temporary each time. "
        f"The last one was: {last}"
    ) from last
