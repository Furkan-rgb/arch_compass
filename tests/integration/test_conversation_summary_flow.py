from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from archcompass.adapters.models.deterministic import DeterministicReasoningProvider
from archcompass.adapters.persistence import SQLiteReportConversationRepository
from archcompass.adapters.persistence.database import SQLiteDatabase
from archcompass.application.conversation_context import ConversationContextBuilder
from archcompass.application.conversation_rendering import ConversationRenderer
from archcompass.application.conversation_retrieval import ConversationEvidenceRetriever
from archcompass.application.conversations import ReportConversationService
from archcompass.bootstrap import Runtime
from archcompass.configuration import ReasoningModelConfig
from archcompass.domain.case import ArchitectureCase
from archcompass.domain.consultation import ConsultationRun
from archcompass.domain.conversation import (
    ConversationEvidenceReference,
    ConversationMessage,
    ConversationMessageView,
    ConversationRole,
    ConversationSummary,
    ConversationSummaryItem,
    ConversationSummaryRevision,
)
from archcompass.domain.errors import (
    ConversationRevisionConflictError,
    ConversationValidationError,
)


def _reasoning_model_config() -> ReasoningModelConfig:
    return ReasoningModelConfig(
        provider="fake",
        model="deterministic",
        base_url="http://ollama.test",
        timeout_seconds=1,
    )

def _successful_run(runtime: Runtime) -> ConsultationRun:
    source = yaml.safe_load(
        Path("eval/cases/audiobook-greenfield/case.yaml").read_text(encoding="utf-8")
    )
    revision = runtime.case_service.create(ArchitectureCase.model_validate(source))
    return runtime.workflow.advise(revision.case_id)


def _service(
    runtime: Runtime,
    *,
    reasoning: DeterministicReasoningProvider,
    repository: SQLiteReportConversationRepository | None = None,
) -> tuple[ReportConversationService, SQLiteReportConversationRepository]:
    selected_repository = repository or SQLiteReportConversationRepository(
        runtime.database
    )
    return (
        ReportConversationService(
            runs=runtime.run_repository,
            cases=runtime.case_repository,
            conversations=selected_repository,
            atlases=runtime.atlas_repository,
            policies=runtime.policy_store,
            reasoning=reasoning,
            retrieval=ConversationEvidenceRetriever(
                reasoning=_reasoning_model_config(),
                atlases=runtime.atlas_repository,
                queries=runtime.query_service,
                config=runtime.config.conversation,
            ),
            context_builder=ConversationContextBuilder(
                runtime.config.conversation,
                reasoning=_reasoning_model_config(),
            ),
            renderer=ConversationRenderer(),
            config=runtime.config.conversation,
        ),
        selected_repository,
    )


def _ask_turns(
    service: ReportConversationService,
    conversation_id: str,
    *,
    count: int,
) -> list[ConversationMessage]:
    return [
        service.ask(
            conversation_id,
            f"What are the main findings? Summary audit turn {turn}.",
        )
        for turn in range(1, count + 1)
    ]


class SummaryAuditReasoner(DeterministicReasoningProvider):
    def __init__(self) -> None:
        self.repository: SQLiteReportConversationRepository | None = None
        self.conversation_id: str | None = None
        self.committed_message_counts: list[int] = []
        self.batches: list[list[tuple[int, ConversationRole]]] = []
        self.prior_summaries: list[ConversationSummary | None] = []

    def summarize_report_conversation(
        self,
        current_summary: ConversationSummary | None,
        messages: list[ConversationMessageView],
    ) -> ConversationSummary:
        assert self.repository is not None
        assert self.conversation_id is not None
        persisted = self.repository.get(self.conversation_id)
        self.committed_message_counts.append(persisted.message_count)
        self.batches.append(
            [(message.ordinal, message.role) for message in messages]
        )
        self.prior_summaries.append(current_summary)
        return super().summarize_report_conversation(current_summary, messages)


class InvalidSummaryReasoner(DeterministicReasoningProvider):
    def summarize_report_conversation(
        self,
        current_summary: ConversationSummary | None,
        messages: list[ConversationMessageView],
    ) -> ConversationSummary:
        del current_summary, messages
        return ConversationSummary(
            narrative="This invalid summary introduces FIND-999.",
            discussed_finding_ids=["FIND-999"],
        )


class FailingSummaryReasoner(DeterministicReasoningProvider):
    def summarize_report_conversation(
        self,
        current_summary: ConversationSummary | None,
        messages: list[ConversationMessageView],
    ) -> ConversationSummary:
        del current_summary, messages
        raise RuntimeError("summary provider failed")


