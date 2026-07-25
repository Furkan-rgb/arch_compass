from __future__ import annotations

import shutil
from pathlib import Path

import pytest
import yaml

from archcompass.adapters.models.deterministic import DeterministicReasoningProvider
from archcompass.adapters.persistence import SQLiteReportConversationRepository
from archcompass.application.conversation_context import ConversationContextBuilder
from archcompass.application.conversation_rendering import ConversationRenderer
from archcompass.application.conversation_retrieval import ConversationEvidenceRetriever
from archcompass.application.conversations import ReportConversationService
from archcompass.bootstrap import Runtime
from archcompass.configuration import ConversationConfig
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
    ConversationEvidenceKind,
    ConversationEvidenceScope,
    ConversationMessage,
    ConversationMessageView,
    ConversationRole,
    ConversationSummary,
    FindingDigest,
    ListFindingsAction,
    ReportConversationContext,
    ReportQuestionPlan,
    ReportQuestionType,
)
from archcompass.domain.errors import (
    ConversationRetrievalError,
    ConversationRevisionConflictError,
    ConversationValidationError,
)


def _successful_run(
    runtime: Runtime,
    *,
    brownfield: bool = False,
    repository: Path | None = None,
) -> ConsultationRun:
    case_path = (
        "eval/cases/provider-leakage/case.yaml"
        if brownfield
        else "eval/cases/audiobook-greenfield/case.yaml"
    )
    source = yaml.safe_load(Path(case_path).read_text(encoding="utf-8"))
    revision = runtime.case_service.create(ArchitectureCase.model_validate(source))
    if not brownfield:
        return runtime.workflow.advise(revision.case_id)
    selected_repository = repository or Path(
        "eval/cases/provider-leakage/repository"
    ).resolve()
    atlas = runtime.analyzer.analyze(selected_repository)
    runtime.atlas_repository.save(atlas)
    return runtime.workflow.advise(
        revision.case_id,
        atlas_version_id=atlas.version.version_id,
    )


class InvalidConversationReasoner(DeterministicReasoningProvider):
    repair_calls = 0

    def answer_report_question(
        self,
        context: ReportConversationContext,
    ) -> ConversationAnswer:
        claim = AnswerClaim(
            text="Invented support",
            classification=ClaimClassification.ADVISOR_INFERENCE,
            report_claim_ids=["claim_invented"],
        )
        return ConversationAnswer(
            direct_answer=AnswerStatement(
                text="This answer cites evidence that was never supplied.",
                kind=AnswerStatementKind.DIRECT_ANSWER,
                answer_claim_ids=[claim.claim_id],
            ),
            claims=[claim],
        )

    def repair_conversation_answer(
        self,
        answer: ConversationAnswer,
        errors: list[str],
        allowed_finding_ids: set[str],
        allowed_claim_ids: set[str],
        allowed_evidence_ids: set[str],
        allowed_policy_ids: set[str],
    ) -> ConversationAnswer:
        self.repair_calls += 1
        return answer


class InvalidSummaryReasoner(DeterministicReasoningProvider):
    def summarize_report_conversation(
        self,
        current_summary: ConversationSummary | None,
        messages: list[ConversationMessageView],
    ) -> ConversationSummary:
        del current_summary, messages
        return ConversationSummary(
            narrative="An invalid post-answer summary.",
            discussed_finding_ids=["FIND-999"],
        )


class CapturingConversationReasoner(DeterministicReasoningProvider):
    last_context: ReportConversationContext | None = None

    def answer_report_question(
        self,
        context: ReportConversationContext,
    ) -> ConversationAnswer:
        self.last_context = context
        return super().answer_report_question(context)


def _conversation_service(
    runtime: Runtime,
    *,
    reasoning: DeterministicReasoningProvider,
) -> tuple[ReportConversationService, SQLiteReportConversationRepository]:
    repository = SQLiteReportConversationRepository(runtime.database)
    return (
        ReportConversationService(
            runs=runtime.run_repository,
            cases=runtime.case_repository,
            conversations=repository,
            atlases=runtime.atlas_repository,
            policies=runtime.policy_store,
            reasoning=reasoning,
            retrieval=ConversationEvidenceRetriever(
                atlases=runtime.atlas_repository,
                queries=runtime.query_service,
                config=runtime.config.conversation,
            ),
            context_builder=ConversationContextBuilder(runtime.config.conversation),
            renderer=ConversationRenderer(),
            config=runtime.config.conversation,
        ),
        repository,
    )


