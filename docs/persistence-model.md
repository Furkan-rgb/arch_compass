# Persistence model

ArchCompass separates resumable execution storage from architectural history.

```text
review-checkpoints.db
  LangGraph thread/checkpoint state

archcompass-v2.db
  repository and atlas records
  case revisions
  immutable review snapshots
  execution-to-review aliases
  standing-decision history
  finding cache
  review conversations
  model selection
  retrieval approvals and provenance
```

Checkpoint IDs are never review IDs. Domain lineage uses repository/branch identity,
sequence, and `previous_review_id`.

## Immutable records

Review snapshots are inserted at awaiting, completed, failed, and cancelled boundaries.
Case answers create new case revisions. Standing decisions and conversations are append-only.
Pydantic `TypeAdapter` codecs validate stored JSON before domain dataclasses are rebuilt.

The finding cache is keyed from the candidate, case, generic retrieval identity, reasoning
model, and prompt. It is an optimization, not a source of domain identity. Retrieval
manifests persisted on reviews explain exactly which policies were selected.

## Schema epoch

The clean-break database is epoch 2. A pre-refactor `archcompass.db` is detected before the
runtime opens and is never changed automatically.

```bash
archcompass workspace export-legacy /path/to/export.db
archcompass workspace reset
```

Export copies the legacy database. Reset is explicit and recoverable: it moves the database
and its WAL/SHM companions under `.archcompass/legacy-backups/` before initializing epoch 2.
A fresh or reset runtime does not recreate the legacy database.

Explicit review deletion remains available to the user. Startup and normal execution never
silently erase architectural history.
