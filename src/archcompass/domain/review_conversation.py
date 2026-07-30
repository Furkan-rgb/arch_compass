"""Follow-up questions about one immutable boundary review.

Deliberately not the V1.2 report conversation. That machinery exists because a
consultation's evidence does not fit in one request: it plans retrieval actions, applies
cumulative budgets, resolves finding references and validates all of it, across some 3,800
lines. A review is different in kind — the whole thing serialises to about 25,000
characters, roughly five per cent of the input budget — so there is nothing to retrieve
and no budget to spend.

This is the same reasoning that removed policy retrieval from the judgement stage (§6A).
When the evidence fits, a retrieval layer is indirection in front of one concrete thing.

Grounding follows §12.0. Boundaries are presented in the order the review stored them and
the answer returns one flag per boundary in that order, so the model never writes a `BR-`
reference that ArchCompass then has to trust.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import Field, model_validator

from archcompass.domain.base import DomainModel, new_id, utc_now

#: A question longer than this is a document, not a question, and the limit exists so an
#: oversized input fails at the boundary with a clear message rather than deep inside a
#: prompt-budget check.
MAX_QUESTION_CHARACTERS = 4000


class ReviewAnswer(DomainModel):
    """One answer, and which reviewed boundaries it rests on."""

    answer: str = Field(min_length=1)
    #: `BR-nnn` references, resolved by the application from positional flags. Never
    #: parsed out of model text.
    supporting_references: list[str] = Field(default_factory=list[str])
    #: A phrasing the reader could adopt as their answer to the open question under
    #: discussion, and empty everywhere else. Only the question-discussion stage has a field
    #: for it in its reply schema, so a conversation about a finished review structurally
    #: cannot produce one — the same way `summarise_review` cannot ask a question (§6C.6).
    #:
    #: Nothing is done with it. It is offered beside a button the reader presses, and what
    #: it fills is the answer box, editable, still requiring the whole preview-and-save walk
    #: before any of it reaches the case. §6C.4 is explicit that this is allowed: the
    #: substance of the answer is the user's, including where their whole contribution is
    #: confirming a phrasing that was suggested to them.
    suggested_answer: str = ""

    @property
    def grounded(self) -> bool:
        """Whether the answer rests on anything in the review.

        Derived rather than asked. The model already said which boundaries support the
        answer; asking it a second time whether it was grounded would be asking it to
        grade its own work in a field the application can compute.
        """

        return bool(self.supporting_references)


class ReviewMessage(DomainModel):
    """One question and its answer, appended in order."""

    message_id: str = Field(default_factory=lambda: new_id("rmsg"))
    ordinal: int = Field(ge=1)
    question: str = Field(min_length=1, max_length=MAX_QUESTION_CHARACTERS)
    answer: ReviewAnswer | None = None
    #: Present instead of an answer when the turn failed. Both are never set.
    failure: str = ""
    asked_at: datetime = Field(default_factory=utc_now)

    @model_validator(mode="after")
    def one_outcome(self) -> ReviewMessage:
        if (self.answer is None) == (not self.failure):
            raise ValueError("A review message must carry exactly one of an answer or a failure")
        return self


class ReviewConversation(DomainModel):
    """A conversation pinned to one review, and through it to one case revision.

    Optionally pinned one level finer, to a single open question that review asked. That
    narrower pin is what makes a conversation possible at all while the review is still
    waiting on answers: the reader is being asked something and may not know what it means,
    and telling them to answer it before they may discuss it is the tax elicitation exists
    to remove (§6C.5). What the narrower pin buys is that the discussion is shown only the
    boundaries that question cites — so the withheld verdicts stay withheld, which is the
    reason a review-wide conversation is still refused at that status.
    """

    schema_version: Literal[1] = 1
    conversation_id: str = Field(default_factory=lambda: new_id("rconv"))
    review_id: str = Field(min_length=1)
    case_id: str = Field(min_length=1)
    case_revision: int = Field(ge=1)
    title: str = Field(min_length=1)
    #: `Q-n` where this conversation is about one open question, absent where it is about
    #: the review as a whole. Assigned by the application from the review's own report; a
    #: reference no question in that report carries is refused rather than stored.
    question_reference: str | None = Field(default=None, pattern=r"^Q-[0-9]+$")
    messages: list[ReviewMessage] = Field(default_factory=list[ReviewMessage])
    created_at: datetime = Field(default_factory=utc_now)

    @model_validator(mode="after")
    def messages_are_consecutive(self) -> ReviewConversation:
        expected = list(range(1, len(self.messages) + 1))
        if [item.ordinal for item in self.messages] != expected:
            raise ValueError("Review conversation messages must be numbered consecutively from 1")
        return self

    @property
    def next_ordinal(self) -> int:
        return len(self.messages) + 1
