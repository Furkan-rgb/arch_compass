from __future__ import annotations

import pytest
from pydantic import ValidationError

from archcompass.domain.consultation import ClaimClassification
from archcompass.domain.conversation import (
    AnswerClaim,
    AnswerStatement,
    AnswerStatementKind,
    ConversationAnswer,
    ConversationEvidenceKind,
    ConversationEvidenceReference,
    ConversationEvidenceScope,
    ConversationMessage,
    ConversationRetrievalRecord,
    ConversationRole,
    ConversationSummary,
    ConversationSummaryItem,
    PinnedCaseSummary,
    ReportQuestionPlan,
    ReportQuestionType,
)


def _plan() -> ReportQuestionPlan:
    return ReportQuestionPlan(
        question_types=[ReportQuestionType.FINDING_DETAILS],
        finding_ids=["FIND-001"],
        retrieval_actions=[],
        rationale="Explain the selected canonical finding.",
    )


def _record() -> ConversationRetrievalRecord:
    reference = ConversationEvidenceReference(
        evidence_id="finding:FIND-001",
        kind=ConversationEvidenceKind.FINDING,
        artifact_id="FIND-001",
        scope=ConversationEvidenceScope.ORIGINAL_RUN,
        content_hash="a" * 64,
    )
    return ConversationRetrievalRecord(
        consultation_run_id="run-1",
        case_id="case-1",
        case_revision=1,
        question_plan=_plan(),
        retrieval_actions=[],
        evidence_references=[reference],
        supplied_finding_ids=["FIND-001"],
        supplied_evidence_ids=[reference.evidence_id],
        recent_message_ordinals=[1],
        context_hash="b" * 64,
    )


def _answer() -> ConversationAnswer:
    claim = AnswerClaim(
        claim_id="answer-claim-1",
        text="The finding is important because its recorded consequence is material.",
        classification=ClaimClassification.ADVISOR_INFERENCE,
        finding_ids=["FIND-001"],
    )
    return ConversationAnswer(
        direct_answer=AnswerStatement(
            text=claim.text,
            kind=AnswerStatementKind.DIRECT_ANSWER,
            answer_claim_ids=[claim.claim_id],
            finding_ids=["FIND-001"],
        ),
        claims=[claim],
        relevant_finding_ids=["FIND-001"],
    )


def test_answer_claim_and_rendered_statement_require_explicit_support() -> None:
    with pytest.raises(ValidationError, match="exact supplied support"):
        AnswerClaim(
            text="Production latency is exactly five milliseconds.",
            classification=ClaimClassification.REPOSITORY_OBSERVATION,
        )

    with pytest.raises(ValidationError, match="explicit support"):
        AnswerStatement(
            text="Production latency is exactly five milliseconds.",
            kind=AnswerStatementKind.DIRECT_ANSWER,
        )


def test_durable_retrieval_record_contains_references_not_rich_results() -> None:
    record = _record()

    assert "retrieval_results" not in ConversationRetrievalRecord.model_fields
    assert record.supplied_evidence_ids == ["finding:FIND-001"]
    assert len(record.context_hash) == 64

    with pytest.raises(ValidationError, match="exactly match ordered"):
        record.model_copy(update={"supplied_evidence_ids": []}).model_dump()
        ConversationRetrievalRecord.model_validate(
            {
                **record.model_dump(mode="json"),
                "supplied_evidence_ids": [],
            }
        )


def test_assistant_message_requires_complete_audit_fields() -> None:
    answer = _answer()
    with pytest.raises(ValidationError, match="retrieval record"):
        ConversationMessage(
            conversation_id="conversation-1",
            ordinal=2,
            role=ConversationRole.ASSISTANT,
            text=answer.direct_answer.text,
            answer=answer,
            model_identity="fake:test",
            prompt_identities=["answer-report-question:v1"],
            question_type=ReportQuestionType.FINDING_DETAILS,
        )

    message = ConversationMessage(
        conversation_id="conversation-1",
        ordinal=2,
        role=ConversationRole.ASSISTANT,
        text=answer.direct_answer.text,
        answer=answer,
        retrieved_context=_record(),
        model_identity="fake:test",
        prompt_identities=["answer-report-question:v1"],
        question_type=ReportQuestionType.FINDING_DETAILS,
    )
    assert message.answer == answer


def test_typed_summary_links_user_state_to_source_ordinals() -> None:
    summary = ConversationSummary(
        narrative="The user is examining the first finding.",
        discussed_finding_ids=["FIND-001"],
        user_corrections=[
            ConversationSummaryItem(
                text="Hosted providers are mandatory in the hypothetical.",
                source_ordinals=[3],
                finding_ids=["FIND-001"],
            )
        ],
    )
    assert summary.user_corrections[0].source_ordinals == [3]

    with pytest.raises(ValidationError, match="unique and ordered"):
        ConversationSummaryItem(
            text="An invalid duplicate source link.",
            source_ordinals=[3, 3],
        )

    with pytest.raises(ValidationError, match="must be positive"):
        ConversationSummaryItem(
            text="An invalid non-message source link.",
            source_ordinals=[0],
        )


def test_pinned_case_summary_does_not_silently_truncate_the_input_revision() -> None:
    requirements = [f"Requirement {ordinal}" for ordinal in range(1, 31)]
    workflows = [f"Workflow {ordinal}" for ordinal in range(1, 31)]
    facts = [f"Fact {ordinal}" for ordinal in range(1, 31)]

    summary = PinnedCaseSummary(
        case_id="case-1",
        revision=7,
        title="Exact pinned case",
        problem_statement="Preserve every item from the pinned input revision.",
        desired_outcome="Conversation planning receives the exact case lists.",
        actors_and_workflows=workflows,
        functional_requirements=requirements,
        confirmed_facts=facts,
    )

    assert summary.actors_and_workflows == workflows
    assert summary.functional_requirements == requirements
    assert summary.confirmed_facts == facts
