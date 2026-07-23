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
- `consultation_runs`: immutable complete execution and report record.

Case append uses optimistic revision matching in the same transaction as the new snapshot.
Atlas and policy rebuilds always insert new version rows. Old consultations continue to reference
the exact evidence versions they used.

ArchCompass state defaults to `<workspace>/.archcompass/archcompass.db`; analysed repositories are
never used as persistence destinations by indexing or advice commands.

