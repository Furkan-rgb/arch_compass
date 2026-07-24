from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
import yaml

from archcompass.adapters.persistence import SQLiteReportConversationRepository
from archcompass.adapters.persistence.database import SQLiteDatabase
from archcompass.bootstrap import Runtime
from archcompass.domain.case import ArchitectureCase
from archcompass.domain.consultation import (
    ClaimClassification,
    ConsultationFailureStage,
    ConsultationRun,
    ConsultationStatus,
)
from archcompass.domain.conversation import (
    AnswerClaim,
    AnswerStatement,
    AnswerStatementKind,
    ConversationAnswer,
    ConversationErrorRecord,
    ConversationEvidenceKind,
    ConversationEvidenceReference,
    ConversationEvidenceScope,
    ConversationMessage,
    ConversationRetrievalRecord,
    ConversationRole,
    ConversationSummary,
    ConversationSummaryItem,
    ConversationSummaryRevision,
    ReportConversation,
    ReportQuestionPlan,
    ReportQuestionType,
)
from archcompass.domain.errors import (
    ConversationRevisionConflictError,
    ConversationValidationError,
    RunNotFoundError,
)


def _successful_run(runtime: Runtime) -> ConsultationRun:
    source = yaml.safe_load(
        Path("eval/cases/audiobook-greenfield/case.yaml").read_text(encoding="utf-8")
    )
    revision = runtime.case_service.create(ArchitectureCase.model_validate(source))
    return runtime.workflow.advise(revision.case_id)


def _conversation(run: ConsultationRun, *, title: str = "Persistence audit") -> ReportConversation:
    return ReportConversation(
        consultation_run_id=run.run_id,
        case_id=run.case_id,
        case_revision=run.input_case_revision,
        atlas_version_id=run.atlas_version_id,
        policy_index_version_id=run.policy_index_version_id,
        title=title,
    )


def _user(conversation_id: str, ordinal: int, text: str = "Question") -> ConversationMessage:
    return ConversationMessage(
        conversation_id=conversation_id,
        ordinal=ordinal,
        role=ConversationRole.USER,
        text=text,
    )


def _assistant(
    conversation: ReportConversation,
    run: ConsultationRun,
    ordinal: int,
) -> ConversationMessage:
    assert run.report is not None
    reference = ConversationEvidenceReference(
        evidence_id="evidence_report_context",
        kind=ConversationEvidenceKind.REPORT_CONTEXT,
        artifact_id="report_context:pinned",
        scope=ConversationEvidenceScope.ORIGINAL_RUN,
        content_hash="a" * 64,
    )
    plan = ReportQuestionPlan(
        question_types=[ReportQuestionType.GENERAL_REPORT_QUESTION],
        retrieval_actions=[],
        rationale="Use the pinned report context.",
    )
    record = ConversationRetrievalRecord(
        consultation_run_id=conversation.consultation_run_id,
        case_id=conversation.case_id,
        case_revision=conversation.case_revision,
        atlas_version_id=conversation.atlas_version_id,
        policy_index_version_id=conversation.policy_index_version_id,
        question_plan=plan,
        retrieval_actions=[],
        evidence_references=[reference],
        supplied_finding_ids=[
            finding.finding_id for finding in run.report.findings
        ],
        supplied_evidence_ids=[reference.evidence_id],
        recent_message_ordinals=[ordinal - 1],
        context_hash="b" * 64,
    )
    claim = AnswerClaim(
        claim_id="answer_claim_test",
        text="The answer is grounded in the pinned report context.",
        classification=ClaimClassification.ADVISOR_INFERENCE,
        evidence_ids=[reference.evidence_id],
    )
    answer = ConversationAnswer(
        direct_answer=AnswerStatement(
            text="This is the grounded answer.",
            kind=AnswerStatementKind.DIRECT_ANSWER,
            answer_claim_ids=[claim.claim_id],
        ),
        claims=[claim],
    )
    return ConversationMessage(
        conversation_id=conversation.conversation_id,
        ordinal=ordinal,
        role=ConversationRole.ASSISTANT,
        text=answer.direct_answer.text,
        question_type=ReportQuestionType.GENERAL_REPORT_QUESTION.value,
        retrieved_context=record,
        answer=answer,
        model_identity="fake:deterministic",
        prompt_identities=["answer-report-question:v2"],
    )


