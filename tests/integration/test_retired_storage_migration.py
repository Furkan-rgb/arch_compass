"""Migration 033: the baseline's table goes, and a retired key leaves stored reviews.

Two removals in one file because they are one act. The baseline was retired in favour of the
delta rule and never wrote a row, so its table goes without a data question. `FailureDiagnostic`
is the other half: a consultation-era field the boundary review inherited and nothing on the
review path could ever fill. Domain models forbid extra keys (ADR 0002), so a stored document
that still carries it would stop loading the moment the field left the model — which is what
makes stripping it a migration rather than a tidy-up.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from archcompass.adapters.persistence.database import SQLiteDatabase
from archcompass.adapters.persistence.review_repository import (
    SQLiteBoundaryReviewRepository,
)
from archcompass.domain.errors import UnreadableStoredRecordError
from archcompass.domain.review import BoundaryReview, ReviewStatus

BURIAL = 33


def _era_review() -> BoundaryReview:
    """A failed review, which is the only status that ever carried a diagnostic."""

    return BoundaryReview(
        status=ReviewStatus.FAILED,
        case_id="case-1",
        case_revision=1,
        atlas_version_id="atlas-1",
        reasoning_model="model",
        prompt_identity="judge:v1",
    )


def _era_document(review: BoundaryReview) -> str:
    """The same review as the earlier schema wrote it: the current document plus the key."""

    document = json.loads(review.model_dump_json())
    document["failure_diagnostics"] = [
        {"code": "cluster_count_out_of_range", "force_handles": [], "count": 7}
    ]
    return json.dumps(document)


@pytest.fixture
def era_workspace(tmp_path: Path) -> tuple[SQLiteDatabase, BoundaryReview]:
    """A migrated workspace holding one review as the superseded schema wrote it.

    Written after migration and the version marker removed, rather than by stopping the
    migrations early: `initialize` applies every file it finds, and what is under test is
    what 033 does to a document, not how far the runner got.
    """

    database = SQLiteDatabase(tmp_path / "archcompass.db")
    database.initialize()
    review = _era_review()
    with database.connect() as connection:
        connection.execute(
            "INSERT INTO cases(case_id, current_revision, created_at, updated_at)"
            " VALUES ('case-1', 1, '2026-01-01T00:00:00+00:00', '2026-01-01T00:00:00+00:00')"
        )
        connection.execute(
            "INSERT INTO case_revisions(case_id, revision, event_type, actor, created_at,"
            " snapshot_json) VALUES ('case-1', 1, 'user_update', 'user',"
            " '2026-01-01T00:00:00+00:00', '{}')"
        )
        connection.execute(
            "INSERT INTO atlas_versions(version_id, repository_identity, root_path,"
            " git_commit_sha, content_fingerprint, parser_version, analysis_config_hash,"
            " created_at) VALUES ('atlas-1', 'repo', '/repo', NULL, 'fingerprint', '1', '1',"
            " '2026-01-01T00:00:00+00:00')"
        )
        connection.execute(
            "INSERT INTO boundary_reviews(review_id, case_id, case_revision,"
            " atlas_version_id, status, reasoning_model, boundaries_detected,"
            " boundaries_reviewed, boundaries_material, created_at, updated_at, case_title,"
            " review_json) VALUES (?, 'case-1', 1, 'atlas-1', 'failed', 'model', 0, 0, 0,"
            " '2026-01-01T00:00:00+00:00', '2026-01-01T00:00:00+00:00', 'Title', ?)",
            (review.review_id, _era_document(review)),
        )
        connection.execute(
            "DELETE FROM schema_migrations WHERE version = ?", (BURIAL,)
        )
        connection.commit()
    return database, review


def test_an_era_review_is_unreadable_until_the_migration_runs(
    era_workspace: tuple[SQLiteDatabase, BoundaryReview],
) -> None:
    """The failure the migration exists to prevent, asserted rather than assumed."""

    database, review = era_workspace

    with pytest.raises(UnreadableStoredRecordError) as failure:
        SQLiteBoundaryReviewRepository(database).get(review.review_id)

    assert "run the review again" in str(failure.value)


def test_the_migration_strips_the_key_and_leaves_the_rest_of_the_review(
    era_workspace: tuple[SQLiteDatabase, BoundaryReview],
) -> None:
    database, review = era_workspace

    database.initialize()

    stored = SQLiteBoundaryReviewRepository(database).get(review.review_id)
    assert stored == review
    with database.connect() as connection:
        document = json.loads(
            connection.execute(
                "SELECT review_json FROM boundary_reviews WHERE review_id = ?",
                (review.review_id,),
            ).fetchone()["review_json"]
        )
    # The key is gone from the row, not merely ignored on the way in: a model that forbids
    # extra keys cannot ignore one, so anything left here would be a review nobody can read.
    assert "failure_diagnostics" not in document
    # And nothing else moved, which a migration quietly rewriting content would not manage.
    assert document == json.loads(review.model_dump_json())


def test_migrating_twice_changes_nothing(
    era_workspace: tuple[SQLiteDatabase, BoundaryReview],
) -> None:
    """The guard keeps already-migrated rows out, so a replay is not a second rewrite."""

    database, review = era_workspace
    database.initialize()
    with database.connect() as connection:
        once = connection.execute(
            "SELECT review_json FROM boundary_reviews WHERE review_id = ?",
            (review.review_id,),
        ).fetchone()["review_json"]
        connection.execute("DELETE FROM schema_migrations WHERE version = ?", (BURIAL,))
        connection.commit()

    database.initialize()

    with database.connect() as connection:
        twice = connection.execute(
            "SELECT review_json FROM boundary_reviews WHERE review_id = ?",
            (review.review_id,),
        ).fetchone()["review_json"]
    assert twice == once


def test_a_fresh_workspace_has_no_baseline_table(tmp_path: Path) -> None:
    """027 creates it and 033 removes it, so the full chain must end without it."""

    path = tmp_path / "archcompass.db"
    SQLiteDatabase(path).initialize()

    with sqlite3.connect(path) as connection:
        tables = {
            str(row[0])
            for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
    assert "branch_baselines" not in tables


def test_a_workspace_that_holds_the_baseline_table_loses_it(tmp_path: Path) -> None:
    """The upgrade path: a database created while 027 was the end of the chain.

    The table is put back by hand and the version marker removed, which is the same shape as
    a workspace that stopped between 027 and 033. Nothing ever wrote a row into it in a real
    workspace — the service was never constructed — but one is written here anyway, so the
    drop is exercised against a table with data in it rather than an empty one.
    """

    path = tmp_path / "archcompass.db"
    database = SQLiteDatabase(path)
    database.initialize()
    with database.connect() as connection:
        connection.executescript(
            """
            CREATE TABLE branch_baselines (
                branch_id TEXT NOT NULL,
                boundary_fingerprint TEXT NOT NULL,
                material INTEGER NOT NULL,
                verdict_label TEXT NOT NULL,
                added_at TEXT NOT NULL,
                added_from_review TEXT NOT NULL,
                entry_json TEXT NOT NULL,
                PRIMARY KEY (branch_id, boundary_fingerprint)
            );
            INSERT INTO branch_baselines VALUES
                ('branch-1', 'fingerprint-1', 1, 'sound', '2026-01-01T00:00:00+00:00',
                 'review-1', '{}');
            """
        )
        connection.execute("DELETE FROM schema_migrations WHERE version = ?", (BURIAL,))
        connection.commit()

    database.initialize()

    with sqlite3.connect(path) as connection:
        tables = {
            str(row[0])
            for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
    assert "branch_baselines" not in tables
