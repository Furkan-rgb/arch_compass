CREATE TABLE IF NOT EXISTS report_conversations (
    conversation_id TEXT PRIMARY KEY,
    consultation_run_id TEXT NOT NULL,
    case_id TEXT NOT NULL,
    case_revision INTEGER NOT NULL,
    atlas_version_id TEXT,
    policy_index_version_id TEXT,
    title TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    current_summary TEXT,
    summary_through_ordinal INTEGER NOT NULL,
    message_count INTEGER NOT NULL,
    revision INTEGER NOT NULL,
    CHECK (summary_through_ordinal >= 0),
    CHECK (message_count >= 0),
    CHECK (revision >= 0),
    CHECK (summary_through_ordinal <= message_count),
    CHECK (
        (current_summary IS NULL AND summary_through_ordinal = 0)
        OR (current_summary IS NOT NULL AND summary_through_ordinal > 0)
    ),
    FOREIGN KEY (consultation_run_id) REFERENCES consultation_runs(run_id),
    FOREIGN KEY (case_id, case_revision)
        REFERENCES case_revisions(case_id, revision),
    FOREIGN KEY (atlas_version_id) REFERENCES atlas_versions(version_id),
    FOREIGN KEY (policy_index_version_id)
        REFERENCES policy_index_versions(version_id)
);

CREATE INDEX IF NOT EXISTS report_conversations_run_updated
    ON report_conversations(consultation_run_id, updated_at, conversation_id);

CREATE TABLE IF NOT EXISTS report_conversation_messages (
    message_id TEXT PRIMARY KEY,
    conversation_id TEXT NOT NULL,
    ordinal INTEGER NOT NULL,
    role TEXT NOT NULL,
    created_at TEXT NOT NULL,
    message_json TEXT NOT NULL,
    CHECK (ordinal >= 1),
    CHECK (role IN ('user', 'assistant')),
    UNIQUE (conversation_id, ordinal),
    UNIQUE (conversation_id, message_id, role),
    FOREIGN KEY (conversation_id)
        REFERENCES report_conversations(conversation_id)
);

CREATE INDEX IF NOT EXISTS report_conversation_messages_recent
    ON report_conversation_messages(conversation_id, ordinal DESC);

CREATE TABLE IF NOT EXISTS report_conversation_summaries (
    conversation_id TEXT NOT NULL,
    summary_revision INTEGER NOT NULL,
    through_ordinal INTEGER NOT NULL,
    created_at TEXT NOT NULL,
    summary_json TEXT NOT NULL,
    CHECK (summary_revision >= 1),
    CHECK (through_ordinal >= 1),
    PRIMARY KEY (conversation_id, summary_revision),
    FOREIGN KEY (conversation_id)
        REFERENCES report_conversations(conversation_id)
);

CREATE TABLE IF NOT EXISTS report_conversation_errors (
    error_id TEXT PRIMARY KEY,
    conversation_id TEXT NOT NULL,
    user_message_id TEXT NOT NULL,
    user_message_role TEXT NOT NULL DEFAULT 'user',
    stage TEXT NOT NULL,
    created_at TEXT NOT NULL,
    error_json TEXT NOT NULL,
    CHECK (user_message_role = 'user'),
    FOREIGN KEY (conversation_id)
        REFERENCES report_conversations(conversation_id),
    FOREIGN KEY (conversation_id, user_message_id, user_message_role)
        REFERENCES report_conversation_messages(conversation_id, message_id, role)
);
