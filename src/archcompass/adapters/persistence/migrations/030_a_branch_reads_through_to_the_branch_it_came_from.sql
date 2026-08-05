-- A branch says which branch it came from, so it can read what that branch already settled.
--
-- Everything durable keys on `branch_id`: the standing decisions, the line of revisions, and
-- now the case. That is right — a branch is where a team holds an opinion — and taken alone it
-- makes a pull request the loudest thing the tool produces. A fresh feature branch has decided
-- nothing, so every boundary in a repository that `main` worked through years ago is undecided
-- again, and CI blocks the pull request on history the team settled long before the branch
-- existed. The isolation that makes a branch's own delta legible is exactly what makes its
-- standings useless on the day it is created.
--
-- So a branch names its base, and reads through to it: its own record always wins, and where
-- it has none the base's applies. A branch diverges by deciding differently rather than by
-- starting empty, which is what "this branch changed these boundaries" is supposed to mean.
--
-- Nullable, and NULL on every existing row, because nothing here can compute it. A migration
-- is pure SQL and the default base is the repository's default branch — which is a lineage
-- that may not have been indexed in this workspace yet, and which is derived from a name this
-- file has no way to hash. So the column is filled lazily in application code, when a branch
-- lineage is written for a branch that is not the default one and the default one's lineage
-- exists; a branch whose base is unknown reads only its own standings, which is what it did
-- before this column existed. NULL is therefore a true statement — "nothing is known to be
-- behind this branch" — rather than a value waiting to be backfilled.
--
-- Deliberately not a foreign key onto `branch_lineages` itself, for the reason 026 and 029
-- give about the same table: the application resolves the chain and can say in words that a
-- base has gone, where a constraint would turn a deleted lineage into an opaque integrity
-- error at the next index. It is also what keeps the read bounded and cycle-safe in one place
-- — the walk itself — rather than trusting the schema to have prevented a cycle it cannot see
-- across two separate writes.
--
-- The table is rebuilt rather than widened with `ALTER TABLE ... ADD COLUMN`, for the reason
-- 013, 014, 018, 019 and 024 rebuild: a migration at or above a retired version number is
-- replayed against a workspace that has already applied it, and a bare ADD COLUMN fails there
-- with `duplicate column name`. A rebuild is idempotent, which is what the replay needs.
-- 028 could add its column plainly only because 024 rebuilds the table it widens, so a replay
-- reaches it with the column already gone again; nothing rebuilds `branch_lineages`, so this
-- one has to do it itself. A replay re-copies the old columns and leaves the new one NULL,
-- which costs nothing that is not immediately recoverable: the base is derived, and the next
-- index of the branch writes it back.

CREATE TABLE branch_lineages_next (
    branch_id TEXT PRIMARY KEY,
    repo_id TEXT NOT NULL REFERENCES repository_lineages(repo_id),
    branch_name TEXT NOT NULL,
    -- What this branch reads through to where it has no record of its own.
    base_branch_id TEXT,
    first_seen_at TEXT NOT NULL,
    lineage_json TEXT NOT NULL,
    -- The derivation says the same thing, and saying it twice is the point: `branch_id` is a
    -- hash, and a hash cannot be read by a human checking that one branch has one lineage.
    UNIQUE (repo_id, branch_name)
);

INSERT INTO branch_lineages_next (
    branch_id, repo_id, branch_name, base_branch_id, first_seen_at, lineage_json
)
SELECT
    branch_id, repo_id, branch_name, NULL, first_seen_at, lineage_json
FROM branch_lineages;

DROP TABLE branch_lineages;

ALTER TABLE branch_lineages_next RENAME TO branch_lineages;

CREATE INDEX IF NOT EXISTS branch_lineages_by_repository
    ON branch_lineages(repo_id);
