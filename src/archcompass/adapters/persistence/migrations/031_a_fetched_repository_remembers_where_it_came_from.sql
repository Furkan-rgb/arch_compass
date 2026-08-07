-- A fetched repository remembers where it came from, so its absence is recoverable.
--
-- A workspace that fetches source archives holds a bounded amount of code and deletes the
-- least recently used to stay inside it, because on the deployment that does this the
-- filesystem is memory and running out kills every session on the instance rather than the
-- one fetch. So a directory going away is ordinary, not exceptional.
--
-- It was also, until this table, irreversible. A clone can be asked where it came from —
-- git records the remote — but an extracted archive has no `.git` to ask, so once the
-- directory went, nothing in the workspace knew what had been in it. A stored atlas would
-- go on naming a path that no longer existed, and the run that tried to use it failed with
-- "repository does not exist": a dead end produced by throwing away one short string.
--
-- Keyed by the directory rather than by anything derived, because the directory is what
-- every stored atlas already refers to and what a request arrives holding. The name is
-- deterministic from the address (a slug and a digest of it), so a re-fetch of the same
-- address lands in the same place and this row still describes it.
--
-- `revision` is what the host said it served, read out of the archive's own top-level
-- directory. Recorded so a re-fetch asks for the same commit rather than for whatever the
-- branch points at now: the atlas holds line numbers, and code that shifted under them
-- would make every stored excerpt quietly cite the wrong lines. Nullable, because a host
-- that names its archive some other way is a host we can still fetch from — such a
-- repository simply cannot be restored, and says so, rather than being restored wrongly.

CREATE TABLE IF NOT EXISTS source_origins (
    root_path   TEXT PRIMARY KEY,
    url         TEXT NOT NULL,
    revision    TEXT,
    fetched_at  TEXT NOT NULL
);
