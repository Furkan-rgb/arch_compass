-- Bury the baseline, and take the last consultation-era key off a stored review with it.
--
-- The baseline was the mechanism that made run two quieter than run one: a team declared
-- the boundaries it had already looked at, and later runs led with what was not on the
-- list. architecture.md decision 4 retired the concept in favour of the delta rule — a
-- revision judges what moved since the branch's previous revision, and a boundary is quiet
-- because nothing about it changed rather than because somebody declared it seen. The
-- standings then took over the half the baseline was actually reached for: a boundary is
-- quiet for a reason with an author and a sentence behind it.
--
-- Nothing ever wrote to this table. `BaselineService` existed but was never constructed,
-- its endpoints left the web surface with the delta restructure, and the table was created
-- by 027 into a path that was retired before it carried a row. So there is no data question
-- here and no export to offer: dropped rather than kept, because a table nothing reads is
-- an invitation to wonder what it was for (migrations 017 and 020 on the same grounds).
--
-- `IF EXISTS` because a workspace created after this never had it. No foreign key pointed
-- at it — 027 deliberately gave it none, and 029 says why the review id on it was
-- provenance rather than a reference — so `foreign_key_check` has nothing to complain
-- about on the way out.

DROP TABLE IF EXISTS branch_baselines;

-- `failure_diagnostics` was the structured detail of a consultation clustering failure, and
-- the boundary review inherited the field without ever inheriting anything that could fill
-- it: no stage on the review path raises the error that produced one. The field is gone
-- from the domain, and because domain models forbid extra keys (ADR 0002 — the current
-- schema is the only one that reads), a stored document that still carries the key would
-- stop loading. It is removed here rather than tolerated by a shim.
--
-- Only the reviews that actually hold the key are rewritten, so a workspace whose reviews
-- were all written after the field left is untouched, and re-running this file changes
-- nothing.
UPDATE boundary_reviews
SET review_json = json_remove(review_json, '$.failure_diagnostics')
WHERE json_extract(review_json, '$.failure_diagnostics') IS NOT NULL;
