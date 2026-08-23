"""Typed application boundary for grounded review conversation."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from archcompass.domain import RecordedInvestigation, Review


@dataclass(frozen=True, slots=True)
class ConversationAnswer:
    text: str
    supporting_candidate_ids: tuple[str, ...] = ()
    #: What the answer looked up in the repository before it was written, where anything
    #: was. Carried inline rather than by identity, unlike a finding's: a conversation
    #: holds a handful of messages that are read together, not a docket of forty rows
    #: that are scanned.
    investigation: RecordedInvestigation | None = None


@dataclass(frozen=True, slots=True)
class ConversationMessage:
    question: str
    answer: ConversationAnswer
    asked_at: datetime


@dataclass(frozen=True, slots=True)
class ReviewConversation:
    id: str
    review_id: str
    messages: tuple[ConversationMessage, ...] = ()


class ConversationStore(Protocol):
    def record(self, conversation: ReviewConversation) -> ReviewConversation: ...

    def get(self, conversation_id: str) -> ReviewConversation: ...

    def list_for_review(self, review_id: str) -> tuple[ReviewConversation, ...]: ...

    def delete(self, conversation_id: str) -> None: ...


class ReviewAnswerer(Protocol):
    def answer(
        self,
        review: Review,
        history: tuple[ConversationMessage, ...],
        question: str,
    ) -> ConversationAnswer: ...