class AssistantOrdinalSummaryReasoner(DeterministicReasoningProvider):
    def summarize_report_conversation(
        self,
        current_summary: ConversationSummary | None,
        messages: list[ConversationMessageView],
    ) -> ConversationSummary:
        del current_summary, messages
        return ConversationSummary(
            narrative="A correction was incorrectly attributed to an assistant.",
            user_corrections=[
                ConversationSummaryItem(
                    text="This must cite a user message.",
                    source_ordinals=[2],
                )
            ],
        )


class BoundedReadAuditRepository(SQLiteReportConversationRepository):
    def __init__(self, database: SQLiteDatabase) -> None:
        super().__init__(database)
        self.unbounded_history_reads = 0
        self.unbounded_summary_reads = 0
        self.recent_message_limits: list[int] = []
        self.recent_evidence_limits: list[int] = []
        self.summary_batches: list[tuple[int, int]] = []

    def history(self, conversation_id: str) -> list[ConversationMessage]:
        del conversation_id
        self.unbounded_history_reads += 1
        raise AssertionError("Ordinary turns must not load full message history")

    def summary_history(
        self,
        conversation_id: str,
    ) -> list[ConversationSummaryRevision]:
        del conversation_id
        self.unbounded_summary_reads += 1
        raise AssertionError("Ordinary turns must not load full summary history")

    def recent_messages(
        self,
        conversation_id: str,
        *,
        limit: int = 8,
    ) -> list[ConversationMessage]:
        self.recent_message_limits.append(limit)
        return super().recent_messages(conversation_id, limit=limit)

    def recent_evidence_references(
        self,
        conversation_id: str,
        *,
        limit: int = 96,
    ) -> list[ConversationEvidenceReference]:
        self.recent_evidence_limits.append(limit)
        return super().recent_evidence_references(
            conversation_id,
            limit=limit,
        )

    def message_batch(
        self,
        conversation_id: str,
        *,
        after_ordinal: int,
        limit: int,
    ) -> list[ConversationMessage]:
        self.summary_batches.append((after_ordinal, limit))
        return super().message_batch(
            conversation_id,
            after_ordinal=after_ordinal,
            limit=limit,
        )


def test_summary_runs_after_assistant_commit_in_fixed_twelve_then_eight_batches(
    runtime: Runtime,
) -> None:
    run = _successful_run(runtime)
    reasoner = SummaryAuditReasoner()
    service, repository = _service(runtime, reasoning=reasoner)
    conversation = service.create(run.run_id)
    reasoner.repository = repository
    reasoner.conversation_id = conversation.conversation_id

    _ask_turns(service, conversation.conversation_id, count=10)

    assert reasoner.committed_message_counts == [12, 20]
    assert reasoner.batches == [
        [
            (ordinal, ConversationRole.USER if ordinal % 2 else ConversationRole.ASSISTANT)
            for ordinal in range(1, 13)
        ],
        [
            (ordinal, ConversationRole.USER if ordinal % 2 else ConversationRole.ASSISTANT)
            for ordinal in range(13, 21)
        ],
    ]
    assert reasoner.prior_summaries[0] is None
    assert reasoner.prior_summaries[1] is not None
    assert [
        (summary.summary_revision, summary.through_ordinal)
        for summary in repository.summary_history(conversation.conversation_id)
    ] == [(1, 12), (2, 20)]


def test_invalid_summary_does_not_advance_coverage_or_hide_committed_answer(
    runtime: Runtime,
) -> None:
    run = _successful_run(runtime)
    service, repository = _service(runtime, reasoning=InvalidSummaryReasoner())
    conversation = service.create(run.run_id)

    answers = _ask_turns(service, conversation.conversation_id, count=6)

    history = repository.history(conversation.conversation_id)
    current = repository.get(conversation.conversation_id)
    assert history[-1].message_id == answers[-1].message_id
    assert history[-1].role is ConversationRole.ASSISTANT
    assert current.message_count == 12
    assert current.current_summary is None
    assert current.summary_through_ordinal == 0
    assert repository.latest_summary(conversation.conversation_id) is None
    assert repository.summary_history(conversation.conversation_id) == []
    failures = repository.errors(conversation.conversation_id)
    assert len(failures) == 1
    assert failures[0].stage == "summarization"
    assert failures[0].user_message_id == history[-2].message_id
    assert "unknown finding IDs" in failures[0].errors[0]
    assert failures[0].prompt_identities == ["summarize-report-conversation:v2"]


