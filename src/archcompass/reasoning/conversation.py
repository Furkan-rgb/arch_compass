"""Grounded follow-up conversation over an immutable clean-break Review."""

from __future__ import annotations

from dataclasses import replace

from archcompass.domain import Question, Review
from archcompass.domain._support import new_id, utc_now
from archcompass.domain.errors import ConversationValidationError
from archcompass.persistence.ports import ReviewSnapshots
from archcompass.reasoning.ports import (
    ConversationMessage,
    ConversationStore,
    ReviewAnswerer,
    ReviewConversation,
)


class CoreReviewConversationService:
    def __init__(
        self,
        *,
        reviews: ReviewSnapshots,
        conversations: ConversationStore,
        answerer: ReviewAnswerer,
    ) -> None:
        self._reviews = reviews
        self._conversations = conversations
        self._answerer = answerer

    def create(self, review_id: str, question_id: str = "") -> ReviewConversation:
        """Open a thread, over the whole review or over one question it is waiting on.

        The question is checked against the review here rather than at the first message.
        A thread scoped to a question the review never asked cannot be answered later, and
        a reader who opened one would find that out one round trip after it mattered.
        """

        review = self._reviews.get(review_id)
        if question_id:
            _question(review, question_id)
        return self._conversations.record(
            ReviewConversation(new_id("conversation"), review_id, question_id=question_id)
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
            raise ConversationValidationError("conversation question cannot be empty")
        conversation = self._conversations.get(conversation_id)
        review = self._reviews.get(conversation.review_id)
        answer = self._answerer.answer(
            review,
            conversation.messages,
            question.strip(),
            about=(
                _question(review, conversation.question_id) if conversation.question_id else None
            ),
        )
        return self._conversations.record(
            replace(
                conversation,
                messages=(
                    *conversation.messages,
                    ConversationMessage(question.strip(), answer, utc_now()),
                ),
            )
        )


def _question(review: Review, question_id: str) -> Question:
    """The clarification question a thread is about, as the review recorded it.

    Read off the snapshot rather than carried on the conversation. The question's own text
    and proposed options are what a thread is answerable against, and a copy taken when the
    thread opened would be a second version of a record this product keeps immutable.
    """

    for question in review.questions:
        if question.id == question_id:
            return question
    # Named rather than a bare `ValueError`, because this reaches a client: a request naming
    # a question the review it names never asked is malformed, not a fault in this program.
    raise ConversationValidationError(
        f"Review {review.id} did not ask question {question_id}"
    )