def test_conversation_creation_is_gated_and_legacy_table_is_retained(
    runtime: Runtime,
) -> None:
    run = _successful_run(runtime)
    conversation = runtime.conversation_service.create(run.run_id)

    assert conversation.consultation_run_id == run.run_id
    assert conversation.case_revision == run.input_case_revision
    assert conversation.atlas_version_id == run.atlas_version_id
    assert conversation.policy_index_version_id == run.policy_index_version_id
    with runtime.database.connect() as connection:
        table = connection.execute(
            """
            SELECT name FROM sqlite_master
            WHERE type = 'table' AND name = 'report_follow_ups'
            """
        ).fetchone()
    assert table is not None
    with runtime.database.connect() as connection:
        connection.execute(
            """
            INSERT INTO report_follow_ups(
                follow_up_id, run_id, created_at, entry_json
            ) VALUES ('follow_up_retained', ?, '2026-07-24T00:00:00+00:00', '{}')
            """,
            (run.run_id,),
        )
        connection.commit()
    runtime.database.initialize()
    with runtime.database.connect() as connection:
        retained = connection.execute(
            """
            SELECT entry_json FROM report_follow_ups
            WHERE follow_up_id = 'follow_up_retained'
            """
        ).fetchone()
    assert retained is not None

    failed = ConsultationRun(
        schema_version=3,
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
        runtime.conversation_service.create(failed.run_id)


def test_append_is_ordered_with_compare_and_swap(runtime: Runtime) -> None:
    run = _successful_run(runtime)
    conversation = runtime.conversation_service.create(run.run_id)
    repository = SQLiteReportConversationRepository(runtime.database)
    first = ConversationMessage(
        conversation_id=conversation.conversation_id,
        ordinal=1,
        role=ConversationRole.USER,
        text="First question",
    )
    competing = first.model_copy(
        update={"message_id": "message_competing", "text": "Competing question"}
    )

    updated = repository.append_message(first, expected_revision=0)

    assert updated.revision == 1
    assert [item.ordinal for item in repository.history(conversation.conversation_id)] == [1]
    with pytest.raises(ConversationRevisionConflictError):
        repository.append_message(competing, expected_revision=0)


def test_invalid_answer_is_repaired_once_then_recorded_as_failed(
    runtime: Runtime,
) -> None:
    run = _successful_run(runtime)
    reasoner = InvalidConversationReasoner()
    service, repository = _conversation_service(
        runtime,
        reasoning=reasoner,
    )
    conversation = service.create(run.run_id)

    with pytest.raises(ConversationValidationError, match="after one repair"):
        service.ask(conversation.conversation_id, "What supports the recommendation?")

    history = repository.history(conversation.conversation_id)
    failures = repository.errors(conversation.conversation_id)
    assert [item.role for item in history] == [ConversationRole.USER]
    assert len(failures) == 1
    assert failures[0].stage == "validation"
    assert reasoner.repair_calls == 1
    assert failures[0].prompt_identities[-1].startswith(
        "repair-conversation-answer:"
    )
    failure = failures[0]
    assert failure.question_plan is not None
    assert failure.retrieval_record is not None
    assert failure.attempted_answer is not None
    assert failure.context_hash == failure.retrieval_record.context_hash
    assert failure.context_hash is not None
    assert len(failure.context_hash) == 64


@pytest.mark.evaluation
def test_answers_record_original_and_additional_pinned_atlas_evidence(
    runtime: Runtime,
) -> None:
    run = _successful_run(runtime, brownfield=True)
    assert run.report is not None
    conversation = runtime.conversation_service.create(run.run_id)
    finding_id = run.report.findings[0].finding_id

    original_answer = runtime.conversation_service.ask(
        conversation.conversation_id,
        f"What dependency blast radius evidence supports {finding_id}?",
    )

    assert original_answer.retrieved_context is not None
    original_record = original_answer.retrieved_context
    assert original_record.question_plan.finding_ids == [finding_id]
    original_refs = [
        item
        for item in original_record.evidence_references
        if item.scope is ConversationEvidenceScope.ORIGINAL_RUN
        and item.kind
        in {
            ConversationEvidenceKind.ATLAS_NODE,
            ConversationEvidenceKind.ATLAS_RELATIONSHIP,
            ConversationEvidenceKind.ATLAS_METRIC,
            ConversationEvidenceKind.ATLAS_SIGNAL,
            ConversationEvidenceKind.SOURCE_EXCERPT,
            ConversationEvidenceKind.TEST,
        }
    ]
    assert original_refs
    assert original_record.supplied_finding_ids == [
        item.finding_id for item in run.report.findings
    ]
    assert original_record.supplied_evidence_ids == [
        item.evidence_id for item in original_record.evidence_references
    ]
    assert len(original_record.supplied_evidence_ids) == len(
        set(original_record.supplied_evidence_ids)
    )
    assert original_record.retrieval_actions == (
        original_record.question_plan.retrieval_actions
    )
    assert len(original_record.context_hash) == 64
    assert not hasattr(original_record, "retrieval_results")
    additional_answer = runtime.conversation_service.ask(
        conversation.conversation_id,
        "Search the pinned Atlas for frontend.",
    )
    assert additional_answer.retrieved_context is not None
    record = additional_answer.retrieved_context
    additional_refs = [
        item
        for item in record.evidence_references
        if item.scope is ConversationEvidenceScope.ADDITIONAL_CONVERSATION
    ]
    assert additional_refs
    assert record.consultation_run_id == run.run_id
    assert record.atlas_version_id == run.atlas_version_id
    assert (
        "Additional repository evidence retrieved during conversation"
        in additional_answer.text
    )
    assert original_answer.answer is not None
    assert finding_id in original_answer.answer.relevant_finding_ids

    additional_node = next(
        item
        for item in additional_refs
        if item.kind is ConversationEvidenceKind.ATLAS_NODE
    )
    source_answer = runtime.conversation_service.ask(
        conversation.conversation_id,
        f"Show source code for Atlas node {additional_node.artifact_id}.",
    )
    assert source_answer.retrieved_context is not None
    source_record = source_answer.retrieved_context
    assert source_record.excerpt_snapshots
    source_refs = {
        item.evidence_id: item for item in source_record.evidence_references
    }
    assert all(
        source_refs[item.evidence_id].kind
        is ConversationEvidenceKind.SOURCE_EXCERPT
        and source_refs[item.evidence_id].scope
        is ConversationEvidenceScope.ADDITIONAL_CONVERSATION
        and source_refs[item.evidence_id].location == item.location
        for item in source_record.excerpt_snapshots
    )


@pytest.mark.evaluation
def test_rolling_summary_is_created_and_refreshed(runtime: Runtime) -> None:
    run = _successful_run(runtime)
    conversation = runtime.conversation_service.create(run.run_id)

    for ordinal in range(10):
        runtime.conversation_service.ask(
            conversation.conversation_id,
            f"What are the main findings? Turn {ordinal + 1}.",
        )

    current = runtime.conversation_service.show(conversation.conversation_id)
    assert current.message_count == 20
    assert current.current_summary is not None
    assert len(current.current_summary.narrative) <= 6000
    with runtime.database.connect() as connection:
        revisions = connection.execute(
            """
            SELECT summary_revision, through_ordinal
            FROM report_conversation_summaries
            WHERE conversation_id = ?
            ORDER BY summary_revision
            """,
            (conversation.conversation_id,),
        ).fetchall()
    assert [tuple(item) for item in revisions] == [(1, 12), (2, 20)]


def test_invalid_post_answer_summary_is_recorded_without_losing_answer(
    runtime: Runtime,
) -> None:
    run = _successful_run(runtime)
    service, repository = _conversation_service(
        runtime,
        reasoning=InvalidSummaryReasoner(),
    )
    conversation = service.create(run.run_id)

    answer: ConversationMessage | None = None
    for ordinal in range(6):
        answer = service.ask(
            conversation.conversation_id,
            f"What are the main findings? Summary turn {ordinal + 1}.",
        )

    assert answer is not None
    assert answer.role is ConversationRole.ASSISTANT
    history = repository.history(conversation.conversation_id)
    assert len(history) == 12
    assert history[-1].message_id == answer.message_id
    current = service.show(conversation.conversation_id)
    assert current.current_summary is None
    failures = repository.errors(conversation.conversation_id)
    assert len(failures) == 1
    assert failures[0].stage == "summarization"


def test_later_rebuilds_do_not_change_pins_and_stale_excerpts_are_unavailable(
    runtime: Runtime,
    tmp_path: Path,
) -> None:
    repository = tmp_path.parent / f"{tmp_path.name}-provider-leakage"
    shutil.copytree(
        Path("eval/cases/provider-leakage/repository"),
        repository,
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
    )
    run = _successful_run(runtime, brownfield=True, repository=repository)
    assert run.report is not None
    conversation = runtime.conversation_service.create(run.run_id)
    pinned_atlas = run.atlas_version_id
    pinned_policies = run.policy_index_version_id

    frontend = repository / "frontend.py"
    frontend.write_text(
        frontend.read_text(encoding="utf-8") + "\n# changed after consultation\n",
        encoding="utf-8",
    )
    later_atlas = runtime.analyzer.analyze(repository)
    runtime.atlas_repository.save(later_atlas)
    later_policies = runtime.policy_service.rebuild(repository_root=repository)
    assert later_atlas.version.version_id != pinned_atlas
    assert later_policies.version_id != pinned_policies

    answer = runtime.conversation_service.ask(
        conversation.conversation_id,
        f"Show the source code evidence for {run.report.findings[0].finding_id}.",
    )

    assert answer.retrieved_context is not None
    record = answer.retrieved_context
    assert record.atlas_version_id == pinned_atlas
    assert record.policy_index_version_id == pinned_policies
    assert any(
        action.kind == "get_source_excerpt"
        for action in record.retrieval_actions
    )
    assert record.unavailable_reasons
    assert not record.excerpt_snapshots


def test_retrieval_and_provider_context_are_bounded(
    runtime: Runtime,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run = _successful_run(runtime)
    assert run.report is not None
    retriever = ConversationEvidenceRetriever(
        atlases=runtime.atlas_repository,
        queries=runtime.query_service,
        config=ConversationConfig(max_actions_per_question=1),
    )
    over_budget = ReportQuestionPlan(
        question_types=[ReportQuestionType.LIST_FINDINGS],
        retrieval_actions=[
            ListFindingsAction(kind="list_findings", limit=1),
            ListFindingsAction(kind="list_findings", limit=1),
        ],
        rationale="Exercise the configured action ceiling.",
    )
    with pytest.raises(ConversationRetrievalError, match="retrieval-action limit"):
        retriever.execute(run=run, plan=over_budget)

    reasoner = CapturingConversationReasoner()
    service, repository = _conversation_service(runtime, reasoning=reasoner)

    def reject_unbounded_history(conversation_id: str) -> list[ConversationMessage]:
        raise AssertionError(
            f"Ordinary turn loaded unbounded history for {conversation_id}"
        )

    monkeypatch.setattr(repository, "history", reject_unbounded_history)
    conversation = service.create(run.run_id)
    for ordinal in range(5):
        service.ask(
            conversation.conversation_id,
            f"What are the main findings? Context turn {ordinal + 1}.",
        )

    assert reasoner.last_context is not None
    assert len(reasoner.last_context.recent_messages) == 8
    assert reasoner.last_context.recent_messages[-1].ordinal == 9
    assert reasoner.last_context.finding_digests == [
        FindingDigest.from_finding(item) for item in run.report.findings
    ]
    assert reasoner.last_context.retrieved_findings == []
    pinned_case = reasoner.last_context.pinned_case
    exact_case = runtime.case_repository.get(
        run.case_id,
        run.input_case_revision,
    ).snapshot
    assert pinned_case.functional_requirements == exact_case.functional_requirements
    assert pinned_case.technical_constraints == exact_case.technical_constraints
    assert pinned_case.expected_future_changes == exact_case.expected_future_changes
    assert pinned_case.non_goals == exact_case.non_goals
    assert pinned_case.assumptions == [
        item.text for item in exact_case.assumptions
    ]
    assert not hasattr(reasoner.last_context, "atlas")
    assert not hasattr(reasoner.last_context, "repository_root")
    assert not hasattr(reasoner.last_context, "policy_corpus")


def test_finding_titles_ordinals_and_recent_references_are_resolved(
    runtime: Runtime,
) -> None:
    run = _successful_run(runtime)
    assert run.report is not None
    conversation = runtime.conversation_service.create(run.run_id)
    first, second = run.report.findings[:2]

    comparison = runtime.conversation_service.ask(
        conversation.conversation_id,
        f"Compare {first.title} versus {second.title}.",
    )
    assert comparison.retrieved_context is not None
    assert comparison.retrieved_context.question_plan.finding_ids == [
        first.finding_id,
        second.finding_id,
    ]

    detail = runtime.conversation_service.ask(
        conversation.conversation_id,
        "Why is the 2nd finding important?",
    )
    assert detail.retrieved_context is not None
    assert detail.retrieved_context.question_plan.finding_ids == [second.finding_id]

    recent = runtime.conversation_service.ask(
        conversation.conversation_id,
        "What evidence supports this finding?",
    )
    assert recent.retrieved_context is not None
    assert recent.retrieved_context.question_plan.finding_ids == [second.finding_id]