def test_summary_provider_failure_is_recorded_after_valid_answer_returns(
    runtime: Runtime,
) -> None:
    run = _successful_run(runtime)
    service, repository = _service(runtime, reasoning=FailingSummaryReasoner())
    conversation = service.create(run.run_id)

    answers = _ask_turns(service, conversation.conversation_id, count=6)

    history = repository.history(conversation.conversation_id)
    current = repository.get(conversation.conversation_id)
    assert history[-1].message_id == answers[-1].message_id
    assert current.message_count == 12
    assert current.summary_through_ordinal == 0
    assert repository.latest_summary(conversation.conversation_id) is None
    failures = repository.errors(conversation.conversation_id)
    assert len(failures) == 1
    assert failures[0].stage == "summarization"
    assert failures[0].user_message_id == history[-2].message_id
    assert failures[0].errors == ["summary provider failed"]


def test_summary_state_items_must_cite_user_message_ordinals(
    runtime: Runtime,
) -> None:
    run = _successful_run(runtime)
    service, repository = _service(
        runtime,
        reasoning=AssistantOrdinalSummaryReasoner(),
    )
    conversation = service.create(run.run_id)

    _ask_turns(service, conversation.conversation_id, count=6)

    current = repository.get(conversation.conversation_id)
    assert current.current_summary is None
    assert current.summary_through_ordinal == 0
    failure = repository.errors(conversation.conversation_id)[0]
    assert failure.stage == "summarization"
    assert "must cite user-message ordinals: [2]" in failure.errors[0]


def test_summary_repository_rolls_back_revision_coverage_and_source_failures(
    runtime: Runtime,
) -> None:
    run = _successful_run(runtime)
    repository = SQLiteReportConversationRepository(runtime.database)
    conversation = runtime.conversation_service.create(run.run_id)
    current = conversation
    for ordinal in range(1, 5):
        current = repository.append_message(
            ConversationMessage(
                conversation_id=conversation.conversation_id,
                ordinal=ordinal,
                role=ConversationRole.USER,
                text=f"Question {ordinal}",
            ),
            expected_revision=current.revision,
        )

    first = ConversationSummaryRevision(
        conversation_id=conversation.conversation_id,
        summary_revision=1,
        through_ordinal=2,
        summary=ConversationSummary(narrative="The first two messages."),
        model_identity="fake:deterministic",
        prompt_identity="summarize-report-conversation:v2",
    )
    after_first = repository.update_summary(
        first,
        expected_revision=current.revision,
    )
    failed_updates = [
        (
            first.model_copy(
                update={"summary_revision": 3, "through_ordinal": 3}
            ),
            ConversationRevisionConflictError,
            "must be 2",
        ),
        (
            first.model_copy(
                update={"summary_revision": 2, "through_ordinal": 2}
            ),
            ConversationValidationError,
            "monotonically",
        ),
        (
            first.model_copy(
                update={"summary_revision": 2, "through_ordinal": 5}
            ),
            ConversationValidationError,
            "past message history",
        ),
        (
            ConversationSummaryRevision(
                conversation_id=conversation.conversation_id,
                summary_revision=2,
                through_ordinal=3,
                summary=ConversationSummary(
                    narrative="An invalid source link.",
                    user_corrections=[
                        ConversationSummaryItem(
                            text="This source is outside covered history.",
                            source_ordinals=[4],
                        )
                    ],
                ),
                model_identity="fake:deterministic",
                prompt_identity="summarize-report-conversation:v2",
            ),
            ConversationValidationError,
            "beyond covered history",
        ),
    ]
    for attempted, error_type, message in failed_updates:
        with pytest.raises(error_type, match=message):
            repository.update_summary(
                attempted,
                expected_revision=after_first.revision,
            )
        assert repository.latest_summary(conversation.conversation_id) == first
        assert (
            repository.get(conversation.conversation_id).revision
            == after_first.revision
        )


def test_ordinary_turns_use_only_bounded_history_and_summary_reads(
    runtime: Runtime,
) -> None:
    run = _successful_run(runtime)
    repository = BoundedReadAuditRepository(runtime.database)
    service, _ = _service(
        runtime,
        reasoning=DeterministicReasoningProvider(),
        repository=repository,
    )
    conversation = service.create(run.run_id)

    _ask_turns(service, conversation.conversation_id, count=6)

    assert repository.unbounded_history_reads == 0
    assert repository.unbounded_summary_reads == 0
    assert repository.recent_message_limits == [8] * 6
    assert repository.recent_evidence_limits == [96] * 6
    assert repository.summary_batches == [(0, 12)]
