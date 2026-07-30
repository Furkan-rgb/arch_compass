-- A first pass judges every boundary against whatever the case says — usually nothing —
-- and then asks for what would settle the verdicts it could not settle alone. Until now
-- that run was stored as `succeeded`, so a review whose questions nobody had answered read
-- as finished in every listing, for ever. It is not finished: measured on the bundled
-- `warehouse-sync` example, four of five first-pass verdicts moved once the questions were
-- answered, so those verdicts are not findings and the record must not imply they are.
--
-- `awaiting_answers` is therefore a fifth status rather than a flavour of `succeeded`, on
-- the same reasoning that made `cancelled` its own status in 014: it is a different outcome,
-- and a listing that showed the two alike would have a reader acting on provisional verdicts.
-- It is terminal. Nobody is obliged to answer, and answering does not move this row — it
-- produces a second review pinned to the case revision the answers created.
--
-- `elicited_from` is that link, stored rather than inferred. "Has this review been carried
-- on from?" was previously read off the listing, where any newer review of the same case
-- counted, and that is wrong in a way a user meets: revising the case by hand also produces
-- a newer review and would silently mark the questions answered. As a column it also lets a
-- listing pair the two passes without decoding either document.
--
-- Rebuilt for the reason 013 and 014 were — SQLite cannot widen a CHECK in place — and by
-- the same recipe, with `review_conversations` created against the new table first because
-- it holds the only foreign key in.
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
    -- Nullable, and null is the ordinary value: a first pass came from nothing. Self-reference
    -- rather than a second table, because a second pass names exactly one predecessor.
    elicited_from TEXT,
    review_json TEXT NOT NULL,
    CHECK (case_revision >= 1),
    CHECK (status IN (
        'running', 'awaiting_answers', 'succeeded', 'failed', 'cancelled'
    )),
    CHECK (boundaries_detected IS NULL OR boundaries_detected >= 0),
    CHECK (boundaries_reviewed >= 0),
    CHECK (boundaries_material >= 0),
    CHECK (boundaries_material <= boundaries_reviewed),
    CHECK (elicited_from IS NULL OR elicited_from <> review_id),
    FOREIGN KEY (case_id, case_revision)
        REFERENCES case_revisions(case_id, revision),
    FOREIGN KEY (atlas_version_id) REFERENCES atlas_versions(version_id),
    -- Deleting a first pass leaves its second pass standing, with the link cleared. The
    -- second pass is a complete review in its own right — its own case revision, its own
    -- verdicts, its own conclusion — and refusing the delete, or cascading it, would both
    -- destroy a finished review to tidy up the question that led to it.
    FOREIGN KEY (elicited_from)
        REFERENCES boundary_reviews_next(review_id) ON DELETE SET NULL
);

INSERT INTO boundary_reviews_next (
    review_id, case_id, case_revision, atlas_version_id, status, reasoning_model,
    boundaries_detected, boundaries_reviewed, boundaries_material, created_at,
    updated_at, case_title, elicited_from, review_json
)
SELECT
    review_id, case_id, case_revision, atlas_version_id, status, reasoning_model,
    boundaries_detected, boundaries_reviewed, boundaries_material, created_at,
    updated_at, case_title, NULL, review_json
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

-- The second pass is looked up from the first — "has this been carried on from?" is the
-- question the waiting page asks on every load — so the link is indexed in that direction.
CREATE INDEX boundary_reviews_by_elicited_from
    ON boundary_reviews(elicited_from);
