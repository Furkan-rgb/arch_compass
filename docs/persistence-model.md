# Persistence model

SQLite is private to persistence and retrieval adapters. Connections enable foreign keys, WAL,
and a busy timeout; `sqlite-vec` is loaded only for vector operations. Numbered SQL migrations are
embedded in the package and applied explicitly during initialization.

## Tables and ownership

- `cases`: materialized current-revision pointer and timestamps.
- `case_revisions`: immutable complete snapshots keyed by case and revision.
- `atlas_versions`: immutable repository evidence identity.
- `atlas_nodes`, `atlas_edges`, `atlas_metrics`, `atlas_signals`: evidence owned by one version.
- `policy_index_versions`: immutable corpus/model/dimension identity.
- `policies`, `policy_chunks`: original validated policy data by index version.
- `policy_vector_rows`: stable relational mapping to dimension-specific `vec0` rows.
- `policy_source_registrations`: canonical persistent workspace policy-source paths.
- `consultation_runs`: immutable successful or failed execution and report record.

Case append uses optimistic revision matching in the same transaction as the new snapshot.
Atlas and policy rebuilds always insert new version rows. Old consultations continue to reference
the exact evidence versions they used. A successful consultation inserts its run and next case
revision atomically. Once a valid input case is loaded, a terminal workflow failure is stored as a
failed run with its partial audit data and never advances the case.

ArchCompass state defaults to `<workspace>/.archcompass/archcompass.db`; analysed repositories are
never used as persistence destinations by indexing or advice commands. The workspace may not
equal or be contained by an analysed repository. Database and report paths are revalidated inside
the workspace and reject traversal or symlink escapes.

Migration `002_policy_source_registrations.sql` adds the source registry without replacing
existing tables. Stored schema-v1 case and run JSON remains readable through model upgrade
validators; new case, atlas, policy-index, report, and run output uses schema version 2.
