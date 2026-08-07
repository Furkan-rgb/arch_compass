-- A repository remembers which of its folders it is reviewed without.
--
-- A visitor who points Arch Compass at a large repository is usually not asking about all of
-- it. The tests, the docs, the vendored copy of somebody else's library are code, and they
-- spend the same node cap and the same memory as the code the review is about — so a scope
-- that leaves them out is the difference between a repository being reviewable here and not.
--
-- The choice could have been passed with each request and forgotten afterwards, and that is
-- exactly what does not work. A scoped analysis fingerprints the files it read, and every
-- later use of that atlas asks the repository what it fingerprints as *now* to decide whether
-- the stored evidence is still true. Asked without the exclusions, that recomputation reads
-- the folders the analysis skipped, produces a different digest, and reports the atlas stale
-- — permanently, because re-indexing it would land in the same place. The selection has to
-- outlive the request that made it or a scoped atlas can never be fresh.
--
-- Keyed by the canonical root path, like `source_origins` and like what every stored atlas
-- already holds, so a freshness check that starts from a stored atlas can find the selection
-- from the one string it has.
--
-- `excluded_paths` is a JSON array of relative POSIX directory paths, sorted, de-duplicated
-- and with nested entries collapsed before it is written (see `domain/scope.py`). An empty
-- array is a real answer and is not the same as having no row: it says somebody looked at
-- the folder list and chose to review everything, and it survives a re-index that names no
-- scope, where a missing row would mean "nobody has chosen".

CREATE TABLE IF NOT EXISTS scope_selections (
    root_path      TEXT PRIMARY KEY,
    excluded_paths TEXT NOT NULL,
    updated_at     TEXT NOT NULL
);
