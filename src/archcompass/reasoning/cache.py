"""Strategy-neutral verdict reuse around one ArchitectureJudge capability call."""

from __future__ import annotations

from collections.abc import Callable, Sequence
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
    BatchArchitectureJudge,
    BatchOutcome,
    JudgementRequest,
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

    def supports_batch(self) -> bool:
        return isinstance(self._judge, BatchArchitectureJudge) and (
            self._judge.supports_batch()
        )

    def judge_all(
        self,
        requests: Sequence[JudgementRequest],
        *,
        observe: Callable[[BatchOutcome], None] | None = None,
    ) -> tuple[Finding, ...]:
        """Cache first, then submit only what is left.

        A re-judgement round re-asks about every selected candidate, and most of them have
        not moved — so submitting the cached ones would pay for verdicts already held. The
        answers are stitched back into the caller's order, because a review is composed
        against the candidate list and not against whatever the batch happened to return.
        """

        keys = [self.key(item.candidate, item.case, item.policies) for item in requests]
        found: dict[int, Finding] = {}
        missing: list[int] = []
        for index, key in enumerate(keys):
            cached = self._cache.get(key)
            if cached is None:
                missing.append(index)
            else:
                found[index] = cached

        if missing:
            if not isinstance(self._judge, BatchArchitectureJudge):
                raise TypeError("the wrapped judge cannot judge a batch")
            judged = self._judge.judge_all(
                [requests[index] for index in missing], observe=observe
            )
            if len(judged) != len(missing):
                raise ValueError(
                    f"the judge answered {len(judged)} of {len(missing)} submitted "
                    "judgements"
                )
            for index, finding in zip(missing, judged, strict=True):
                found[index] = self._cache.put(keys[index], finding)

        return tuple(found[index] for index in range(len(requests)))

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
