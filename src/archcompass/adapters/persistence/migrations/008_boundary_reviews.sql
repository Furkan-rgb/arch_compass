-- Boundary reviews: the advisory path that judges detected boundaries against a case.
--
-- Separate from consultation_runs rather than sharing it. A review produces a different
-- artifact and pins a different set of inputs, and storing both shapes in one table would
-- mean every column that applies to only one of them becomes nullable, which stops the
-- schema saying anything about either.
--
-- The report itself lives in review_json alongside the rest of the aggregate, matching how
-- consultation_runs stores run_json: the columns exist to be queried and joined against,
-- not to duplicate the document.

CREATE TABLE IF NOT EXISTS boundary_reviews (
    review_id TEXT PRIMARY KEY,
    case_id TEXT NOT NULL,
    case_revision INTEGER NOT NULL,
    atlas_version_id TEXT NOT NULL,
    status TEXT NOT NULL,
    reasoning_model TEXT NOT NULL,
    boundaries_reviewed INTEGER NOT NULL,
    boundaries_material INTEGER NOT NULL,
    created_at TEXT NOT NULL,
    review_json TEXT NOT NULL,
    CHECK (case_revision >= 1),
    CHECK (status IN ('succeeded', 'failed')),
    CHECK (boundaries_reviewed >= 0),
    CHECK (boundaries_material >= 0),
    CHECK (boundaries_material <= boundaries_reviewed),
    FOREIGN KEY (case_id, case_revision)
        REFERENCES case_revisions(case_id, revision),
    FOREIGN KEY (atlas_version_id) REFERENCES atlas_versions(version_id)
);

CREATE INDEX IF NOT EXISTS boundary_reviews_by_case
    ON boundary_reviews(case_id, created_at DESC);
