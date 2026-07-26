"""Ask follow-up questions about one immutable boundary review.

No retrieval, no budgets, no rolling summary. A review serialises to roughly 25,000
characters — about five per cent of a 128k input budget — so the whole thing goes into
every turn along with the history. The V1.2 report conversation needs 3,800 lines of
retrieval machinery because a consultation's evidence does not fit; here it does, and
building the same machinery anyway would be indirection in front of one concrete thing.

The pin is the review, and through it the exact case revision and atlas the review ran
against. A conversation therefore cannot drift onto evidence that did not exist when the
verdicts were reached.
"""

from __future__ import annotations

from archcompass.domain.errors import (
    ConversationNotFoundError,
    ConversationValidationError,
    ProviderError,
)
from archcompass.domain.review import BoundaryReview, ReviewStatus
from archcompass.domain.review_conversation import (
    MAX_QUESTION_CHARACTERS,
    ReviewConversation,
    ReviewMessage,
)
from archcompass.ports.reasoning import FocusedReasoningProvider
from archcompass.ports.repositories import (
    BoundaryReviewRepository,
    CaseRepository,
    ReviewConversationRepository,
)


class ReviewConversationService:
    def __init__(
        self,
        *,
        reviews: BoundaryReviewRepository,
        cases: CaseRepository,
        conversations: ReviewConversationRepository,
        reasoner: FocusedReasoningProvider,
    ) -> None:
        self._reviews = reviews
        self._cases = cases
        self._conversations = conversations
        self._reasoner = reasoner

    def create(self, review_id: str, *, title: str | None = None) -> ReviewConversation:
        review = self._load(review_id)
        report = review.report
        assert report is not None  # guaranteed by _load
        # Reading the pinned revision is the check that it still exists, not decoration:
        # a conversation that opens against a case revision the workspace no longer holds
        # would answer from a review whose grounds cannot be shown.
        self._cases.get(review.case_id, review.case_revision)
        chosen = (title or "").strip()
        return self._conversations.create(
            ReviewConversation(
                review_id=review.review_id,
                case_id=review.case_id,
                case_revision=review.case_revision,
                title=chosen or f"{report.case_title} — review questions",
            )
        )

    def show(self, conversation_id: str) -> ReviewConversation:
        return self._conversations.get(conversation_id)

    def list(self, review_id: str) -> list[ReviewConversation]:
        return self._conversations.list(review_id=review_id)

    def ask(self, conversation_id: str, question: str) -> ReviewMessage:
        text = question.strip()
        if not text:
            raise ConversationValidationError("A review question must not be blank")
        if len(text) > MAX_QUESTION_CHARACTERS:
            raise ConversationValidationError(
                f"A review question must contain at most {MAX_QUESTION_CHARACTERS} characters"
            )
        conversation = self._conversations.get(conversation_id)
        review = self._load(conversation.review_id)
        try:
            answer = self._reasoner.answer_review_question(
                review,
                conversation.messages,
                text,
            )
        except ProviderError as error:
            # The failed turn is appended rather than dropped. A question that produced
            # nothing is part of the history a reader needs to make sense of what follows,
            # and silently discarding it makes the conversation look like it was never asked.
            message = ReviewMessage(
                ordinal=conversation.next_ordinal,
                question=text,
                failure=str(error),
            )
        else:
            message = ReviewMessage(
                ordinal=conversation.next_ordinal,
                question=text,
                answer=answer,
            )
        appended = conversation.model_copy(
            update={"messages": [*conversation.messages, message]}
        )
        self._conversations.append(appended)
        return message

    def _load(self, review_id: str) -> BoundaryReview:
        review = self._reviews.get(review_id)
        if review.status is not ReviewStatus.SUCCEEDED or review.report is None:
            raise ConversationNotFoundError(
                f"Review {review_id} did not succeed, so it has nothing to discuss"
            )
        return review
