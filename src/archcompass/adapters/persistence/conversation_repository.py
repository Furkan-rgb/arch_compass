"""SQLite persistence for pinned report conversations and append-only messages."""

from __future__ import annotations

import sqlite3
from hashlib import sha256

from pydantic import ValidationError

from archcompass.adapters.persistence.database import SQLiteDatabase
from archcompass.domain.atlas import SourceExcerpt
from archcompass.domain.base import canonical_json
from archcompass.domain.consultation import ConsultationRun, ConsultationStatus
from archcompass.domain.conversation import (
    ConversationErrorRecord,
    ConversationEvidenceKind,
    ConversationEvidenceReference,
    ConversationMessage,
    ConversationSummary,
    ConversationSummaryRevision,
    ReportConversation,
)
from archcompass.domain.errors import (
    ConversationNotFoundError,
    ConversationRevisionConflictError,
    ConversationValidationError,
    RunNotFoundError,
)


class SQLiteReportConversationRepository:
    """Own conversation ordering, pin, and audit invariants at the write boundary."""

    def __init__(self, database: SQLiteDatabase) -> None:
        self._database = database

    def create(self, conversation: ReportConversation) -> ReportConversation:
        with self._database.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT run_json FROM consultation_runs WHERE run_id = ?",
                (conversation.consultation_run_id,),
            ).fetchone()
            if row is None:
                raise RunNotFoundError(
                    f"Consultation run {conversation.consultation_run_id} was not found"
                )
            run = ConsultationRun.model_validate_json(row["run_json"])
            self._validate_creation(connection, conversation, run)
            connection.execute(
                """
                INSERT INTO report_conversations(
                    conversation_id, consultation_run_id, case_id, case_revision,
                    atlas_version_id, policy_index_version_id, title, created_at,
                    updated_at, current_summary, summary_through_ordinal,
                    message_count, revision
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                self._values(conversation),
            )
            connection.commit()
        return conversation

    def get(self, conversation_id: str) -> ReportConversation:
        with self._database.connect() as connection:
            row = connection.execute(
                """
                SELECT * FROM report_conversations
                WHERE conversation_id = ?
                """,
                (conversation_id,),
            ).fetchone()
        if row is None:
            raise ConversationNotFoundError(
                f"Report conversation {conversation_id} was not found"
            )
        return self._conversation_from_row(row)

    def list_for_run(self, run_id: str) -> list[ReportConversation]:
        with self._database.connect() as connection:
            rows = connection.execute(
                """
                SELECT * FROM report_conversations
                WHERE consultation_run_id = ?
                ORDER BY updated_at DESC, conversation_id
                """,
                (run_id,),
            ).fetchall()
        return [self._conversation_from_row(row) for row in rows]

    def append_message(
        self,
        message: ConversationMessage,
        *,
        expected_revision: int,
    ) -> ReportConversation:
        with self._database.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = self._conversation_row(connection, message.conversation_id)
            conversation = self._conversation_from_row(row)
            if conversation.revision != expected_revision:
                raise ConversationRevisionConflictError(
                    f"Conversation revision is {conversation.revision}, "
                    f"not {expected_revision}"
                )
            expected_ordinal = conversation.message_count + 1
            if message.ordinal != expected_ordinal:
                raise ConversationRevisionConflictError(
                    f"Message ordinal must be {expected_ordinal}, not {message.ordinal}"
                )
            if message.retrieved_context is not None:
                self._validate_message_audit(connection, conversation, message)
            connection.execute(
                """
                INSERT INTO report_conversation_messages(
                    message_id, conversation_id, ordinal, role, created_at, message_json
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    message.message_id,
                    message.conversation_id,
                    message.ordinal,
                    message.role.value,
                    message.created_at.isoformat(),
                    message.model_dump_json(),
                ),
            )
            cursor = connection.execute(
                """
                UPDATE report_conversations
                SET updated_at = ?, message_count = ?, revision = revision + 1
                WHERE conversation_id = ? AND revision = ?
                """,
                (
                    message.created_at.isoformat(),
                    expected_ordinal,
                    message.conversation_id,
                    expected_revision,
                ),
            )
            if cursor.rowcount != 1:
                raise ConversationRevisionConflictError(
                    "Conversation changed while appending a message"
                )
            connection.commit()
        return self.get(message.conversation_id)

    def history(self, conversation_id: str) -> list[ConversationMessage]:
        self.get(conversation_id)
        with self._database.connect() as connection:
            rows = connection.execute(
                """
                SELECT message_json
                FROM report_conversation_messages
                WHERE conversation_id = ?
                ORDER BY ordinal
                """,
                (conversation_id,),
            ).fetchall()
        return self._messages(rows)

    def recent_messages(
        self,
        conversation_id: str,
        *,
        limit: int = 8,
    ) -> list[ConversationMessage]:
        self._bounded_limit(limit, maximum=8, name="recent-message")
        self.get(conversation_id)
        with self._database.connect() as connection:
            rows = connection.execute(
                """
                SELECT message_json
                FROM report_conversation_messages
                WHERE conversation_id = ?
                ORDER BY ordinal DESC
                LIMIT ?
                """,
                (conversation_id, limit),
            ).fetchall()
        return list(reversed(self._messages(rows)))

    def message_batch(
        self,
        conversation_id: str,
        *,
        after_ordinal: int,
        limit: int,
    ) -> list[ConversationMessage]:
        if after_ordinal < 0:
            raise ConversationValidationError(
                "Message-batch starting ordinal must be non-negative"
            )
        self._bounded_limit(limit, maximum=12, name="message-batch")
        self.get(conversation_id)
        with self._database.connect() as connection:
            rows = connection.execute(
                """
                SELECT message_json
                FROM report_conversation_messages
                WHERE conversation_id = ? AND ordinal > ?
                ORDER BY ordinal
                LIMIT ?
                """,
                (conversation_id, after_ordinal, limit),
            ).fetchall()
        return self._messages(rows)

    def recent_evidence_references(
        self,
        conversation_id: str,
        *,
        limit: int = 96,
    ) -> list[ConversationEvidenceReference]:
        self._bounded_limit(limit, maximum=96, name="evidence-reference")
        self.get(conversation_id)
        with self._database.connect() as connection:
            rows = connection.execute(
                """
                SELECT message_json
                FROM report_conversation_messages
                WHERE conversation_id = ? AND role = 'assistant'
                ORDER BY ordinal DESC
                LIMIT ?
                """,
                (conversation_id, limit),
            ).fetchall()
        references: list[ConversationEvidenceReference] = []
        seen: set[str] = set()
        for message in self._messages(rows):
            if message.retrieved_context is None:
                continue
            for reference in message.retrieved_context.evidence_references:
                if reference.evidence_id in seen:
                    continue
                references.append(reference)
                seen.add(reference.evidence_id)
                if len(references) == limit:
                    return references
        return references

    def summary_history(
        self,
        conversation_id: str,
    ) -> list[ConversationSummaryRevision]:
        self.get(conversation_id)
        with self._database.connect() as connection:
            rows = connection.execute(
                """
                SELECT summary_json
                FROM report_conversation_summaries
                WHERE conversation_id = ?
                ORDER BY summary_revision
                """,
                (conversation_id,),
            ).fetchall()
        return [
            ConversationSummaryRevision.model_validate_json(row["summary_json"])
            for row in rows
        ]

    def latest_summary(
        self,
        conversation_id: str,
    ) -> ConversationSummaryRevision | None:
        self.get(conversation_id)
        with self._database.connect() as connection:
            row = connection.execute(
                """
                SELECT summary_json
                FROM report_conversation_summaries
                WHERE conversation_id = ?
                ORDER BY summary_revision DESC
                LIMIT 1
                """,
                (conversation_id,),
            ).fetchone()
        return (
            None
            if row is None
            else ConversationSummaryRevision.model_validate_json(row["summary_json"])
        )

    def update_summary(
        self,
        summary: ConversationSummaryRevision,
        *,
        expected_revision: int,
    ) -> ReportConversation:
        with self._database.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = self._conversation_row(connection, summary.conversation_id)
            conversation = self._conversation_from_row(row)
            if conversation.revision != expected_revision:
                raise ConversationRevisionConflictError(
                    f"Conversation revision is {conversation.revision}, "
                    f"not {expected_revision}"
                )
            latest = connection.execute(
                """
                SELECT summary_revision, through_ordinal
                FROM report_conversation_summaries
                WHERE conversation_id = ?
                ORDER BY summary_revision DESC
                LIMIT 1
                """,
                (summary.conversation_id,),
            ).fetchone()
            expected_summary_revision = (
                1 if latest is None else int(latest["summary_revision"]) + 1
            )
            prior_through = (
                0 if latest is None else int(latest["through_ordinal"])
            )
            if summary.summary_revision != expected_summary_revision:
                raise ConversationRevisionConflictError(
                    "Summary revision must be "
                    f"{expected_summary_revision}, not {summary.summary_revision}"
                )
            if summary.through_ordinal <= prior_through:
                raise ConversationValidationError(
                    "Summary coverage must advance monotonically"
                )
            if summary.through_ordinal > conversation.message_count:
                raise ConversationValidationError(
                    "Conversation summary cannot extend past message history"
                )
            source_ordinals = [
                ordinal
                for item in (
                    *summary.summary.user_corrections,
                    *summary.summary.hypotheticals,
                    *summary.summary.unresolved_questions,
                )
                for ordinal in item.source_ordinals
            ]
            if any(ordinal > summary.through_ordinal for ordinal in source_ordinals):
                raise ConversationValidationError(
                    "Summary items cannot cite messages beyond covered history"
                )
            connection.execute(
                """
                INSERT INTO report_conversation_summaries(
                    conversation_id, summary_revision, through_ordinal,
                    created_at, summary_json
                ) VALUES (?, ?, ?, ?, ?)
                """,
                (
                    summary.conversation_id,
                    summary.summary_revision,
                    summary.through_ordinal,
                    summary.created_at.isoformat(),
                    summary.model_dump_json(),
                ),
            )
            cursor = connection.execute(
                """
                UPDATE report_conversations
                SET current_summary = ?, summary_through_ordinal = ?,
                    updated_at = ?, revision = revision + 1
                WHERE conversation_id = ? AND revision = ?
                """,
                (
                    summary.summary.model_dump_json(),
                    summary.through_ordinal,
                    summary.created_at.isoformat(),
                    summary.conversation_id,
                    expected_revision,
                ),
            )
            if cursor.rowcount != 1:
                raise ConversationRevisionConflictError(
                    "Conversation changed while updating its summary"
                )
            connection.commit()
        return self.get(summary.conversation_id)

    def record_error(self, error: ConversationErrorRecord) -> None:
        with self._database.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            self._conversation_row(connection, error.conversation_id)
            message = connection.execute(
                """
                SELECT role
                FROM report_conversation_messages
                WHERE message_id = ? AND conversation_id = ?
                """,
                (error.user_message_id, error.conversation_id),
            ).fetchone()
            if message is None or message["role"] != "user":
                raise ConversationValidationError(
                    "Conversation errors must reference a user message "
                    "from the same conversation"
                )
            connection.execute(
                """
                INSERT INTO report_conversation_errors(
                    error_id, conversation_id, user_message_id, user_message_role,
                    stage, created_at, error_json
                ) VALUES (?, ?, ?, 'user', ?, ?, ?)
                """,
                (
                    error.error_id,
                    error.conversation_id,
                    error.user_message_id,
                    error.stage,
                    error.created_at.isoformat(),
                    error.model_dump_json(),
                ),
            )
            connection.commit()

    def errors(self, conversation_id: str) -> list[ConversationErrorRecord]:
        self.get(conversation_id)
        with self._database.connect() as connection:
            rows = connection.execute(
                """
                SELECT error_json
                FROM report_conversation_errors
                WHERE conversation_id = ?
                ORDER BY created_at, error_id
                """,
                (conversation_id,),
            ).fetchall()
        return [
            ConversationErrorRecord.model_validate_json(row["error_json"])
            for row in rows
        ]

    @staticmethod
    def _messages(rows: list[sqlite3.Row]) -> list[ConversationMessage]:
        return [
            ConversationMessage.model_validate_json(row["message_json"])
            for row in rows
        ]

    @staticmethod
    def _conversation_from_row(row: sqlite3.Row) -> ReportConversation:
        data = dict(row)
        current_summary = data.get("current_summary")
        if current_summary:
            try:
                data["current_summary"] = ConversationSummary.model_validate_json(
                    current_summary
                )
            except ValidationError:
                data["current_summary"] = ConversationSummary(
                    narrative=str(current_summary)
                )
        return ReportConversation.model_validate(data)

    @staticmethod
    def _conversation_row(
        connection: sqlite3.Connection,
        conversation_id: str,
    ) -> sqlite3.Row:
        row = connection.execute(
            """
            SELECT * FROM report_conversations
            WHERE conversation_id = ?
            """,
            (conversation_id,),
        ).fetchone()
        if row is None:
            raise ConversationNotFoundError(
                f"Report conversation {conversation_id} was not found"
            )
        return row

    @staticmethod
    def _validate_creation(
        connection: sqlite3.Connection,
        conversation: ReportConversation,
        run: ConsultationRun,
    ) -> None:
        if (
            run.status is not ConsultationStatus.SUCCEEDED
            or run.report is None
            or run.final_validation_errors
        ):
            raise ConversationValidationError(
                "A report conversation requires a successful run with a validated report"
            )
        expected_pins = (
            run.run_id,
            run.case_id,
            run.input_case_revision,
            run.atlas_version_id,
            run.policy_index_version_id,
        )
        actual_pins = (
            conversation.consultation_run_id,
            conversation.case_id,
            conversation.case_revision,
            conversation.atlas_version_id,
            conversation.policy_index_version_id,
        )
        if actual_pins != expected_pins:
            raise ConversationValidationError(
                "Conversation pins must exactly match its consultation run"
            )
        if (
            conversation.message_count != 0
            or conversation.revision != 0
            or conversation.current_summary is not None
            or conversation.summary_through_ordinal != 0
        ):
            raise ConversationValidationError(
                "A new conversation must have empty history and summary state"
            )
        case_row = connection.execute(
            """
            SELECT 1 FROM case_revisions
            WHERE case_id = ? AND revision = ?
            """,
            (run.case_id, run.input_case_revision),
        ).fetchone()
        if case_row is None:
            raise ConversationValidationError(
                "The run's exact input case revision is unavailable"
            )
        if run.atlas_version_id is not None:
            atlas_row = connection.execute(
                "SELECT 1 FROM atlas_versions WHERE version_id = ?",
                (run.atlas_version_id,),
            ).fetchone()
            if atlas_row is None:
                raise ConversationValidationError(
                    "The run's exact Atlas version is unavailable"
                )
        if run.policy_index_version_id is not None:
            policy_row = connection.execute(
                "SELECT 1 FROM policy_index_versions WHERE version_id = ?",
                (run.policy_index_version_id,),
            ).fetchone()
            if policy_row is None:
                raise ConversationValidationError(
                    "The run's exact policy-index version is unavailable"
                )

    @staticmethod
    def _validate_message_audit(
        connection: sqlite3.Connection,
        conversation: ReportConversation,
        message: ConversationMessage,
    ) -> None:
        record = message.retrieved_context
        if record is None:
            return
        if (
            record.consultation_run_id,
            record.case_id,
            record.case_revision,
            record.atlas_version_id,
            record.policy_index_version_id,
        ) != (
            conversation.consultation_run_id,
            conversation.case_id,
            conversation.case_revision,
            conversation.atlas_version_id,
            conversation.policy_index_version_id,
        ):
            raise ConversationValidationError(
                "Assistant retrieval pins must exactly match the conversation"
            )
        latest = connection.execute(
            """
            SELECT summary_revision
            FROM report_conversation_summaries
            WHERE conversation_id = ?
            ORDER BY summary_revision DESC
            LIMIT 1
            """,
            (conversation.conversation_id,),
        ).fetchone()
        latest_revision = None if latest is None else int(latest["summary_revision"])
        if record.summary_revision != latest_revision:
            raise ConversationValidationError(
                "Assistant retrieval must identify the exact current summary revision"
            )
        if any(
            ordinal > conversation.message_count
            for ordinal in record.recent_message_ordinals
        ):
            raise ConversationValidationError(
                "Assistant retrieval references messages outside current history"
            )
        run_row = connection.execute(
            "SELECT run_json FROM consultation_runs WHERE run_id = ?",
            (conversation.consultation_run_id,),
        ).fetchone()
        if run_row is None:
            raise RunNotFoundError(
                f"Consultation run {conversation.consultation_run_id} was not found"
            )
        run = ConsultationRun.model_validate_json(run_row["run_json"])
        expected_finding_ids = (
            [finding.finding_id for finding in run.report.findings]
            if run.report is not None
            else []
        )
        if record.supplied_finding_ids != expected_finding_ids:
            raise ConversationValidationError(
                "Assistant finding inventory must contain every ordered pinned-report digest"
            )
        detailed_finding_ids = [
            reference.artifact_id
            for reference in record.evidence_references
            if reference.kind is ConversationEvidenceKind.FINDING
        ]
        if not set(detailed_finding_ids) <= set(expected_finding_ids):
            raise ConversationValidationError(
                "Assistant detailed findings must belong to the pinned report"
            )
        expected_inventories = (
            (
                record.supplied_report_claim_ids,
                ConversationEvidenceKind.REPORT_CLAIM,
                "report-claim",
            ),
            (
                record.supplied_policy_ids,
                ConversationEvidenceKind.POLICY,
                "policy",
            ),
        )
        for supplied, kind, name in expected_inventories:
            expected = [
                reference.artifact_id
                for reference in record.evidence_references
                if reference.kind is kind
            ]
            if supplied != expected:
                raise ConversationValidationError(
                    f"Assistant {name} inventory must match supplied evidence exactly"
                )
        reference_by_id = {
            reference.evidence_id: reference
            for reference in record.evidence_references
        }
        for snapshot in record.excerpt_snapshots:
            reference = reference_by_id.get(snapshot.evidence_id)
            if (
                reference is None
                or reference.kind is not ConversationEvidenceKind.SOURCE_EXCERPT
                or reference.scope.value != "additional_conversation"
                or reference.node_id is None
                or reference.location != snapshot.location
            ):
                raise ConversationValidationError(
                    "Only exact additional-conversation excerpts may be snapshotted"
                )
            excerpt = SourceExcerpt(
                node_id=reference.node_id,
                location=snapshot.location,
                text=snapshot.text,
            )
            content_hash = sha256(
                canonical_json(excerpt).encode("utf-8")
            ).hexdigest()
            if content_hash != reference.content_hash:
                raise ConversationValidationError(
                    "Excerpt snapshot content does not match its exact evidence reference"
                )

    @staticmethod
    def _bounded_limit(limit: int, *, maximum: int, name: str) -> None:
        if not 1 <= limit <= maximum:
            raise ConversationValidationError(
                f"{name} limit must be between 1 and {maximum}"
            )

    @staticmethod
    def _values(conversation: ReportConversation) -> tuple[object, ...]:
        return (
            conversation.conversation_id,
            conversation.consultation_run_id,
            conversation.case_id,
            conversation.case_revision,
            conversation.atlas_version_id,
            conversation.policy_index_version_id,
            conversation.title,
            conversation.created_at.isoformat(),
            conversation.updated_at.isoformat(),
            (
                conversation.current_summary.model_dump_json()
                if conversation.current_summary is not None
                else None
            ),
            conversation.summary_through_ordinal,
            conversation.message_count,
            conversation.revision,
        )
