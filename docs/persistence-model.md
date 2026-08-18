# Persistence model

ArchCompass separates resumable execution storage from architectural history.

```text
review-checkpoints.db
  LangGraph thread/checkpoint state

workspace.sqlite3
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

## Startup

The runtime opens `.archcompass/workspace.sqlite3` and initializes it when missing. This is
the sole application database name; other files in `.archcompass/` are neither interpreted
nor allowed to block startup.

Explicit review deletion remains available to the user. Startup and normal execution never
silently erase architectural history.