def test_create_validates_exact_successful_run_pins_and_preserves_legacy_data(
    runtime: Runtime,
) -> None:
    run = _successful_run(runtime)
    repository = SQLiteReportConversationRepository(runtime.database)

    created = repository.create(_conversation(run))

    assert created.consultation_run_id == run.run_id
    wrong_pin = _conversation(run).model_copy(
        update={"case_revision": run.input_case_revision + 1}
    )
    with pytest.raises(ConversationValidationError, match="exactly match"):
        repository.create(wrong_pin)
    with pytest.raises(RunNotFoundError):
        repository.create(
            ReportConversation(
                consultation_run_id="run_missing",
                case_id=run.case_id,
                case_revision=run.input_case_revision,
                title="Missing run",
            )
        )

    failed = ConsultationRun(
        status=ConsultationStatus.FAILED,
        case_id=run.case_id,
        input_case_revision=run.result_case_revision or 2,
        reasoning_model="fake:test",
        embedding_model="fake:test",
        config_hash="cfg-test",
        failure_stage=ConsultationFailureStage.SYNTHESIS,
        sanitized_errors=["The test consultation failed."],
    )
    runtime.run_repository.save(failed)
    with pytest.raises(ConversationValidationError, match="successful run"):
        repository.create(_conversation(failed, title="Failed run"))

    with runtime.database.connect() as connection:
        connection.execute(
            """
            INSERT INTO report_follow_ups(follow_up_id, run_id, created_at, entry_json)
            VALUES ('follow_up_retained', ?, '2026-07-24T00:00:00+00:00', '{}')
            """,
            (run.run_id,),
        )
        connection.commit()
    runtime.database.initialize()
    with runtime.database.connect() as connection:
        retained = connection.execute(
            "SELECT entry_json FROM report_follow_ups WHERE follow_up_id = ?",
            ("follow_up_retained",),
        ).fetchone()
    assert retained is not None


def test_message_reads_are_bounded_and_error_links_require_same_user_message(
    runtime: Runtime,
) -> None:
    run = _successful_run(runtime)
    repository = SQLiteReportConversationRepository(runtime.database)
    first = repository.create(_conversation(run, title="First"))
    second = repository.create(_conversation(run, title="Second"))

    after_user = repository.append_message(
        _user(first.conversation_id, 1),
        expected_revision=0,
    )
    assistant = _assistant(first, run, 2)
    assert assistant.retrieved_context is not None
    wrong_record = assistant.retrieved_context.model_copy(
        update={"case_id": "case_wrong"}
    )
    wrong_pins = assistant.model_copy(update={"retrieved_context": wrong_record})
    with pytest.raises(ConversationValidationError, match="exactly match"):
        repository.append_message(
            wrong_pins,
            expected_revision=after_user.revision,
        )
    after_assistant = repository.append_message(
        assistant,
        expected_revision=after_user.revision,
    )
    other_user = _user(second.conversation_id, 1, "Other conversation")
    repository.append_message(other_user, expected_revision=0)

    assert [item.ordinal for item in repository.recent_messages(
        first.conversation_id, limit=2
    )] == [1, 2]
    assert [item.ordinal for item in repository.message_batch(
        first.conversation_id, after_ordinal=0, limit=1
    )] == [1]
    assert [
        item.evidence_id
        for item in repository.recent_evidence_references(
            first.conversation_id,
            limit=8,
        )
    ] == ["evidence_report_context"]
    with pytest.raises(ConversationValidationError, match="between 1 and 8"):
        repository.recent_messages(first.conversation_id, limit=9)

    with runtime.database.connect() as connection:
        message_json = connection.execute(
            """
            SELECT message_json FROM report_conversation_messages
            WHERE message_id = ?
            """,
            (assistant.message_id,),
        ).fetchone()["message_json"]
    assert '"retrieval_results"' not in message_json
    assert '"atlas_results"' not in message_json

    valid_error = ConversationErrorRecord(
        conversation_id=first.conversation_id,
        user_message_id=_user(first.conversation_id, 1).message_id,
        stage="retrieval",
        errors=["Evidence was unavailable."],
    )
    # Reuse the persisted user's actual identity.
    valid_error = valid_error.model_copy(
        update={
            "user_message_id": repository.history(first.conversation_id)[0].message_id
        }
    )
    repository.record_error(valid_error)
    assert len(repository.errors(first.conversation_id)) == 1

    wrong_conversation = valid_error.model_copy(
        update={
            "error_id": "conversation_error_wrong_conversation",
            "user_message_id": other_user.message_id,
        }
    )
    with pytest.raises(ConversationValidationError, match="same conversation"):
        repository.record_error(wrong_conversation)
    assistant_link = valid_error.model_copy(
        update={
            "error_id": "conversation_error_assistant",
            "user_message_id": assistant.message_id,
        }
    )
    with pytest.raises(ConversationValidationError, match="user message"):
        repository.record_error(assistant_link)
    assert after_assistant.message_count == 2


