-- A boundary keeps a line across revisions, and the line is written down.
--
-- Everything about a boundary that survives a run has keyed on `(branch_id,
-- boundary_fingerprint)`: the verdict cache, the standing decision, the discussion thread.
-- That works perfectly while the participants are untouched, which is most boundaries in
-- most revisions, and it breaks in exactly two ways. A participant is renamed, so the
-- fingerprint changes: the standing decision silently orphans and the boundary reads as
-- brand new, which is the worst outcome available — a decision was lost and nobody was
-- told. Or the boundary disappears entirely, and it simply stops appearing in runs, which
-- throws away the best news the tool can deliver: somebody fixed it.
--
-- This table is the record of both, and of the third thing that follows from them. A
-- succession says one fingerprint became another, so a standing carried across a rename can
-- be shown wearing the mark it was carried with rather than applied silently. A closure says
-- a line was addressed — reported loudly, never confirmed, because succession matching runs
-- first and nothing is deleted, so there is nothing to protect against. And a resurrection
-- says a closed fingerprint came back, which is what makes the closure safe to take
-- automatically: the standing and the thread were never removed, they key on the pair, and
-- they apply again the moment the pair reappears. The event is what lets the page say
-- "addressed in an earlier revision, back now" instead of presenting a boundary with history
-- as though nobody had ever seen it.
--
-- Append-only, like `standing_decisions` and `review_conversations` and for the same reason:
-- this is an account of something that happened, and an account that can be rewritten is not
-- evidence of anything. There is deliberately no `state` column and no row per boundary. The
-- state of a line is its latest event, derived on read; a stored state would be a second
-- answer to a question that has one, free to disagree with the history sitting beside it.
-- The correction for a premature closure is the resurrection event, not an UPDATE.
--
-- `review_id` is provenance and carries no foreign key and no deletion rule, exactly as the
-- review id on `verdict_cache` and `branch_baselines` does. What happened to a line stays
-- true whether or not the run that observed it is still stored, and cascading a delete here
-- would mean tidying a listing silently re-opens closures a team has already read.
--
-- `successor_fingerprint` is null on everything but a succession, where it is required: a
-- succession that cannot say what the boundary became records that something moved and
-- nothing about where, which is not worth storing.
--
-- Plain CREATE TABLE IF NOT EXISTS: nothing existing is widened, so the replay hazard that
-- made 013, 014, 018, 019 and 024 rebuild their tables does not apply, and re-running this
-- against a database that already has it is a no-op.

CREATE TABLE IF NOT EXISTS boundary_lines (
    event_id TEXT PRIMARY KEY,
    -- Deliberately not a foreign key onto `branch_lineages`, for the reason 026 gives: the
    -- application checks the branch and can say so in words, where a constraint would turn
    -- the same mistake into an opaque integrity error at the write.
    branch_id TEXT NOT NULL,
    boundary_fingerprint TEXT NOT NULL,
    event TEXT NOT NULL,
    review_id TEXT NOT NULL,
    successor_fingerprint TEXT,
    recorded_at TEXT NOT NULL,
    event_json TEXT NOT NULL,
    CHECK (event IN ('succeeded', 'addressed', 'resurfaced')),
    CHECK (event <> 'succeeded' OR successor_fingerprint IS NOT NULL),
    CHECK (event = 'succeeded' OR successor_fingerprint IS NULL)
);

-- Every read is "what has happened to this line", per boundary or for a set of them at the
-- start of a revision. Newest first, because the only question asked of the whole history is
-- what the latest event was.
CREATE INDEX IF NOT EXISTS boundary_lines_by_boundary
    ON boundary_lines(branch_id, boundary_fingerprint, recorded_at DESC, event_id DESC);
