-- A review keeps one sequence number for its whole life.
--
-- It used to take a new one every time it asked a question: the waiting snapshot was filed
-- as revision N, the answers advanced the lineage, and the review that came back with the
-- verdicts was filed as revision N+1. One review, two numbers on the rail, and a reader who
-- answered a question watched the revision they were reading turn into a different one.
--
-- So a sequence is no longer unique per branch. It is shared by every snapshot of one
-- review — each round it waited in, and the record it finished as — which the `round`
-- column tells apart. The row identity stays `review_id`, which is derived and now carries
-- the round, so two waiting snapshots of one review are two rows rather than one dropped as
-- a duplicate of the other.
--
-- The table is rebuilt rather than dropped: a review already recorded is still a true
-- record of what was judged, and the numbers it carries are still the numbers it was read
-- under. Only what a *new* review does with them changes. The `CREATE TABLE IF NOT EXISTS`
-- ahead of the rebuild is for a database that has never had a review in it — migrations run
-- before the repositories create their own tables, so there may be nothing here to rebuild.
--
-- The self-reference on the old primary key goes with it. A row that references itself is
-- not a constraint anything can fail.

CREATE TABLE IF NOT EXISTS core_review_snapshots (
    review_id TEXT PRIMARY KEY REFERENCES core_review_snapshots(review_id)
        ON DELETE CASCADE,
    repository_id TEXT NOT NULL,
    branch_id TEXT NOT NULL,
    sequence INTEGER NOT NULL,
    status TEXT NOT NULL,
    review_json TEXT NOT NULL,
    UNIQUE(repository_id, branch_id, sequence)
);

CREATE TABLE core_review_snapshots_rebuilt (
    review_id TEXT PRIMARY KEY,
    repository_id TEXT NOT NULL,
    branch_id TEXT NOT NULL,
    sequence INTEGER NOT NULL,
    round INTEGER NOT NULL DEFAULT 1,
    status TEXT NOT NULL,
    review_json TEXT NOT NULL
);

INSERT INTO core_review_snapshots_rebuilt(
    review_id, repository_id, branch_id, sequence, round, status, review_json
)
SELECT review_id, repository_id, branch_id, sequence, 1, status, review_json
FROM core_review_snapshots;

DROP TABLE core_review_snapshots;

ALTER TABLE core_review_snapshots_rebuilt RENAME TO core_review_snapshots;

CREATE INDEX IF NOT EXISTS core_review_snapshots_by_branch
    ON core_review_snapshots(branch_id, sequence DESC);
