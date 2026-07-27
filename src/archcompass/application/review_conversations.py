"""Ask follow-up questions about one immutable boundary review.

No budgets and no rolling summary. A review serialises to roughly 25,000 characters — about
five per cent of a 128k input budget — so the whole thing goes into every turn along with
the history. The V1.2 report conversation needs 3,800 lines of retrieval machinery because
a consultation's evidence does not fit; here it does, and building the same machinery
anyway would be indirection in front of one concrete thing.

Alongside it goes background — the bundled method primer and the whole policy corpus — so a
reader can ask what a boundary is or what a policy argues, not only what this review found.
It is presented whole rather than retrieved, because it is about 45,000 characters and fits
several times over; an embedding index over it was built and measured first, and it missed
the primer's own "what the detector cannot see" section when asked exactly that. Background
is a different kind of thing from evidence and stays separate: the review says what was
found here and grounds every citation, while background only says what the words mean.

The pin is the review, and through it the exact case revision and atlas the review ran
against. A conversation therefore cannot drift onto evidence that did not exist when the
verdicts were reached.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from archcompass.application.policies import PolicyService
from archcompass.domain.errors import (
    ConversationNotFoundError,
    ConversationValidationError,
    ProviderError,
)
from archcompass.domain.knowledge import MethodKnowledge
from archcompass.domain.review import BoundaryReview, ReviewStatus
from archcompass.domain.review_conversation import (
    MAX_QUESTION_CHARACTERS,
    ReviewAnswer,
    ReviewConversation,
    ReviewMessage,
)
from archcompass.ports.reasoning import FocusedReasoningProvider, StreamingAnswerReasoner
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
        policies: PolicyService,
        method_primer: str,
    ) -> None:
        self._reviews = reviews
        self._cases = cases
        self._conversations = conversations
        self._reasoner = reasoner
        self._policies = policies
        self._method_primer = method_primer

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

    def ask(
        self,
        conversation_id: str,
        question: str,
        on_prose: Callable[[str], None] | None = None,
    ) -> ReviewMessage:
        """Ask one question, and append whatever came of it.

        `on_prose` is an optional window onto the answer being written, not a second way to
        ask. One flow appends one message either way, the same validation decides what that
        message contains, and a caller that passes nothing gets exactly the behaviour it had
        before. Where the reasoner cannot stream, the callback is simply never called.

        Nothing passed to `on_prose` is stored or grounded. The record is the returned
        message, and a reader looking at fragments is looking at prose on its way to being
        checked — which is why a failed turn ends as a failure even after text has appeared.
        """

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
            answer = self._answer(review, conversation.messages, text, on_prose)
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

    def _answer(
        self,
        review: BoundaryReview,
        history: list[ReviewMessage],
        question: str,
        on_prose: Callable[[str], None] | None,
    ) -> ReviewAnswer:
        """Take the streaming route only where both the caller and the reasoner offer it.

        The capability is the reasoner's, so it is asked rather than configured: a workspace
        pointed at a provider whose transport cannot stream answers the question anyway,
        after the last token instead of during, and nothing above here has to know which
        happened. Both calls return the same validated answer.
        """

        background = self._background(review)
        if on_prose is not None and isinstance(self._reasoner, StreamingAnswerReasoner):
            return self._reasoner.stream_review_answer(
                review, history, question, background, on_prose
            )
        return self._reasoner.answer_review_question(review, history, question, background)

    def _background(self, review: BoundaryReview) -> MethodKnowledge:
        """What the advisor knows about its own method, whole.

        The same question every turn, so the answer does not depend on the question: there
        is nothing to rank, and therefore no way for the passage a reader needed to be the
        one left out. Sorted by id, matching the order the judging stage presents policies
        in, so the same corpus reads the same way wherever it appears.

        Not fatal on its own. Background explains the review's vocabulary while the review
        itself carries the evidence and is already in the request, so a corpus that cannot
        be read answers the question without it rather than taking a working conversation
        off a person.
        """

        try:
            policies = sorted(
                self._policies.catalog(repository_root=self._repository_root(review)),
                key=lambda policy: policy.id,
            )
        except Exception:
            policies = []
        return MethodKnowledge(method=self._method_primer, policies=policies)

    def _repository_root(self, review: BoundaryReview) -> Path | None:
        """The repository this review judged, so its own policies are in reach.

        Read from the pinned case revision rather than from the workspace's current state:
        a review's questions are answered against the corpus that review saw, and a
        repository indexed since then has nothing to say about it.
        """

        snapshot = self._cases.get(review.case_id, review.case_revision).snapshot
        root = snapshot.repository.root_path if snapshot.repository else None
        return Path(root) if root else None

    def _load(self, review_id: str) -> BoundaryReview:
        review = self._reviews.get(review_id)
        if review.status is not ReviewStatus.SUCCEEDED or review.report is None:
            raise ConversationNotFoundError(
                f"Review {review_id} did not succeed, so it has nothing to discuss"
            )
        return review
