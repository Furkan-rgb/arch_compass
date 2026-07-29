-- Remove the policy index. Nothing ranked the corpus any more, so nothing read these rows.
--
-- The index existed to retrieve a few policy sections against a query. It has not served
-- that purpose since the judging stage began receiving every policy in one request and the
-- conversation began carrying the corpus whole: 48 policies against an input budget near
-- 490,000 characters (master plan §6A, ADR 0013). What was left was a build step that
-- embedded 432 chunks on demand and a version stamp nothing displayed.
--
-- Dropped rather than left in place, on the same grounds as migration 017: these are a
-- derived cache holding no record, regenerable from the Markdown at any time, and a table
-- nothing reads is an invitation to wonder what it was for.
--
-- Child before parent, because foreign keys are only suspended for the length of this
-- script and `foreign_key_check` runs before it commits. `IF EXISTS` throughout: a
-- workspace created after this never had them.
--
-- What this migration cannot drop, and why it is safe to leave. Each rebuild created a
-- `vec0` virtual table named `policy_vectors_d<dim>_<version_id>`, plus five shadow tables
-- per index. Both halves of that defeat static SQL: the names carry a generated version id,
-- so they cannot be enumerated in a script, and `DROP TABLE` on a virtual table asks its
-- module to destroy itself — which fails with `no such module: vec0` once `sqlite-vec` is
-- no longer a dependency, verified rather than assumed. Keeping the dependency solely so
-- this migration could delete its own leftovers would mean paying for the index for ever in
-- order to be rid of it.
--
-- So they remain, inert. Nothing opens them, they hold no foreign key into anything that
-- survives, and `foreign_key_check` does not walk them. A workspace that wants the space
-- back can drop them by name while the extension is still installed; a workspace that never
-- ran a rebuild has none.

DROP TABLE IF EXISTS policy_vector_rows;
DROP TABLE IF EXISTS policy_chunks;
DROP TABLE IF EXISTS policies;
DROP TABLE IF EXISTS policy_index_versions;
