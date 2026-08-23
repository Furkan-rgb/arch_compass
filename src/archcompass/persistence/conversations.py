"""SQLite persistence for clean-break review conversations."""

from __future__ import annotations

from archcompass.domain.errors import ConversationNotFoundError
from archcompass.persistence.sqlite.codecs import DataclassRecordCodec
from archcompass.persistence.sqlite.database import Transaction
from archcompass.reasoning.ports import ReviewConversation


class SQLiteCoreConversationRepository:
    def __init__(self, transaction: Transaction) -> None:
        self._transaction = transaction
        self._codec = DataclassRecordCodec(ReviewConversation)
        with self._transaction() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS core_review_conversations (
                    conversation_id TEXT PRIMARY KEY,
                    review_id TEXT NOT NULL REFERENCES core_review_snapshots(review_id)
                        ON DELETE CASCADE,
                    conversation_json TEXT NOT NULL
                )
                """
            )

    def record(self, conversation: ReviewConversation) -> ReviewConversation:
        document = self._codec.encode(conversation)
        with self._transaction() as connection:
            connection.execute(
                "INSERT INTO core_review_conversations(conversation_id, review_id, "
                "conversation_json) VALUES (?, ?, ?) "
                "ON CONFLICT(conversation_id) DO UPDATE SET "
                "conversation_json=excluded.conversation_json",
                (conversation.id, conversation.review_id, document),
            )
        return conversation

    def get(self, conversation_id: str) -> ReviewConversation:
        with self._transaction() as connection:
            row = connection.execute(
                "SELECT conversation_json FROM core_review_conversations "
                "WHERE conversation_id = ?",
                (conversation_id,),
            ).fetchone()
        if row is None:
            raise ConversationNotFoundError(
                f"Review conversation {conversation_id} was not found"
            )
        return self._codec.decode(str(row[0]), description="Review conversation")

    def list_for_review(self, review_id: str) -> tuple[ReviewConversation, ...]:
        # Oldest first, by insertion. The conversation id is a UUID, so ordering by it put
        # a reader's conversations in an order nothing on screen could explain.
        with self._transaction() as connection:
            rows = connection.execute(
                "SELECT conversation_json FROM core_review_conversations "
                "WHERE review_id = ? ORDER BY rowid",
                (review_id,),
            ).fetchall()
        return tuple(
            self._codec.decode(str(row[0]), description="Review conversation")
            for row in rows
        )

    def delete(self, conversation_id: str) -> None:
        with self._transaction() as connection:
            deleted = connection.execute(
                "DELETE FROM core_review_conversations WHERE conversation_id = ?",
                (conversation_id,),
            ).rowcount
        if not deleted:
            raise ConversationNotFoundError(
                f"Review conversation {conversation_id} was not found"
            )
