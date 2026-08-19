CREATE TABLE IF NOT EXISTS atlas_versions (
    version_id TEXT PRIMARY KEY,
    repository_identity TEXT NOT NULL,
    root_path TEXT NOT NULL,
    git_commit_sha TEXT,
    root_commit_sha TEXT,
    branch_name TEXT,
    repo_id TEXT,
    branch_id TEXT,
    content_fingerprint TEXT NOT NULL,
    parser_version TEXT NOT NULL,
    analysis_config_hash TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS atlas_versions_root_created
    ON atlas_versions(root_path, created_at DESC);

CREATE INDEX IF NOT EXISTS atlas_versions_by_branch
    ON atlas_versions(branch_id);

CREATE TABLE IF NOT EXISTS atlas_nodes (
    version_id TEXT NOT NULL REFERENCES atlas_versions(version_id),
    atlas_id TEXT NOT NULL,
    node_json TEXT NOT NULL,
    PRIMARY KEY (version_id, atlas_id)
);

CREATE TABLE IF NOT EXISTS atlas_edges (
    version_id TEXT NOT NULL REFERENCES atlas_versions(version_id),
    edge_id TEXT NOT NULL,
    edge_json TEXT NOT NULL,
    PRIMARY KEY (version_id, edge_id)
);

CREATE TABLE IF NOT EXISTS atlas_metrics (
    version_id TEXT NOT NULL REFERENCES atlas_versions(version_id),
    node_id TEXT NOT NULL,
    metrics_json TEXT NOT NULL,
    PRIMARY KEY (version_id, node_id)
);

CREATE TABLE IF NOT EXISTS atlas_signals (
    version_id TEXT NOT NULL REFERENCES atlas_versions(version_id),
    ordinal INTEGER NOT NULL,
    signal_json TEXT NOT NULL,
    PRIMARY KEY (version_id, ordinal)
);

CREATE TABLE IF NOT EXISTS atlas_module_facts (
    version_id TEXT NOT NULL REFERENCES atlas_versions(version_id),
    node_id TEXT NOT NULL,
    facts_json TEXT NOT NULL,
    PRIMARY KEY (version_id, node_id)
);

CREATE TABLE IF NOT EXISTS repository_lineages (
    repo_id TEXT PRIMARY KEY,
    root_commit_sha TEXT,
    canonical_root TEXT NOT NULL,
    first_seen_at TEXT NOT NULL,
    lineage_json TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS branch_lineages (
    branch_id TEXT PRIMARY KEY,
    repo_id TEXT NOT NULL REFERENCES repository_lineages(repo_id),
    branch_name TEXT NOT NULL,
    base_branch_id TEXT,
    first_seen_at TEXT NOT NULL,
    lineage_json TEXT NOT NULL,
    UNIQUE (repo_id, branch_name)
);

CREATE INDEX IF NOT EXISTS branch_lineages_by_repository
    ON branch_lineages(repo_id);

CREATE TABLE IF NOT EXISTS policy_source_registrations (
    canonical_path TEXT PRIMARY KEY,
    registered_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS scope_selections (
    root_path TEXT PRIMARY KEY,
    excluded_paths TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS source_origins (
    root_path TEXT PRIMARY KEY,
    url TEXT NOT NULL,
    revision TEXT,
    fetched_at TEXT NOT NULL
);
