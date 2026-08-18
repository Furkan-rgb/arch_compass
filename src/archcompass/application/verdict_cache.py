"""Strategy-neutral verdict reuse around one ArchitectureJudge capability call."""

from __future__ import annotations

from collections.abc import Callable
from hashlib import sha256
from typing import Protocol

from archcompass.application.capabilities import ArchitectureJudge
from archcompass.domain import ArchitectureCase, Candidate, Finding, Review
from archcompass.ports.policy_retrieval import RetrievedPolicySet


class FindingCache(Protocol):
    def get(self, key: str) -> Finding | None: ...

    def put(self, key: str, finding: Finding) -> Finding: ...

    def record_sources(self, review: Review) -> None: ...


class ReviewStore(Protocol):
    def record(self, review: Review) -> Review: ...


class CachingReviewRecorder:
    """Record the review, then make it the provenance source for fresh cache entries."""

    def __init__(self, reviews: ReviewStore, cache: FindingCache) -> None:
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
    ) -> Finding:
        key = self.key(candidate, case, policies)
        cached = self._cache.get(key)
        if cached is not None:
            return cached
        return self._cache.put(key, self._judge.judge(candidate, case, policies))

    def key(
        self,
        candidate: Candidate,
        case: ArchitectureCase,
        policies: RetrievedPolicySet,
    ) -> str:
        material = repr(
            (
                candidate,
                case,
                policies.provenance.identity,
                self._model_identity(),
                self._prompt_identity(),
            )
        )
        return sha256(material.encode()).hexdigest()
