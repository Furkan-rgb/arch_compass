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
from archcompass.application.review_source import ReviewSourceService
from archcompass.domain.case import AnsweredQuestions
from archcompass.domain.errors import (
    ArchCompassError,
    ConversationNotFoundError,
    ConversationValidationError,
    ProviderError,
)
from archcompass.domain.knowledge import MethodKnowledge
from archcompass.domain.review import (
    AnsweredQuestion,
    BoundaryReview,
    OpenQuestion,
    ReviewEvidence,
    ReviewStatus,
)
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
        source: ReviewSourceService,
        method_primer: str,
    ) -> None:
        self._reviews = reviews
        self._cases = cases
        self._conversations = conversations
        self._reasoner = reasoner
        self._policies = policies
        self._source = source
        self._method_primer = method_primer

    def create(
        self,
        review_id: str,
        *,
        title: str | None = None,
        question_reference: str | None = None,
    ) -> ReviewConversation:
        review = self._load(review_id, about_question=question_reference)
        report = review.report
        assert report is not None  # guaranteed by _load
        # Reading the pinned revision is the check that it still exists, not decoration:
        # a conversation that opens against a case revision the workspace no longer holds
        # would answer from a review whose grounds cannot be shown.
        self._cases.get(review.case_id, review.case_revision)
        question = (
            None if question_reference is None else self._question(review, question_reference)
        )
        chosen = (title or "").strip()
        default = (
            f"{report.case_title} — review questions"
            if question is None
            else f"{question.reference}: {question.question}"
        )
        return self._conversations.create(
            ReviewConversation(
                review_id=review.review_id,
                case_id=review.case_id,
                case_revision=review.case_revision,
                title=chosen or default,
                question_reference=None if question is None else question.reference,
            )
        )

    @staticmethod
    def _question(review: BoundaryReview, reference: str) -> OpenQuestion:
        """The open question a conversation names, or a refusal naming what exists.

        Resolved from the review's own report rather than trusted from the request, which
        is the same rule every other reference obeys (§12.0): `Q-n` is an identifier the
        application assigned, so the application is what turns it back into a question.
        """

        report = review.report
        questions = [] if report is None else report.overview.open_questions
        for question in questions:
            if question.reference == reference:
                return question
        known = ", ".join(item.reference for item in questions) or "none"
        raise ConversationNotFoundError(
            f"Review {review.review_id} asked no question {reference} (it asked: {known})"
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
        review = self._load(
            conversation.review_id, about_question=conversation.question_reference
        )
        try:
            answer = self._answer(review, conversation, text, on_prose)
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
        conversation: ReviewConversation,
        question: str,
        on_prose: Callable[[str], None] | None,
    ) -> ReviewAnswer:
        """Take the streaming route only where both the caller and the reasoner offer it.

        The capability is the reasoner's, so it is asked rather than configured: a workspace
        pointed at a provider whose transport cannot stream answers the question anyway,
        after the last token instead of during, and nothing above here has to know which
        happened. Both calls return the same validated answer.

        Which stage answers is decided by the conversation's pin, not by the review's
        status. A question-scoped conversation about a review that has since concluded still
        goes to the discussion stage: it was opened about one question, it is titled with
        that question, and answering its later turns from the whole review would silently
        change what the thread is about halfway down.
        """

        background = self._background(review)
        if conversation.question_reference is not None:
            about = self._question(review, conversation.question_reference)
            evidence = self._evidence(review, about_question=about)
            if on_prose is not None and isinstance(self._reasoner, StreamingAnswerReasoner):
                return self._reasoner.stream_open_question_discussion(
                    review,
                    evidence,
                    about,
                    conversation.messages,
                    question,
                    background,
                    on_prose,
                )
            return self._reasoner.discuss_open_question(
                review, evidence, about, conversation.messages, question, background
            )
        evidence = self._evidence(review, about_question=None)
        if on_prose is not None and isinstance(self._reasoner, StreamingAnswerReasoner):
            return self._reasoner.stream_review_answer(
                review, evidence, conversation.messages, question, background, on_prose
            )
        return self._reasoner.answer_review_question(
            review, evidence, conversation.messages, question, background
        )

    def _evidence(
        self,
        review: BoundaryReview,
        *,
        about_question: OpenQuestion | None,
    ) -> ReviewEvidence:
        """Everything this review's record holds that the stage about to run may see.

        One place, because the three things assembled here were each once left out of a call
        and each time the stage said the review contained no such thing. An omission is a
        line missing from this method now, rather than an argument missing from one of four
        call sites.

        What varies by stage is scope and nothing else. A question-scoped discussion reads
        only the boundaries that question cites and is told nothing of the round it is part
        of; a concluded review shows everything, because everything is already on the page.
        """

        # The exact revision this review ran against, not the workspace's current case. A
        # conversation is pinned to the review and through it to that revision, so a case
        # edited since must not change what an old review is explained from.
        revision = self._cases.get(review.case_id, review.case_revision)
        if about_question is not None:
            # Only the boundaries this question cites, matching what the stage is shown of
            # the review itself: reading source for verdicts it is not allowed to see would
            # widen the input past the scope that makes it safe to run while waiting.
            return ReviewEvidence(
                case=revision.snapshot,
                excerpts=[
                    excerpt
                    for reference in about_question.supporting_references
                    for excerpt in self._source.for_review(review, reference=reference)
                ],
            )
        # Every boundary, because a concluded review shows every boundary. The code follows
        # whatever the stage is already allowed to reason about.
        elicitation, recorded = self._elicitation(review, revision.answered)
        return ReviewEvidence(
            case=revision.snapshot,
            excerpts=self._source.for_review(review),
            elicitation=elicitation,
            answers_were_recorded=recorded,
        )

    def _elicitation(
        self,
        review: BoundaryReview,
        answered: AnsweredQuestions | None,
    ) -> tuple[list[AnsweredQuestion], bool]:
        """The round that produced this review, joined back together.

        The two halves are stored apart on purpose and neither is the wrong place. A question
        is advisor output and belongs to the review that asked it; an answer is user-authored
        and belongs to the case revision it created (invariant 25). What was missing was only
        the join, and it is a lookup rather than a stored link: `elicited_from` names the pass
        that asked, and the revision this pass pinned records what it answered.

        A first pass has asked nothing yet and gets an empty round. So does a pass whose
        predecessor has since been deleted — the questions are genuinely unavailable then,
        and inventing the shape of a round from the answers alone would be describing
        questions nobody can read.

        Skipped questions are carried with an empty answer rather than dropped. "You were
        asked this and chose not to say" is a fact about the round, and a verdict that still
        hinges is often hinging on exactly that.
        """

        if review.elicited_from is None:
            return [], False
        try:
            asked = self._reviews.get(review.elicited_from)
        except ArchCompassError:
            return [], False
        report = asked.report
        if report is None:
            return [], False
        # Answers only count for the pass they were written against. A revision carrying
        # some other review's round would mean a case edited between the two passes, and
        # pairing across that would attribute text to a question it never answered.
        written: dict[str, str] = {}
        recorded = answered is not None and answered.review_id == asked.review_id
        if answered is not None and recorded:
            written = {
                item.question_reference: item.recorded_text for item in answered.answers
            }
        return [
            AnsweredQuestion(
                question=question,
                answer=written.get(question.reference, ""),
            )
            for question in report.overview.open_questions
        ], recorded

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

    def _load(self, review_id: str, *, about_question: str | None = None) -> BoundaryReview:
        review = self._reviews.get(review_id)
        # A review still waiting on answers is refused a conversation about itself, and for
        # a stronger reason than a failed one is. It has verdicts and a report, so a question
        # about it would be answerable — but those verdicts are the ones the run itself said
        # it could not settle, and answering questions about them would hand a reader the
        # provisional set through a side door the page deliberately withholds it through.
        #
        # A conversation about one of its open questions is a different thing and is allowed
        # (§6C.7). It is shown only the boundaries that question cites, so there is no held
        # set in the input to leak — and refusing it would mean telling a reader who does not
        # understand the question that they must answer it before they may ask about it,
        # which is §6C.5's adoption tax in its purest form.
        if review.status is ReviewStatus.AWAITING_ANSWERS and about_question is None:
            raise ConversationNotFoundError(
                f"Review {review_id} is still waiting on answers, so its verdicts are not "
                "settled enough to discuss as a whole. Ask about one of its open questions, "
                "or answer them and ask the review that follows."
            )
        settled = {ReviewStatus.SUCCEEDED, ReviewStatus.AWAITING_ANSWERS}
        if review.status not in settled or review.report is None:
            raise ConversationNotFoundError(
                f"Review {review_id} did not succeed, so it has nothing to discuss"
            )
        return review
