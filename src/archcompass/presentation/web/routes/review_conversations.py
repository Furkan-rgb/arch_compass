"""Asking a finished review questions, and reading what it answered.

A conversation is hung off one review and reasons only from what that review already
contains. Two routes append a turn — one plain, one streaming the prose as it is written —
and they are the same flow through the same application call, not two flows: a provider
that cannot stream simply sends no fragments, which is why there is no capability to query
first.
"""

# Pyright cannot see FastAPI's decorator registration as a function reference.
# pyright: reportUnusedFunction=false

from __future__ import annotations

from fastapi import APIRouter
from pydantic import Field

from archcompass.domain.review_conversation import ReviewConversation, ReviewMessage
from archcompass.presentation.web.dependencies import RuntimeDep, SpendsModelBudget
from archcompass.presentation.web.schemas import APIModel, problem_responses
from archcompass.presentation.web.streaming import (
    AnswerProgress,
    NDJSONStreamingResponse,
    answer_progress_lines,
)


class ReviewConversationCreateRequest(APIModel):
    review_id: str = Field(min_length=1)
    title: str | None = Field(default=None, min_length=1)
    #: `Q-n` to talk about one open question rather than the review as a whole (§6C.7).
    #: The only form of conversation a review still waiting on answers will open, and
    #: resolved against that review's own report — a reference it did not ask is refused.
    question_reference: str | None = Field(default=None, pattern=r"^Q-[0-9]+$")


class ReviewQuestionRequest(APIModel):
    question: str = Field(min_length=1, max_length=4000)


def routes() -> APIRouter:
    """Opening a thread on a review, listing threads, and taking a turn in one."""

    router = APIRouter()

    @router.post(
        "/api/review-conversations",
        status_code=201,
        responses=problem_responses(404, 422),
    )
    def create_review_conversation(
        runtime: RuntimeDep,
        request: ReviewConversationCreateRequest,
    ) -> ReviewConversation:
        return runtime.review_conversation_service.create(
            request.review_id,
            title=request.title,
            question_reference=request.question_reference,
        )

    @router.get(
        "/api/review-conversations",
        responses=problem_responses(404, 422),
    )
    def list_review_conversations(runtime: RuntimeDep, review_id: str) -> list[ReviewConversation]:
        return runtime.review_conversation_service.list(review_id)

    @router.get(
        "/api/review-conversations/{conversation_id}",
        responses=problem_responses(404, 422),
    )
    def get_review_conversation(runtime: RuntimeDep, conversation_id: str) -> ReviewConversation:
        return runtime.review_conversation_service.show(conversation_id)

    @router.post(
        "/api/review-conversations/{conversation_id}/messages",
        status_code=201,
        dependencies=[SpendsModelBudget],
        responses=problem_responses(404, 409, 422, 503),
    )
    def ask_review_question(
        runtime: RuntimeDep,
        conversation_id: str,
        request: ReviewQuestionRequest,
    ) -> ReviewMessage:
        return runtime.review_conversation_service.ask(conversation_id, request.question)

    @router.post(
        "/api/review-conversations/{conversation_id}/messages/stream",
        response_class=NDJSONStreamingResponse,
        dependencies=[SpendsModelBudget],
        responses={
            200: {
                "model": AnswerProgress,
                "description": (
                    "The same turn as POST .../messages, as newline-delimited JSON: any "
                    "number of prose fragments, then one answered or failed line."
                ),
            },
            **problem_responses(404, 409, 422, 503),
        },
    )
    def stream_review_question(
        runtime: RuntimeDep,
        conversation_id: str,
        request: ReviewQuestionRequest,
    ) -> NDJSONStreamingResponse:
        """The same turn, with the answer's prose arriving as it is written.

        A second transport for one flow, not a second flow: the same application call appends
        the same message, and this route adds only when its text reaches the reader. A
        provider that cannot stream sends no fragments and the answered line arrives on its
        own, which is why there is no capability to query first.
        """

        return NDJSONStreamingResponse(
            answer_progress_lines(runtime, conversation_id, request.question),
            headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"},
        )

    return router
