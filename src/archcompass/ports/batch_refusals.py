"""Which API keys the provider's batch facility has already turned away."""

from __future__ import annotations

from hashlib import sha256
from typing import Protocol


def fingerprint_key(api_key: str) -> str:
    """A key as something that can be compared and not read back."""

    return sha256(api_key.encode("utf-8")).hexdigest()[:32]


class BatchRefusalStore(Protocol):
    """A refusal is about the project behind the key, so it outlives the process.

    `400 FAILED_PRECONDITION` from the Gemini Batch API is what a project that is not
    eligible for batching answers, and it is the same answer tomorrow. Holding that only in
    memory cost a rejected submission on the first review of every session — and, because
    the graph routes on `supports_batch` before anything has been submitted, it also showed
    that review's reader a notice saying a batch had been queued while every candidate was
    judged interactively.

    Keyed by the key, not by the provider: swapping in a key on an eligible project has to
    get a fresh answer. What is stored is a fingerprint, because this has to answer "was
    this one refused" and has no business being able to reproduce a credential.
    """

    def refused(self, api_key: str) -> bool: ...

    def record(self, api_key: str) -> None: ...


class InMemoryBatchRefusals:
    """The default, for a process with nowhere to write: forgotten on exit."""

    def __init__(self) -> None:
        self._refused: set[str] = set()

    def refused(self, api_key: str) -> bool:
        return fingerprint_key(api_key) in self._refused

    def record(self, api_key: str) -> None:
        self._refused.add(fingerprint_key(api_key))
