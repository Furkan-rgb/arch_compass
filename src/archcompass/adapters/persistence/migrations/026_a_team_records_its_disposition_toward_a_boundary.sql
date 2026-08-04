-- A team records its disposition toward a boundary, and argues about it in the open.
--
-- Everything stored so far is something ArchCompass produced: an atlas it built, a review it
-- reasoned out, a case someone wrote for it to reason against. These two tables are the first
-- record of what the *team* concluded, which is a different kind of fact and belongs in its
-- own place. A review stays immutable and untouched by this migration; nothing in the review
-- pipeline reads these tables, so a disposition can never quietly become a verdict.
--
-- Why the key is `(branch_id, boundary_fingerprint)`. A review id and a `BR-nnn` reference
-- are both minted per run — re-run the same repository and every one of them is different —
-- so neither can carry an opinion from one morning to the next. `branch_id` (024) is the
-- level a team actually holds an opinion at, and the fingerprint is what the boundary
-- structurally is, independent of the run that noticed it. The four verdict-context columns
-- record which run was on screen when the decision was taken, as provenance and as the
-- comparison that lets a later run say "this was decided against an earlier verdict". They
-- are never joined on.
--
-- Why both tables are append-only. A decision that changed by UPDATE would erase the fact
-- that it changed, and "who waived this, and had anyone accepted it before?" is the whole
-- question a reader brings here. Changing a mind appends a row; the latest `decided_at`,
-- tie-broken by rowid for two writes inside the same clock tick, is what stands. Same
-- discipline as `review_conversations`: no edits, no deletes.
--
-- Why the thread keys on the boundary rather than on a decision row. Argument comes before
-- judgement at least as often as after it, so a thread that could only hang off a decision
-- would have nowhere to put the discussion that produces one — and it would be orphaned, or
-- silently split, the moment the decision was superseded by the next row. The thread belongs
-- to the boundary; decisions come and go beneath it.
--
-- Why there is no row for "unreviewed". The absence of a decision is the fourth state, and it
-- is stored as absence. A row saying `unreviewed` would be a record that somebody decided not
-- to decide, and no interface could then tell it apart from a boundary nobody has looked at.
-- Silence means unreviewed, and the listing is a left join away from saying so.
--
-- Nothing existing is widened or rebuilt, so both statements are plain CREATE TABLE IF NOT
-- EXISTS and a replay against a database that already has them does nothing.

CREATE TABLE IF NOT EXISTS standing_decisions (
    decision_id TEXT PRIMARY KEY,
    -- Deliberately not a foreign key onto `branch_lineages`. A decision is checked against a
    -- known branch by the application, which can say so in words; a constraint here would
    -- turn the same mistake into an opaque integrity error at the write.
    branch_id TEXT NOT NULL,
    boundary_fingerprint TEXT NOT NULL,
    state TEXT NOT NULL,
    -- Self-reported, because there is no identity in the product yet. When there is, this
    -- column holds a validated value and no row has to move.
    author TEXT NOT NULL,
    -- NULL everywhere except a waiver, where the domain requires it: silencing a finding
    -- without stating why leaves nothing for the next reader to weigh.
    reason TEXT,
    decided_at TEXT NOT NULL,
    -- The verdict that was on screen. Provenance, and the comparison behind "decided against
    -- an earlier verdict — review again".
    review_id TEXT NOT NULL,
    boundary_reference TEXT NOT NULL,
    material INTEGER NOT NULL,
    verdict_label TEXT NOT NULL,
    decision_json TEXT NOT NULL,
    CHECK (state IN ('accepted', 'waived', 'parked')),
    CHECK (material IN (0, 1)),
    CHECK (state <> 'waived' OR (reason IS NOT NULL AND trim(reason) <> ''))
);

-- Every read of this table is "what does this branch currently think", per boundary or across
-- all of them.
CREATE INDEX IF NOT EXISTS standing_decisions_by_boundary
    ON standing_decisions(branch_id, boundary_fingerprint, decided_at DESC);

CREATE TABLE IF NOT EXISTS decision_comments (
    comment_id TEXT PRIMARY KEY,
    branch_id TEXT NOT NULL,
    boundary_fingerprint TEXT NOT NULL,
    -- Position in this boundary's thread. Timestamps are not an order: two remarks written in
    -- the same millisecond still came in some sequence, and the uniqueness below is what makes
    -- the sequence a fact rather than a hope.
    ordinal INTEGER NOT NULL,
    author TEXT NOT NULL,
    created_at TEXT NOT NULL,
    comment_json TEXT NOT NULL,
    CHECK (ordinal >= 1),
    -- Doubles as the index the thread is read through: reading a boundary's comments is a
    -- prefix lookup on the first two columns, already in ordinal order. A second index on the
    -- pair would be the same index written twice.
    UNIQUE (branch_id, boundary_fingerprint, ordinal)
);
