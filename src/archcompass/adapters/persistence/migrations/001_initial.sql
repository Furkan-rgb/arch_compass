CREATE TABLE IF NOT EXISTS schema_migrations (
    version INTEGER PRIMARY KEY,
    applied_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS cases (
    case_id TEXT PRIMARY KEY,
    current_revision INTEGER NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS case_revisions (
    case_id TEXT NOT NULL,
    revision INTEGER NOT NULL,
    event_type TEXT NOT NULL,
    actor TEXT NOT NULL,
    origin_run_id TEXT,
    created_at TEXT NOT NULL,
    snapshot_json TEXT NOT NULL,
    PRIMARY KEY (case_id, revision),
    FOREIGN KEY (case_id) REFERENCES cases(case_id)
);

CREATE TABLE IF NOT EXISTS atlas_versions (
    version_id TEXT PRIMARY KEY,
    repository_identity TEXT NOT NULL,
    root_path TEXT NOT NULL,
    git_commit_sha TEXT,
    content_fingerprint TEXT NOT NULL,
    parser_version TEXT NOT NULL,
    analysis_config_hash TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS atlas_versions_root_created
    ON atlas_versions(root_path, created_at DESC);

CREATE TABLE IF NOT EXISTS atlas_nodes (
    version_id TEXT NOT NULL,
    atlas_id TEXT NOT NULL,
    node_json TEXT NOT NULL,
    PRIMARY KEY (version_id, atlas_id),
    FOREIGN KEY (version_id) REFERENCES atlas_versions(version_id)
);

CREATE TABLE IF NOT EXISTS atlas_edges (
    version_id TEXT NOT NULL,
    edge_id TEXT NOT NULL,
    edge_json TEXT NOT NULL,
    PRIMARY KEY (version_id, edge_id),
    FOREIGN KEY (version_id) REFERENCES atlas_versions(version_id)
);

CREATE TABLE IF NOT EXISTS atlas_metrics (
    version_id TEXT NOT NULL,
    node_id TEXT NOT NULL,
    metrics_json TEXT NOT NULL,
    PRIMARY KEY (version_id, node_id),
    FOREIGN KEY (version_id) REFERENCES atlas_versions(version_id)
);

CREATE TABLE IF NOT EXISTS atlas_signals (
    version_id TEXT NOT NULL,
    ordinal INTEGER NOT NULL,
    signal_json TEXT NOT NULL,
    PRIMARY KEY (version_id, ordinal),
    FOREIGN KEY (version_id) REFERENCES atlas_versions(version_id)
);

CREATE TABLE IF NOT EXISTS policy_index_versions (
    version_id TEXT PRIMARY KEY,
    embedding_provider TEXT NOT NULL,
    embedding_model TEXT NOT NULL,
    dimensions INTEGER NOT NULL,
    corpus_hash TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS policies (
    version_id TEXT NOT NULL,
    policy_id TEXT NOT NULL,
    policy_json TEXT NOT NULL,
    PRIMARY KEY (version_id, policy_id),
    FOREIGN KEY (version_id) REFERENCES policy_index_versions(version_id)
);

CREATE TABLE IF NOT EXISTS policy_chunks (
    version_id TEXT NOT NULL,
    chunk_id TEXT NOT NULL,
    policy_id TEXT NOT NULL,
    chunk_json TEXT NOT NULL,
    PRIMARY KEY (version_id, chunk_id),
    FOREIGN KEY (version_id, policy_id) REFERENCES policies(version_id, policy_id)
);

CREATE TABLE IF NOT EXISTS policy_vector_rows (
    rowid INTEGER PRIMARY KEY AUTOINCREMENT,
    version_id TEXT NOT NULL,
    chunk_id TEXT NOT NULL,
    dimensions INTEGER NOT NULL,
    UNIQUE(version_id, chunk_id),
    FOREIGN KEY (version_id, chunk_id) REFERENCES policy_chunks(version_id, chunk_id)
);

CREATE TABLE IF NOT EXISTS consultation_runs (
    run_id TEXT PRIMARY KEY,
    case_id TEXT NOT NULL,
    input_case_revision INTEGER NOT NULL,
    status TEXT NOT NULL,
    completed_at TEXT NOT NULL,
    run_json TEXT NOT NULL,
    FOREIGN KEY (case_id, input_case_revision)
        REFERENCES case_revisions(case_id, revision)
);

