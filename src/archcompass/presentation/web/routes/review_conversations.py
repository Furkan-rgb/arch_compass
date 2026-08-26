"""Grounded follow-up conversations over immutable clean-break reviews."""

# pyright: reportUnusedFunction=false

from __future__ import annotations

from fastapi import APIRouter, Response
from pydantic import Field

from archcompass.presentation.web.dependencies import RuntimeDep, SpendsModelBudget
from archcompass.presentation.web.routes.reviews import (
    RecordedInvestigationResponse,
    investigation_response,
)
from archcompass.presentation.web.schemas import APIModel, problem_responses
from archcompass.reasoning.ports import ReviewConversation


class ReviewConversationCreateRequest(APIModel):
    review_id: str = Field(min_length=1)
    #: The clarification question this thread is about. Empty opens a thread about the
    #: review as a whole, which is what the Ask surface does.
    question_id: str = Field(default="", max_length=200)


class ReviewQuestionRequest(APIModel):
    question: str = Field(min_length=1, max_length=4000)


class ConversationAnswerResponse(APIModel):
    text: str
    supporting_candidate_ids: list[str]
    investigation: RecordedInvestigationResponse | None
    #: Wording offered for the reader's own answer box, on a thread about a clarification
    #: question. Empty everywhere else, and empty here too whenever the agent had nothing to
    #: propose — which is the ordinary case. Never submitted by anything but a person.
    suggested_answer: str = ""
    #: Which model wrote this answer. What the round stamps on an accepted draft, so the
    #: case records who wrote the words rather than only that somebody did.
    model_identity: str = ""


class ConversationMessageResponse(APIModel):
    question: str
    answer: ConversationAnswerResponse
    asked_at: str


class ReviewConversationResponse(APIModel):
    id: str
    review_id: str
    messages: list[ConversationMessageResponse]
    question_id: str = ""

    @classmethod
    def from_application(
        cls, conversation: ReviewConversation
    ) -> ReviewConversationResponse:
        return cls(
            id=conversation.id,
            review_id=conversation.review_id,
            question_id=conversation.question_id,
            messages=[
                ConversationMessageResponse(
                    question=item.question,
                    answer=ConversationAnswerResponse(
                        text=item.answer.text,
                        supporting_candidate_ids=list(
                            item.answer.supporting_candidate_ids
                        ),
                        investigation=investigation_response(item.answer.investigation),
                        suggested_answer=item.answer.suggested_answer,
                        model_identity=item.answer.model_identity,
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
            runtime.review_conversation_service.create(
                request.review_id, request.question_id
            )
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

    return router
