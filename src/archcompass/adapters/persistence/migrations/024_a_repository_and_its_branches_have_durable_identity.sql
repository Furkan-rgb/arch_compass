-- A repository and its branches have an identity that outlives the directory they are in.
--
-- Everything stored so far identifies a repository by where it is: `repository_identity` is
-- the hash of the canonical path. That is a true fact about a checkout and the wrong key for
-- anything that has to survive one. Two clones of the same repository are two strangers
-- under it; moving a clone makes it a new repository; and CI, which checks out somewhere
-- else every time, would share nothing with the workspace it is meant to be reporting on.
--
-- So a second identity is added beside it rather than replacing it. `repo_id` is derived
-- from the sha of the root commit — the one identifier every clone of a history shares and
-- nothing an ordinary workflow rewrites — falling back to the canonical path for a directory
-- that is not a git repository at all, which has nothing else to be identified by. Not the
-- remote URL: remotes are renamed, a repository can have several, and a checkout can have
-- none. `branch_id` is `(repo_id, branch_name)`, because a branch is where a team holds an
-- opinion — "on main, this boundary is accepted" — and the baselines and standing decisions
-- that come next attach there rather than to any single run.
--
-- The four columns added to `atlas_versions` and the two added to `boundary_reviews` are
-- nullable, and that is not laziness about defaults. A migration is pure SQL, and both ids
-- are hashes of facts that have to be read out of git; nothing here can compute them.
-- Existing rows therefore stay NULL and are filled lazily: the next analysis of a repository
-- writes a stamped atlas row, and the next review of a stamped atlas carries the same pair
-- onto its own row. Nothing reads a NULL as a claim — an unstamped row is a row that
-- predates lineages, which is exactly what it looks like.
--
-- `root_commit_sha` and `branch_name` are kept on the atlas version as well, because they
-- are what the ids were derived from. A hash nobody can explain is a hash nobody will trust
-- the day two runs disagree about which repository they were looking at.
--
-- Both tables are rebuilt rather than widened with `ALTER TABLE ... ADD COLUMN`, for the
-- reason 013, 014, 018 and 019 rebuild: a migration at or above a retired version number is
-- replayed against a workspace that has already applied it, and a bare ADD COLUMN fails
-- there with `duplicate column name`. A rebuild is idempotent, which is what the replay
-- needs. A replay does re-copy the old columns and leave the new ones NULL — the same trade
-- 018 made with `elicited_from` — and here it costs nothing that is not immediately
-- recoverable, because a lineage id is derived and the next analysis writes it back.

CREATE TABLE IF NOT EXISTS repository_lineages (
    repo_id TEXT PRIMARY KEY,
    -- NULL for a directory outside git, where the path fallback was used. Its absence is the
    -- record that this identity is only as durable as the path it came from.
    root_commit_sha TEXT,
    -- Where it was first seen, kept for a reader rather than as part of the identity: a
    -- clone elsewhere keeps the same `repo_id`, and this column goes on naming the first path.
    canonical_root TEXT NOT NULL,
    first_seen_at TEXT NOT NULL,
    lineage_json TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS branch_lineages (
    branch_id TEXT PRIMARY KEY,
    repo_id TEXT NOT NULL REFERENCES repository_lineages(repo_id),
    branch_name TEXT NOT NULL,
    first_seen_at TEXT NOT NULL,
    lineage_json TEXT NOT NULL,
    -- The derivation says the same thing, and saying it twice is the point: `branch_id` is a
    -- hash, and a hash cannot be read by a human checking that one branch has one lineage.
    UNIQUE (repo_id, branch_name)
);

CREATE INDEX IF NOT EXISTS branch_lineages_by_repository
    ON branch_lineages(repo_id);

CREATE TABLE atlas_versions_next (
    version_id TEXT PRIMARY KEY,
    -- Unchanged and staying: where this checkout is, which is a question a workspace on one
    -- machine still asks. What it stops being is the identity of the repository.
    repository_identity TEXT NOT NULL,
    root_path TEXT NOT NULL,
    git_commit_sha TEXT,
    content_fingerprint TEXT NOT NULL,
    parser_version TEXT NOT NULL,
    analysis_config_hash TEXT NOT NULL,
    created_at TEXT NOT NULL,
    -- What git said when this atlas was built, and what was derived from it. Kept together
    -- so a `repo_id` can be explained by the row carrying it.
    root_commit_sha TEXT,
    branch_name TEXT,
    repo_id TEXT,
    branch_id TEXT
);

INSERT INTO atlas_versions_next (
    version_id, repository_identity, root_path, git_commit_sha, content_fingerprint,
    parser_version, analysis_config_hash, created_at, root_commit_sha, branch_name,
    repo_id, branch_id
)
SELECT
    version_id, repository_identity, root_path, git_commit_sha, content_fingerprint,
    parser_version, analysis_config_hash, created_at, NULL, NULL, NULL, NULL
FROM atlas_versions;

DROP TABLE atlas_versions;

ALTER TABLE atlas_versions_next RENAME TO atlas_versions;

CREATE INDEX atlas_versions_root_created
    ON atlas_versions(root_path, created_at DESC);

CREATE INDEX atlas_versions_created
    ON atlas_versions(created_at DESC);

-- "Which runs happened on this branch" is the question the baseline and the verdict cache
-- ask constantly, of both tables.
CREATE INDEX atlas_versions_by_branch
    ON atlas_versions(branch_id);

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
    -- Copied from the atlas this run judged rather than resolved again, so a run can never
    -- claim a different branch than the evidence it was drawn from.
    repo_id TEXT,
    branch_id TEXT,
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
    updated_at, case_title, elicited_from, repo_id, branch_id, review_json
)
SELECT
    review_id, case_id, case_revision, atlas_version_id, status, reasoning_model,
    boundaries_detected, boundaries_reviewed, boundaries_material, created_at,
    updated_at, case_title, elicited_from, NULL, NULL, review_json
FROM boundary_reviews;

DROP TABLE boundary_reviews;

ALTER TABLE boundary_reviews_next RENAME TO boundary_reviews;

CREATE INDEX boundary_reviews_by_case
    ON boundary_reviews(case_id, created_at DESC);

CREATE INDEX boundary_reviews_by_elicited_from
    ON boundary_reviews(elicited_from);

CREATE INDEX boundary_reviews_by_branch
    ON boundary_reviews(branch_id);
