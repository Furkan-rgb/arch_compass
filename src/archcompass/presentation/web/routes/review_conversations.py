"""Grounded follow-up conversations over immutable clean-break reviews."""

# pyright: reportUnusedFunction=false

from __future__ import annotations

import json
from collections.abc import Iterator

from fastapi import APIRouter, Response
from fastapi.responses import StreamingResponse
from pydantic import Field

from archcompass.ports.review_conversation import ReviewConversation
from archcompass.presentation.web.dependencies import RuntimeDep, SpendsModelBudget
from archcompass.presentation.web.routes.reviews import (
    RecordedInvestigationResponse,
    investigation_response,
)
from archcompass.presentation.web.schemas import APIModel, problem_responses


class ReviewConversationCreateRequest(APIModel):
    review_id: str = Field(min_length=1)


class ReviewQuestionRequest(APIModel):
    question: str = Field(min_length=1, max_length=4000)


class ConversationAnswerResponse(APIModel):
    text: str
    supporting_candidate_ids: list[str]
    investigation: RecordedInvestigationResponse | None


class ConversationMessageResponse(APIModel):
    question: str
    answer: ConversationAnswerResponse
    asked_at: str


class ReviewConversationResponse(APIModel):
    id: str
    review_id: str
    messages: list[ConversationMessageResponse]

    @classmethod
    def from_application(
        cls, conversation: ReviewConversation
    ) -> ReviewConversationResponse:
        return cls(
            id=conversation.id,
            review_id=conversation.review_id,
            messages=[
                ConversationMessageResponse(
                    question=item.question,
                    answer=ConversationAnswerResponse(
                        text=item.answer.text,
                        supporting_candidate_ids=list(
                            item.answer.supporting_candidate_ids
                        ),
                        investigation=investigation_response(item.answer.investigation),
                    ),
                    asked_at=item.asked_at.isoformat(),
                )
                for item in conversation.messages
            ],
        )


def routes() -> APIRouter:
    router = APIRouter()

    @router.post(
        "/api/review-conversations",
        status_code=201,
        responses=problem_responses(404, 422),
    )
    def create_review_conversation(
        runtime: RuntimeDep, request: ReviewConversationCreateRequest
    ) -> ReviewConversationResponse:
        return ReviewConversationResponse.from_application(
            runtime.review_conversation_service.create(request.review_id)
        )

    @router.get("/api/review-conversations", responses=problem_responses(404, 422))
    def list_review_conversations(
        runtime: RuntimeDep, review_id: str
    ) -> list[ReviewConversationResponse]:
        return [
            ReviewConversationResponse.from_application(item)
            for item in runtime.review_conversation_service.list(review_id)
        ]

    @router.get(
        "/api/review-conversations/{conversation_id}",
        responses=problem_responses(404, 422),
    )
    def get_review_conversation(
        runtime: RuntimeDep, conversation_id: str
    ) -> ReviewConversationResponse:
        return ReviewConversationResponse.from_application(
            runtime.review_conversation_service.show(conversation_id)
        )

    @router.delete(
        "/api/review-conversations/{conversation_id}",
        status_code=204,
        responses=problem_responses(404, 422),
    )
    def delete_review_conversation(runtime: RuntimeDep, conversation_id: str) -> Response:
        runtime.review_conversation_service.delete(conversation_id)
        return Response(status_code=204)

    @router.post(
        "/api/review-conversations/{conversation_id}/messages",
        dependencies=[SpendsModelBudget],
        responses=problem_responses(404, 422, 503),
    )
    def ask_review_question(
        runtime: RuntimeDep,
        conversation_id: str,
        request: ReviewQuestionRequest,
    ) -> ReviewConversationResponse:
        return ReviewConversationResponse.from_application(
            runtime.review_conversation_service.ask(conversation_id, request.question)
        )

    @router.post(
        "/api/review-conversations/{conversation_id}/messages/stream",
        response_class=StreamingResponse,
        dependencies=[SpendsModelBudget],
    )
    def stream_review_question(
        runtime: RuntimeDep,
        conversation_id: str,
        request: ReviewQuestionRequest,
    ) -> StreamingResponse:
        def lines() -> Iterator[str]:
            try:
                conversation = runtime.review_conversation_service.ask(
                    conversation_id, request.question
                )
                payload = ReviewConversationResponse.from_application(
                    conversation
                ).model_dump(mode="json")
                yield json.dumps({"event": "answered", "conversation": payload}) + "\n"
            except Exception as error:
                yield json.dumps({"event": "failed", "message": str(error)}) + "\n"

        return StreamingResponse(lines(), media_type="application/x-ndjson")

    return router
