-- A candidate now carries its measurements as records rather than as name/value pairs, and
-- carries the relationships between its participants. Every review and cached finding
-- written before that holds the old shape, and ArchCompass does not guess at the meaning of
-- a record an earlier schema wrote: a stored review whose measurements are two-element
-- lists cannot be reinterpreted as measurements that state their own nature and limits.
--
-- All of this is derived output — it is produced again by running the review. What is
-- authored rather than derived stays: `core_case_snapshots` holds intent a person wrote,
-- and `core_standing_decisions` holds a team's disposition toward a boundary, keyed by a
-- candidate id whose derivation did not change, so those dispositions still land on the
-- boundaries they were made about.
--
-- The executions and their aliases go with the reviews they point at. That is also what
-- retires the LangGraph checkpoints in `review-checkpoints.db`: a checkpoint is reachable
-- only through the thread id an execution holds, so clearing the executions leaves no path
-- back to in-flight state carrying candidates in the old shape.
--
-- Dropped rather than deleted because the repositories recreate their own tables on
-- construction, which happens after migrations run.

DROP TABLE IF EXISTS core_review_conversations;
DROP TABLE IF EXISTS review_execution_aliases;
DROP TABLE IF EXISTS review_executions;
DROP TABLE IF EXISTS core_finding_cache;
DROP TABLE IF EXISTS core_review_snapshots;
