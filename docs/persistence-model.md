# Persistence model

SQLite is private to persistence and retrieval adapters. Connections enable foreign keys, WAL,
and a busy timeout; `sqlite-vec` is loaded only for vector operations. Numbered SQL migrations are
embedded in the package and applied explicitly during initialization. Each migration file and
its migration-ledger insert commit atomically; a failing later statement cannot leave an earlier
schema or data change applied.

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
- `consultation_jobs`: mutable local queue status linked to a fixed case revision and run ID.
- `consultation_progress_events`: append-only, ordered structured milestones for one job.
- `report_conversations`: mutable revision/count/summary pointer pinned to one immutable run.
- `report_conversation_messages`: immutable, append-only messages with unique conversation
  ordinal; assistant rows retain structured answers and compact retrieval audits rather than
  copies of report, Atlas, or policy aggregates.
- `report_conversation_summaries`: immutable rolling-summary revisions and covered ordinal.
- `report_conversation_errors`: explicit failed answer attempts and post-answer summarization
  failures linked to the originating user message.

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
existing tables. Report and run output uses schema version 3, and stored documents are decoded
strictly: a row written by an earlier, unreleased schema raises `UnreadableStoredRecordError`
naming the record rather than being reinterpreted. No migration deletes stored rows; the owning
consultation is re-run to regenerate a readable record.

Migration `003_consultation_jobs.sql` adds list-query indexes plus the local execution tables.
Progress events contain validated structured artifacts and sanitized errors, not full prompts or
hidden model reasoning. Terminal consultation runs remain immutable and authoritative; job state
exists only to support queuing, live progress, reconnect replay, warnings, and interruption
recovery.

Migration `006_report_conversations.sql` leaves the deprecated `report_follow_ups` table and its
rows intact. V1.2 removes the old route and UI and does not backfill those rows into conversations;
retention is solely a non-destructive migration guarantee.

Conversation creation validates the exact successful run, validated report, case revision, Atlas
version, and policy-index version inside the same immediate transaction that creates the pinned
row. Every message append and summary update uses compare-and-swap revision matching, so
concurrent writes cannot silently reorder ordinals. Assistant rows require a structured answer,
retrieval audit, model identity, and prompt identities. Summary updates require the next revision,
strictly increasing coverage, and a covered ordinal no greater than the persisted message count.
Error rows may reference only a user message from the same conversation. Additional source
snapshots are persisted only when they are bounded and cannot be reconstructed from immutable
pinned stores.
