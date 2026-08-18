"""SQLite persistence for clean-break review conversations."""

from __future__ import annotations

import sqlite3
from collections.abc import Callable

from archcompass.adapters.persistence.dataclass_records import DataclassRecordCodec
from archcompass.domain.errors import ConversationNotFoundError
from archcompass.ports.review_conversation import ReviewConversation


class SQLiteCoreConversationRepository:
    def __init__(self, connect: Callable[[], sqlite3.Connection]) -> None:
        self._connect = connect
        self._codec = DataclassRecordCodec(ReviewConversation)
        with self._connect() as connection:
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
        with self._connect() as connection:
            connection.execute(
                "INSERT INTO core_review_conversations(conversation_id, review_id, "
                "conversation_json) VALUES (?, ?, ?) "
                "ON CONFLICT(conversation_id) DO UPDATE SET "
                "conversation_json=excluded.conversation_json",
                (conversation.id, conversation.review_id, document),
            )
        return conversation

    def get(self, conversation_id: str) -> ReviewConversation:
        with self._connect() as connection:
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
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT conversation_json FROM core_review_conversations "
                "WHERE review_id = ? ORDER BY conversation_id",
                (review_id,),
            ).fetchall()
        return tuple(
            self._codec.decode(str(row[0]), description="Review conversation")
            for row in rows
        )