def test_summary_updates_are_sequential_monotonic_and_transactional(
    runtime: Runtime,
) -> None:
    run = _successful_run(runtime)
    repository = SQLiteReportConversationRepository(runtime.database)
    conversation = repository.create(_conversation(run))
    current = conversation
    for ordinal in range(1, 4):
        current = repository.append_message(
            _user(conversation.conversation_id, ordinal, f"Question {ordinal}"),
            expected_revision=current.revision,
        )

    first = ConversationSummaryRevision(
        conversation_id=conversation.conversation_id,
        summary_revision=1,
        through_ordinal=2,
        summary=ConversationSummary(
            narrative="The first two questions asked for report clarification.",
            unresolved_questions=[
                ConversationSummaryItem(
                    text="Clarify the recommendation.",
                    source_ordinals=[1],
                )
            ],
        ),
        model_identity="fake:deterministic",
        prompt_identity="summarize-report-conversation:v2",
    )
    after_first = repository.update_summary(
        first,
        expected_revision=current.revision,
    )
    assert after_first.summary_through_ordinal == 2
    assert repository.latest_summary(conversation.conversation_id) == first

    skipped = first.model_copy(
        update={"summary_revision": 3, "through_ordinal": 3}
    )
    with pytest.raises(ConversationRevisionConflictError, match="must be 2"):
        repository.update_summary(skipped, expected_revision=after_first.revision)
    regressed = first.model_copy(
        update={"summary_revision": 2, "through_ordinal": 1}
    )
    with pytest.raises(ConversationValidationError, match="monotonically"):
        repository.update_summary(regressed, expected_revision=after_first.revision)
    beyond_history = first.model_copy(
        update={"summary_revision": 2, "through_ordinal": 4}
    )
    with pytest.raises(ConversationValidationError, match="past message history"):
        repository.update_summary(
            beyond_history,
            expected_revision=after_first.revision,
        )

    assert repository.latest_summary(conversation.conversation_id) == first
    assert repository.get(conversation.conversation_id).revision == after_first.revision


def test_one_migration_rolls_back_all_earlier_statements_on_failure() -> None:
    connection = sqlite3.connect(":memory:")
    connection.execute(
        """
        CREATE TABLE schema_migrations (
            version INTEGER PRIMARY KEY,
            applied_at TEXT NOT NULL
        )
        """
    )
    connection.commit()

    with pytest.raises(sqlite3.OperationalError):
        SQLiteDatabase._apply_migration(  # pyright: ignore[reportPrivateUsage]
            connection,
            version=99,
            script=(
                "CREATE TABLE migration_should_rollback(value TEXT);\n"
                "INSERT INTO missing_table(value) VALUES ('boom');\n"
            ),
        )

    table = connection.execute(
        """
        SELECT name FROM sqlite_master
        WHERE type = 'table' AND name = 'migration_should_rollback'
        """
    ).fetchone()
    marker = connection.execute(
        "SELECT version FROM schema_migrations WHERE version = 99"
    ).fetchone()
    connection.close()
    assert table is None
    assert marker is None
