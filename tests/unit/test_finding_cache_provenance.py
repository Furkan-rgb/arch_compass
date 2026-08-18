from __future__ import annotations

import sqlite3
from pathlib import Path

from archcompass.adapters.persistence.core_finding_cache import SQLiteCoreFindingCache
from archcompass.adapters.persistence.core_review_repository import SQLiteCoreReviewRepository
from archcompass.application.verdict_cache import CachingReviewRecorder
from archcompass.domain.core import (
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
from archcompass.domain.core._support import utc_now


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
    case = ArchitectureCase.create("Keep changes local")
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
