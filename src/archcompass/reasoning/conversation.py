"""Grounded follow-up conversation over an immutable clean-break Review."""

from __future__ import annotations

from dataclasses import replace

from archcompass.domain._support import new_id, utc_now
from archcompass.ports.review_conversation import (
    ConversationMessage,
    ConversationReviewStore,
    ConversationStore,
    ReviewAnswerer,
    ReviewConversation,
)


class CoreReviewConversationService:
    def __init__(
        self,
        *,
        reviews: ConversationReviewStore,
        conversations: ConversationStore,
        answerer: ReviewAnswerer,
    ) -> None:
        self._reviews = reviews
        self._conversations = conversations
        self._answerer = answerer

    def create(self, review_id: str) -> ReviewConversation:
        self._reviews.get(review_id)
        return self._conversations.record(
            ReviewConversation(new_id("conversation"), review_id)
        )

    def list(self, review_id: str) -> tuple[ReviewConversation, ...]:
        self._reviews.get(review_id)
        return self._conversations.list_for_review(review_id)

    def show(self, conversation_id: str) -> ReviewConversation:
        return self._conversations.get(conversation_id)

    def delete(self, conversation_id: str) -> None:
        """Discard one line of questioning.

        A conversation is a reader's own working notes over an immutable review, not part
        of the audit record — the review, its findings and the standing decisions are
        untouched by this. So it is theirs to throw away.
        """

        self._conversations.delete(conversation_id)

    def ask(self, conversation_id: str, question: str) -> ReviewConversation:
        if not question.strip():
            raise ValueError("conversation question cannot be empty")
        conversation = self._conversations.get(conversation_id)
        review = self._reviews.get(conversation.review_id)
        answer = self._answerer.answer(review, conversation.messages, question.strip())
        return self._conversations.record(
            replace(
                conversation,
                messages=(
                    *conversation.messages,
                    ConversationMessage(question.strip(), answer, utc_now()),
                ),
            )
        )
