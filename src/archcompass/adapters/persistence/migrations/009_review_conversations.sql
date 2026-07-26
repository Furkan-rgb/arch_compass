-- Follow-up questions about one boundary review.
--
-- Separate from report_conversations, which pins to a consultation run and carries the
-- retrieval, budget and summary machinery that a review does not need: a whole review fits
-- in one request, so there is no retrieval to audit and no rolling summary to revise.
--
-- Messages live inside conversation_json rather than in their own table. They are only
-- ever read as a complete ordered history alongside the conversation, never queried or
-- paged independently, so a second table would add a join that nothing needs.

CREATE TABLE IF NOT EXISTS review_conversations (
    conversation_id TEXT PRIMARY KEY,
    review_id TEXT NOT NULL,
    case_id TEXT NOT NULL,
    case_revision INTEGER NOT NULL,
    title TEXT NOT NULL,
    message_count INTEGER NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    conversation_json TEXT NOT NULL,
    CHECK (case_revision >= 1),
    CHECK (message_count >= 0),
    FOREIGN KEY (review_id) REFERENCES boundary_reviews(review_id),
    FOREIGN KEY (case_id, case_revision)
        REFERENCES case_revisions(case_id, revision)
);

CREATE INDEX IF NOT EXISTS review_conversations_by_review
    ON review_conversations(review_id, created_at DESC);
