-- A branch remembers which boundaries it has already seen.
--
-- A team adopting this on a repository that has been alive for years gets a first run with
-- dozens or hundreds of boundaries, and every one of them is news. If the second run
-- presents the same list again, nobody reads the second run — a check that says the same
-- thing every time is indistinguishable from a check that says nothing, and it is the
-- second run where the value was supposed to be. This table is what makes run two quieter
-- than run one (docs/plans/company-readiness.md §3): the boundaries a branch has declared
-- itself to have looked at, so a later run can lead with the ones it has not.
--
-- One row per `(branch_id, boundary_fingerprint)`, written with INSERT OR REPLACE, and that
-- is the difference between this table and everything else stored here. A review is
-- immutable and a discussion is append-only because both are accounts of something that
-- happened, and rewriting an account is falsifying it. "This branch has seen this boundary"
-- is not an account of anything — it is a claim about now — so re-baselining a branch
-- updates the row rather than laying a second one beside it. Nothing is lost: what the
-- boundary was judged as at the time is in the review that judged it, and the verdict
-- itself is in `verdict_cache`. A history of when a boundary was re-baselined would be a
-- log nobody has a question for.
--
-- The key is the branch and the *fingerprint*, never a review reference. `BR-003` is
-- assigned per run and a candidate id is minted per detection; neither survives to the run
-- that would consult this. `branch_id` rather than `repo_id` because a branch is where a
-- team holds an opinion, and a PR branch that inherited a noisy legacy baseline from `main`
-- should be able to move on from it without editing what `main` claims.
--
-- `material` and `verdict_label` are copied onto the row instead of being read back from
-- the origin review. Partly cost — comparing forty boundaries would otherwise open forty
-- reviews to answer a question about a boolean — and mostly durability: the origin review
-- can be deleted, and what the boundary was accepted as is exactly the fact that must not
-- go with it. Comparison uses `material` alone; `verdict_label` is there so a reader can be
-- told what they accepted, and is not a condition on anything (see `domain/baseline.py`).
--
-- `added_from_review` is provenance and, like the review id on `verdict_cache`, carries no
-- foreign key and no deletion rule. An entry stays true about the structure it names
-- whether or not the run that first presented it is still stored, and cascading a delete
-- here would mean tidying a listing silently re-opens a hundred boundaries a team had
-- already worked through.
--
-- Nothing removes rows implicitly. A baseline shrinks when someone says so — that is the
-- ratchet, and it is why removal is an explicit action with its own endpoint rather than a
-- side effect of a run. A boundary that has genuinely vanished from the repository simply
-- stops being matched; its row costs a few dozen bytes and lying about what a branch once
-- accepted would cost more.
--
-- Plain CREATE TABLE IF NOT EXISTS rather than a rebuild: nothing here widens an existing
-- table, so the replay hazard that made 013, 014, 018, 019 and 024 rebuild does not apply.
-- Re-running this file against a database that has it is a no-op.

CREATE TABLE IF NOT EXISTS branch_baselines (
    branch_id TEXT NOT NULL,
    boundary_fingerprint TEXT NOT NULL,
    material INTEGER NOT NULL,
    verdict_label TEXT NOT NULL,
    added_at TEXT NOT NULL,
    added_from_review TEXT NOT NULL,
    entry_json TEXT NOT NULL,
    -- The pair is the identity, so a second baselining of the same branch cannot leave two
    -- disagreeing claims about one boundary standing side by side.
    PRIMARY KEY (branch_id, boundary_fingerprint)
);
