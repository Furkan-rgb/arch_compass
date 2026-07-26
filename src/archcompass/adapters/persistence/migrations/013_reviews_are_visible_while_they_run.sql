-- A review took minutes and existed nowhere until it was over: nothing to open, nothing to
-- come back to, and no way to tell a run in progress from one that never started. The row
-- is now written when the run begins and finished when it ends, so `status` admits
-- `running` and the counts can move while it does.
--
-- Rebuilt rather than altered: SQLite cannot widen a CHECK constraint in place.
-- `review_conversations` is rebuilt with it because it holds the only foreign key into
-- this table — dropping a parent with live children fails outright — and is created
-- against the new table first so nothing is ever left pointing at a table about to go.
-- Renaming afterwards rewrites the reference back to the original name.
CREATE TABLE boundary_reviews_next (
    review_id TEXT PRIMARY KEY,
    case_id TEXT NOT NULL,
    case_revision INTEGER NOT NULL,
    atlas_version_id TEXT NOT NULL,
    status TEXT NOT NULL,
    reasoning_model TEXT NOT NULL,
    -- Null until the sweep finishes: before it, how many boundaries there are is genuinely
    -- unknown, and a zero there would read as "none found".
    boundaries_detected INTEGER,
    boundaries_reviewed INTEGER NOT NULL,
    boundaries_material INTEGER NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    case_title TEXT,
    review_json TEXT NOT NULL,
    CHECK (case_revision >= 1),
    CHECK (status IN ('running', 'succeeded', 'failed')),
    CHECK (boundaries_detected IS NULL OR boundaries_detected >= 0),
    CHECK (boundaries_reviewed >= 0),
    CHECK (boundaries_material >= 0),
    CHECK (boundaries_material <= boundaries_reviewed),
    FOREIGN KEY (case_id, case_revision)
        REFERENCES case_revisions(case_id, revision),
    FOREIGN KEY (atlas_version_id) REFERENCES atlas_versions(version_id)
);

-- Every stored review is finished, so what it detected is what it reviewed, and it last
-- moved when it was created.
INSERT INTO boundary_reviews_next
SELECT review_id, case_id, case_revision, atlas_version_id, status, reasoning_model,
       boundaries_reviewed, boundaries_reviewed, boundaries_material,
       created_at, created_at, case_title, review_json
FROM boundary_reviews;

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
    FOREIGN KEY (review_id) REFERENCES boundary_reviews_next(review_id),
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
