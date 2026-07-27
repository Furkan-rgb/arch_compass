-- Per-module text facts: the constants a module states, and which of this repository's own
-- modules it names.
--
-- Numbered 016 because 015 is retired. A withdrawn embedding index held that number and was
-- applied to real workspaces before being removed, and a version already in
-- `schema_migrations` is never run again — so reusing 015 meant this table was silently
-- skipped in exactly the workspaces that already had data. A migration number is an
-- identifier, not a position in a list: once applied anywhere it is spent, and closing the
-- gap it leaves behind is not worth breaking the workspaces that recorded it.
--
-- Its own table rather than columns on atlas_nodes, because these are properties of a
-- file's whole text rather than of a symbol, and because the detectors that read them
-- compare modules against each other — a fact stored per symbol cannot answer "which
-- modules share this".
--
-- An atlas built by an earlier parser has no rows here. That is not a silent empty result:
-- PARSER_VERSION changed with this table, so such an atlas is stale and is re-analyzed
-- before it can be reviewed.

CREATE TABLE IF NOT EXISTS atlas_module_facts (
    version_id TEXT NOT NULL,
    node_id TEXT NOT NULL,
    facts_json TEXT NOT NULL,
    PRIMARY KEY (version_id, node_id),
    FOREIGN KEY (version_id) REFERENCES atlas_versions(version_id)
);
