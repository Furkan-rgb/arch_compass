from __future__ import annotations

import sqlite3
from dataclasses import replace
from pathlib import Path

from archcompass.domain import (
    ArchitectureCase,
    Candidate,
    Finding,
    Participant,
    RepositoryAtlas,
    RepositoryRef,
    Review,
    ReviewDelta,
    ReviewStatus,
    Verdict,
)
from archcompass.domain._support import utc_now
from archcompass.persistence.findings import SQLiteCoreFindingCache
from archcompass.persistence.reviews import SQLiteCoreReviewRepository
from archcompass.reasoning.cache import CachingReviewRecorder


def test_cache_hit_names_the_review_that_first_recorded_the_finding(
    tmp_path: Path,
) -> None:
    database = tmp_path / "cache.db"

    def connect() -> sqlite3.Connection:
        return sqlite3.connect(database)

    cache = SQLiteCoreFindingCache(connect)
    reviews = SQLiteCoreReviewRepository(connect)
    recorder = CachingReviewRecorder(reviews, cache)
    repository = RepositoryRef("repo", tmp_path, "branch", "content")
    atlas = RepositoryAtlas("atlas", repository)
    case = ArchitectureCase.create()
    candidate = Candidate.identified(
        pattern="sole_implementation",
        summary="Port has one implementation",
        participants=(Participant("Port", "interface"),),
    )
    finding = Finding(candidate, Verdict.CLEARED, "No conflict.", (), ())
    now = utc_now()
    review = Review(
        "review-source",
        1,
        repository,
        atlas,
        case,
        (finding,),
        (),
        ReviewStatus.COMPLETED,
        ReviewDelta(new=(candidate,)),
        now,
        now,
    )

    cache.put("key", finding)
    recorder.record(review)

    reused = cache.get("key")
    assert reused is not None
    assert reused.reused_from_review_id == review.id


def test_a_review_attaches_itself_to_a_finding_it_revised_after_caching_it(
    tmp_path: Path,
) -> None:
    """A settled hinge is the same judgement, so the cached row is still its source.

    The join used to be the finding's whole encoded document, which held only while
    nothing revised a finding between caching it and recording it. A second pass that
    settles a hinge does exactly that, and the row it no longer matched was the row
    holding the provenance every later reuse reads.
    """

    database = tmp_path / "cache.db"

    def connect() -> sqlite3.Connection:
        return sqlite3.connect(database)

    cache = SQLiteCoreFindingCache(connect)
    reviews = SQLiteCoreReviewRepository(connect)
    recorder = CachingReviewRecorder(reviews, cache)
    repository = RepositoryRef("repo", tmp_path, "branch", "content")
    atlas = RepositoryAtlas("atlas", repository)
    case = ArchitectureCase.create()
    candidate = Candidate.identified(
        pattern="sole_implementation",
        summary="Port has one implementation",
        participants=(Participant("Port", "interface"),),
    )
    judged = Finding(
        candidate,
        Verdict.HELD,
        "Held pending intent.",
        (),
        (),
        hinge="whether the seam is deliberate",
    )
    settled = replace(
        judged,
        verdict=Verdict.CLEARED,
        reasoning="The repository shows one implementation and no second caller.",
        hinge=None,
        investigation_identity="investigation-1",
    )
    now = utc_now()
    review = Review(
        "review-source",
        1,
        repository,
        atlas,
        case,
        (settled,),
        (),
        ReviewStatus.COMPLETED,
        ReviewDelta(new=(candidate,)),
        now,
        now,
    )

    cache.put("key", judged)
    recorder.record(review)

    reused = cache.get("key")
    assert reused is not None
    assert reused.reused_from_review_id == review.id
