-- Which model this workspace reasons with, chosen in the interface rather than in a file.
--
-- The choice could not live where the configuration lives. A `models.*.yaml` is written by
-- hand, carries a comment explaining every number in it, and is committed; rewriting one to
-- record a click would strip that prose out through the YAML round trip. So the file stays
-- the source of everything that was reasoned about — the credential variable, the timeouts,
-- the thinking setting — and this table is the source of the one thing that was picked.
--
-- A reference into a file, not a copy of it. `profile_id` is a basename rather than a path,
-- so a workspace that moves between machines keeps its selection and no absolute path from
-- one ends up in another. A selection whose profile has since gone is reported as exactly
-- that rather than silently falling back, because a file appearing or disappearing is
-- something a reader can act on and a quiet substitution is not.
--
-- One row, enforced by the schema rather than by convention: a workspace reasons with one
-- model, and a second row would be a state nothing knows how to read.
--
-- `failed_at` and `failure_detail` are what the last run made of the choice. A probe cannot
-- discover this — it only asks whether a model is listed, and an exhausted quota lists
-- perfectly well — so it is recorded on the way past the failure itself and cleared by the
-- next successful probe.

CREATE TABLE IF NOT EXISTS reasoning_model_selection (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    profile_id TEXT NOT NULL,
    provider TEXT NOT NULL,
    model TEXT NOT NULL,
    selected_at TEXT NOT NULL,
    failed_at TEXT,
    failure_detail TEXT NOT NULL DEFAULT ''
);
