"""Review-conversation persistence."""

from __future__ import annotations

from archcompass.adapters.persistence.database import SQLiteDatabase
from archcompass.adapters.persistence.stored_records import decode_stored_json
from archcompass.domain.base import utc_now
from archcompass.domain.errors import ConversationNotFoundError
from archcompass.domain.review_conversation import ReviewConversation


class SQLiteReviewConversationRepository:
    def __init__(self, database: SQLiteDatabase) -> None:
        self._database = database

    def create(self, conversation: ReviewConversation) -> ReviewConversation:
        with self._database.connect() as connection:
            connection.execute(
                """
                INSERT INTO review_conversations(
                    conversation_id, review_id, case_id, case_revision, title,
                    message_count, created_at, updated_at, conversation_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    conversation.conversation_id,
                    conversation.review_id,
                    conversation.case_id,
                    conversation.case_revision,
                    conversation.title,
                    len(conversation.messages),
                    conversation.created_at.isoformat(),
                    conversation.created_at.isoformat(),
                    conversation.model_dump_json(),
                ),
            )
            connection.commit()
        return conversation

    def get(self, conversation_id: str) -> ReviewConversation:
        with self._database.connect() as connection:
            row = connection.execute(
                "SELECT conversation_json FROM review_conversations WHERE conversation_id = ?",
                (conversation_id,),
            ).fetchone()
        if row is None:
            raise ConversationNotFoundError(
                f"Review conversation {conversation_id} was not found"
            )
        return decode_stored_json(
            ReviewConversation,
            row["conversation_json"],
            description=f"Review conversation {conversation_id}",
            remedy="Start a new thread on the review and ask again.",
        )

    def append(self, conversation: ReviewConversation) -> ReviewConversation:
        """Replace the stored document, refusing to drop or reorder history.

        The guard is a compare-and-swap on message count inside the write. Two turns
        answered concurrently would otherwise both read a history of N, both write N+1, and
        the slower write would silently discard the other's message.
        """

        with self._database.connect() as connection:
            row = connection.execute(
                "SELECT message_count FROM review_conversations WHERE conversation_id = ?",
                (conversation.conversation_id,),
            ).fetchone()
            if row is None:
                raise ConversationNotFoundError(
                    f"Review conversation {conversation.conversation_id} was not found"
                )
            stored = int(row["message_count"])
            if len(conversation.messages) != stored + 1:
                raise ConversationNotFoundError(
                    f"Review conversation {conversation.conversation_id} changed while this "
                    f"answer was being produced ({stored} messages stored, "
                    f"{len(conversation.messages) - 1} expected)"
                )
            connection.execute(
                """
                UPDATE review_conversations
                SET message_count = ?, updated_at = ?, conversation_json = ?
                WHERE conversation_id = ? AND message_count = ?
                """,
                (
                    len(conversation.messages),
                    utc_now().isoformat(),
                    conversation.model_dump_json(),
                    conversation.conversation_id,
                    stored,
                ),
            )
            connection.commit()
        return conversation

    def list(self, *, review_id: str) -> list[ReviewConversation]:
        with self._database.connect() as connection:
            rows = connection.execute(
                """
                SELECT conversation_json FROM review_conversations
                WHERE review_id = ?
                ORDER BY created_at DESC, conversation_id
                """,
                (review_id,),
            ).fetchall()
        return [
            decode_stored_json(
                ReviewConversation,
                row["conversation_json"],
                description="A stored review conversation",
                remedy="Start a new thread on the review and ask again.",
            )
            for row in rows
        ]
