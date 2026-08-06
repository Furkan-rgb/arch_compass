-- A verdict is not recomputed for a question that has not changed.
--
-- Judging is one model call per boundary and a review is minutes long, almost all of it
-- spent asking again about boundaries nobody touched. That is the cost objection, and it is
-- the smaller half. The larger half is trust: two runs over identical inputs can return two
-- different verdicts, and a check that flips its mind about untouched code is a check a team
-- stops reading. Storing the answer makes stability structural rather than statistical —
-- an unchanged boundary cannot flip, because nothing asks again.
--
-- `cache_key` is the whole question rather than the boundary: a hash over the boundary
-- fingerprint, the policy corpus, the case and its revision, and the model and prompt
-- identities. Every one of those changes what the right answer is, so every one of them is
-- in the key, and a change to any of them is simply a miss. The derivation and the reasoning
-- for each component live in `domain/verdict_cache.py`; this table stores the result.
--
-- `boundary_fingerprint` is stored beside the key even though the key already covers it. A
-- hash cannot be taken apart, and the next two features — a branch-level baseline of known
-- fingerprints, and standing decisions attached to one — need to ask what a given boundary
-- has been judged as, which is a question no full-key lookup can answer. The index is for
-- that reader, not for the write path.
--
-- `review_id` is provenance, deliberately with no foreign key to `boundary_reviews` and
-- deliberately with no deletion rule. It records which run first reached this verdict, so a
-- reused verdict can be attributed instead of quietly appearing as if it were fresh. It is
-- never consulted to decide whether the row still applies, because a verdict is true about
-- the structure it judged, and deleting the run that happened to produce it does not make
-- the answer wrong. Dropping cached verdicts when their origin review is deleted would mean
-- tidying up a listing silently re-imposes a full, paid re-run — a surprising bill for a
-- housekeeping action. The attribution goes stale on such a delete, which is the honest
-- cost of the choice and is why the id is stored rather than joined: a dangling review id
-- reads as a run that no longer exists, and nothing here pretends otherwise.
--
-- `verdict_json` is the verdict whole, not a summary of it. Reuse means the reader gets the
-- same words, the same rationale and the same policy bearings as the run that reached them;
-- anything less would be a paraphrase presented as a finding.
--
-- Plain CREATE TABLE IF NOT EXISTS rather than a rebuild: nothing here widens an existing
-- table, so the replay hazard that made 013, 014, 018, 019 and 024 rebuild does not apply.
-- Re-running this file against a database that has it is a no-op.

CREATE TABLE IF NOT EXISTS verdict_cache (
    cache_key TEXT PRIMARY KEY,
    boundary_fingerprint TEXT NOT NULL,
    review_id TEXT NOT NULL,
    created_at TEXT NOT NULL,
    verdict_json TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS verdict_cache_by_boundary
    ON verdict_cache(boundary_fingerprint);
