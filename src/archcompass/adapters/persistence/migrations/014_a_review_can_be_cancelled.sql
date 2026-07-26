-- A review is minutes of model calls, and until now the only way to stop one was to stop
-- the workspace. Cancelling is a fourth status rather than a flavour of `failed`: a review
-- nobody wanted any more is not a review that broke, and a listing showing them the same
-- way would have the reader looking for a problem that never existed.
--
-- Rebuilt for the same reason 013 was — SQLite cannot widen a CHECK in place — and by the
-- same recipe, with `review_conversations` created against the new table first because it
-- holds the only foreign key in.
CREATE TABLE boundary_reviews_next (
    review_id TEXT PRIMARY KEY,
    case_id TEXT NOT NULL,
    case_revision INTEGER NOT NULL,
    atlas_version_id TEXT NOT NULL,
    status TEXT NOT NULL,
    reasoning_model TEXT NOT NULL,
    boundaries_detected INTEGER,
    boundaries_reviewed INTEGER NOT NULL,
    boundaries_material INTEGER NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    case_title TEXT,
    review_json TEXT NOT NULL,
    CHECK (case_revision >= 1),
    CHECK (status IN ('running', 'succeeded', 'failed', 'cancelled')),
    CHECK (boundaries_detected IS NULL OR boundaries_detected >= 0),
    CHECK (boundaries_reviewed >= 0),
    CHECK (boundaries_material >= 0),
    CHECK (boundaries_material <= boundaries_reviewed),
    FOREIGN KEY (case_id, case_revision)
        REFERENCES case_revisions(case_id, revision),
    FOREIGN KEY (atlas_version_id) REFERENCES atlas_versions(version_id)
);

INSERT INTO boundary_reviews_next SELECT * FROM boundary_reviews;

CREATE TABLE review_conversations_next (
    conversation_id TEXT PRIMARY KEY,
    review_id TEXT NOT NULL,
    case_id TEXT NOT NULL,
    case_revision INTEGER NOT NULL,
    title TEXT NOT NULL,
    message_count INTEGER NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    conversation_json TEXT NOT NULL,
    CHECK (case_revision >= 1),
    CHECK (message_count >= 0),
    -- Deleting a review takes its questions with it: a thread whose review is gone has
    -- nothing to be about, and every answer in it cited boundaries that no longer exist.
    FOREIGN KEY (review_id)
        REFERENCES boundary_reviews_next(review_id) ON DELETE CASCADE,
    FOREIGN KEY (case_id, case_revision)
        REFERENCES case_revisions(case_id, revision)
);

INSERT INTO review_conversations_next SELECT * FROM review_conversations;

DROP TABLE review_conversations;

DROP TABLE boundary_reviews;

ALTER TABLE boundary_reviews_next RENAME TO boundary_reviews;

ALTER TABLE review_conversations_next RENAME TO review_conversations;

CREATE INDEX boundary_reviews_by_case
    ON boundary_reviews(case_id, created_at DESC);

CREATE INDEX review_conversations_by_review
    ON review_conversations(review_id, created_at DESC);
