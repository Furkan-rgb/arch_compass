"""Strategy-neutral verdict reuse around one ArchitectureJudge capability call."""

from __future__ import annotations

from collections.abc import Callable
from hashlib import sha256
from typing import Protocol

from archcompass.domain import (
    ArchitectureCase,
    Candidate,
    Finding,
    RecordedInvestigation,
    Review,
)
from archcompass.ports.capabilities import (
    ArchitectureJudge,
    ReviewRecorder,
)
from archcompass.ports.policy_retrieval import RetrievedPolicySet


class FindingCache(Protocol):
    def get(self, key: str) -> Finding | None: ...

    def put(self, key: str, finding: Finding) -> Finding: ...

    def record_sources(self, review: Review) -> None: ...


class CachingReviewRecorder:
    """Record the review, then make it the provenance source for fresh cache entries."""

    def __init__(self, reviews: ReviewRecorder, cache: FindingCache) -> None:
        self._reviews = reviews
        self._cache = cache

    def record(self, review: Review) -> Review:
        recorded = self._reviews.record(review)
        self._cache.record_sources(recorded)
        return recorded


class CachingArchitectureJudge:
    def __init__(
        self,
        judge: ArchitectureJudge,
        cache: FindingCache,
        *,
        model_identity: Callable[[], str],
        prompt_identity: Callable[[], str],
    ) -> None:
        self._judge = judge
        self._cache = cache
        self._model_identity = model_identity
        self._prompt_identity = prompt_identity

    def judge(
        self,
        candidate: Candidate,
        case: ArchitectureCase,
        policies: RetrievedPolicySet,
        investigation: RecordedInvestigation | None = None,
    ) -> Finding:
        key = self.key(candidate, case, policies, investigation)
        cached = self._cache.get(key)
        if cached is not None:
            return cached
        return self._cache.put(
            key, self._judge.judge(candidate, case, policies, investigation)
        )

    def key(
        self,
        candidate: Candidate,
        case: ArchitectureCase,
        policies: RetrievedPolicySet,
        investigation: RecordedInvestigation | None = None,
    ) -> str:
        # The investigation is in the key, and it has to be. A candidate is judged twice —
        # once on its evidence, once again on what a hinge investigation established — with
        # the same candidate, the same case and the same retrieval both times. Without this
        # the second call is a cache hit on the first, and the whole second judgement
        # silently returns the verdict that was reached before anything was looked up.
        # `identity` rather than the record: it is a content hash of every lookup, its
        # arguments and its answer, so two different investigations cannot share a key.
        material = repr(
            (
                candidate,
                case,
                policies.provenance.identity,
                investigation.identity if investigation else "",
                self._model_identity(),
                self._prompt_identity(),
            )
        )
        return sha256(material.encode()).hexdigest()
