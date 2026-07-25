"""Application service for persistent, evidence-grounded report conversations."""

from __future__ import annotations

import re
from contextlib import suppress
from hashlib import sha256
from typing import Literal

from archcompass.application.conversation_context import ConversationContextBuilder
from archcompass.application.conversation_rendering import ConversationRenderer
from archcompass.application.conversation_retrieval import ConversationEvidenceRetriever
from archcompass.application.conversation_validation import (
    validate_conversation_answer,
    validate_conversation_summary,
)
from archcompass.configuration import ConversationConfig
from archcompass.domain import budgets
from archcompass.domain.base import canonical_json
from archcompass.domain.consultation import (
    ArchitecturalFinding,
    Claim,
    ConsultationRun,
    ConsultationStatus,
)
from archcompass.domain.conversation import (
    CompareFindingsAction,
    ConversationAnswer,
    ConversationErrorRecord,
    ConversationEvidenceKind,
    ConversationEvidenceScope,
    ConversationExcerptSnapshot,
    ConversationMessage,
    ConversationMessageView,
    ConversationRetrievalAction,
    ConversationRetrievalRecord,
    ConversationRetrievalResult,
    ConversationRole,
    ConversationSummary,
    ConversationSummaryItem,
    ConversationSummaryRevision,
    GetDependencyNeighbourhoodAction,
    GetFindingAction,
    GetPoliciesAction,
    GetSourceExcerptAction,
    ListFindingsAction,
    ReportConversation,
    ReportQuestionPlan,
    ReportQuestionType,
)
from archcompass.domain.errors import ConversationValidationError
from archcompass.ports.policies import PolicyIndex
from archcompass.ports.reasoning import ReasoningTask, ReportConversationReasoner
from archcompass.ports.repositories import (
    AtlasRepository,
    CaseRepository,
    ConsultationRunRepository,
    ReportConversationRepository,
)

_ConversationStage = Literal[
    "classification",
    "retrieval",
    "answering",
    "validation",
    "persistence",
]

#: Matches ConversationRetrievalRecord.fact_warnings; the audit stays bounded.
_MAX_FACT_WARNINGS = 16

#: Durable excerpt-snapshot row caps (per snapshot and per turn). These bound stored
#: rows, not model context: with the evidence budget derived from the model window a
#: long-line excerpt can legitimately carry more text than a row may keep, so the
#: durable copy is clipped with an audited note while reasoning still receives the
#: full excerpt.
_SNAPSHOT_CHARACTERS = budgets.MAX_SNAPSHOT_CHARACTERS
_SNAPSHOT_TOTAL_CHARACTERS = budgets.MAX_SNAPSHOT_CHARACTERS


def _bounded_snapshot_text(text: str, *, remaining: int) -> tuple[str | None, bool]:
    """Fit one durable snapshot copy inside the row and turn budgets.

    Returns the bounded text and whether it was clipped; None when no meaningful
    copy fits this turn.
    """

    limit = min(_SNAPSHOT_CHARACTERS, remaining)
    if limit <= 0:
        return None, False
    if len(text) <= limit:
        return text, False
    clipped = text[: limit - 1].rstrip()
    if not clipped:
        return None, False
    return clipped + "…", True


class ReportConversationService:
    def __init__(
        self,
        *,
        runs: ConsultationRunRepository,
        cases: CaseRepository,
        conversations: ReportConversationRepository,
        atlases: AtlasRepository,
        policies: PolicyIndex,
        reasoning: ReportConversationReasoner,
        retrieval: ConversationEvidenceRetriever,
        context_builder: ConversationContextBuilder,
        renderer: ConversationRenderer,
        config: ConversationConfig,
    ) -> None:
        self._runs = runs
        self._cases = cases
        self._conversations = conversations
        self._atlases = atlases
        self._policies = policies
        self._reasoning = reasoning
        self._retrieval = retrieval
        self._context_builder = context_builder
        self._renderer = renderer
        self._config = config

    def create(self, run_id: str, *, title: str | None = None) -> ReportConversation:
        run = self._runs.get(run_id)
        if (
            run.status is not ConsultationStatus.SUCCEEDED
            or run.report is None
            or run.final_validation_errors
        ):
            raise ConversationValidationError(
                "A report conversation requires a successful run with a validated report"
            )
        revision = self._cases.get(run.case_id, run.input_case_revision)
        if run.atlas_version_id is not None:
            self._atlases.get(run.atlas_version_id)
        if run.policy_index_version_id is not None:
            self._policies.list_policies(run.policy_index_version_id)
        conversation = ReportConversation(
            consultation_run_id=run.run_id,
            case_id=run.case_id,
            case_revision=run.input_case_revision,
            atlas_version_id=run.atlas_version_id,
            policy_index_version_id=run.policy_index_version_id,
            title=(
                title.strip()
                if title is not None and title.strip()
                else f"{revision.snapshot.title} — Report conversation"
            ),
        )
        # The repository repeats all run and pin checks inside its write transaction.
        return self._conversations.create(conversation)

    def list(self, run_id: str) -> list[ReportConversation]:
        self._runs.get(run_id)
        return self._conversations.list_for_run(run_id)

    def show(self, conversation_id: str) -> ReportConversation:
        return self._conversations.get(conversation_id)

    def history(self, conversation_id: str) -> list[ConversationMessage]:
        return self._conversations.history(conversation_id)

    def ask(self, conversation_id: str, question: str) -> ConversationMessage:
        normalized = question.strip()
        if not normalized:
            raise ConversationValidationError("A report question must not be blank")
        if len(normalized) > 4000:
            raise ConversationValidationError(
                "A report question must contain at most 4000 characters"
            )

        conversation = self._conversations.get(conversation_id)
        run = self._runs.get(conversation.consultation_run_id)
        self._validate_pins(conversation, run)
        if run.report is None:
            raise ConversationValidationError("The pinned run has no report")
        case = self._cases.get(
            conversation.case_id,
            conversation.case_revision,
        ).snapshot
        atlas = (
            self._atlases.get(conversation.atlas_version_id)
            if conversation.atlas_version_id is not None
            else None
        )
        if conversation.policy_index_version_id is not None:
            self._policies.list_policies(conversation.policy_index_version_id)

        user_message = ConversationMessage(
            conversation_id=conversation_id,
            ordinal=conversation.message_count + 1,
            role=ConversationRole.USER,
            text=normalized,
        )
        after_user = self._conversations.append_message(
            user_message,
            expected_revision=conversation.revision,
        )

        stage: _ConversationStage = "classification"
        prompt_identities = [
            self._reasoning.prompt_identity(ReasoningTask.CLASSIFY_REPORT_QUESTION)
        ]
        plan: ReportQuestionPlan | None = None
        record: ConversationRetrievalRecord | None = None
        attempted_answer: ConversationAnswer | None = None
        context_hash: str | None = None
        try:
            recent_messages = self._conversations.recent_messages(
                conversation_id,
                limit=self._config.recent_message_limit,
            )
            prior_references = self._conversations.recent_evidence_references(
                conversation_id,
                limit=budgets.MAX_PRIOR_EVIDENCE_REFERENCES,
            )
            latest_summary = self._conversations.latest_summary(conversation_id)
            planning_context = self._context_builder.build_planning(
                conversation=after_user,
                run=run,
                case=case,
                question=normalized,
                history=recent_messages,
                prior_evidence_references=prior_references,
            )
            provider_plan = self._reasoning.classify_report_question(planning_context)
            plan, plan_truncations = self._resolve_and_enrich_plan(
                provider_plan,
                question=normalized,
                findings=run.report.findings,
                report_policy_ids=[
                    item.id for item in run.report.policy_evidence
                ],
            )

            stage = "retrieval"
            previous_node_ids = {
                reference.node_id
                for reference in prior_references
                if reference.kind is ConversationEvidenceKind.ATLAS_NODE
                and reference.node_id is not None
            }
            results = self._retrieval.execute(
                run=run,
                plan=plan,
                previous_node_ids=previous_node_ids,
            )
            context = self._context_builder.build(
                conversation=after_user,
                run=run,
                case=case,
                question=normalized,
                plan=plan,
                history=recent_messages,
                retrieval_results=results,
                atlas=atlas,
            )
            serialized_context = canonical_json(context)
            context_hash = sha256(serialized_context.encode("utf-8")).hexdigest()
            record = self._retrieval_record(
                run=run,
                plan=plan,
                context=context,
                results=results,
                summary_revision=(
                    latest_summary.summary_revision
                    if latest_summary is not None
                    else None
                ),
                plan_truncations=plan_truncations,
                context_hash=context_hash,
            )

            stage = "answering"
            prompt_identities.append(
                self._reasoning.prompt_identity(ReasoningTask.ANSWER_REPORT_QUESTION)
            )
            attempted_answer = self._reasoning.answer_report_question(context)

            stage = "validation"
            atlas_nodes = (
                {item.atlas_id: item for item in atlas.nodes}
                if atlas is not None
                else {}
            )
            original_registry = self._retrieval.original_evidence_registry(run)
            validation = validate_conversation_answer(
                attempted_answer,
                context=context,
                atlas_nodes=atlas_nodes,
                original_evidence_registry=original_registry,
            )
            errors = validation.errors
            if errors:
                prompt_identities.append(
                    self._reasoning.prompt_identity(ReasoningTask.REPAIR_CONVERSATION_ANSWER)
                )
                attempted_answer = self._reasoning.repair_conversation_answer(
                    attempted_answer,
                    errors,
                    {item.finding_id for item in context.finding_digests},
                    {item.claim_id for item in context.retrieved_claims},
                    {item.evidence_id for item in context.evidence_references},
                    {item.policy.id for item in context.retrieved_policies},
                )
                validation = validate_conversation_answer(
                    attempted_answer,
                    context=context,
                    atlas_nodes=atlas_nodes,
                    original_evidence_registry=original_registry,
                )
                errors = validation.errors
            if errors:
                raise ConversationValidationError(
                    "Conversation answer evidence validation failed after one repair: "
                    + "; ".join(errors)
                )

            stage = "persistence"
            if validation.warnings:
                kept = validation.warnings[: _MAX_FACT_WARNINGS]
                if len(validation.warnings) > len(kept):
                    omitted = len(validation.warnings) - len(kept) + 1
                    kept = [
                        *kept[:-1],
                        f"{omitted} further observations were omitted from this audit.",
                    ]
                record = record.model_copy(update={"fact_warnings": kept})
            assistant = ConversationMessage(
                conversation_id=conversation_id,
                ordinal=after_user.message_count + 1,
                role=ConversationRole.ASSISTANT,
                text=self._renderer.answer(attempted_answer, context),
                question_type=",".join(
                    item.value for item in plan.question_types
                ),
                retrieved_context=record,
                answer=attempted_answer,
                model_identity=self._reasoning.model_identity,
                prompt_identities=prompt_identities,
            )
            after_answer = self._conversations.append_message(
                assistant,
                expected_revision=after_user.revision,
            )
        except Exception as error:
            failure = ConversationErrorRecord(
                conversation_id=conversation_id,
                user_message_id=user_message.message_id,
                stage=stage,
                errors=[str(error)],
                model_identity=self._reasoning.model_identity,
                prompt_identities=prompt_identities,
                question_plan=plan,
                retrieval_record=record,
                attempted_answer=attempted_answer,
                context_hash=context_hash,
            )
            with suppress(Exception):
                self._conversations.record_error(failure)
            raise

        self._summarize_after_commit(
            after_answer,
            run=run,
            user_message_id=user_message.message_id,
        )
        return assistant

    def export(self, conversation_id: str, *, format: str) -> str:
        conversation = self._conversations.get(conversation_id)
        messages = self._conversations.history(conversation_id)
        if format == "markdown":
            return self._renderer.export_markdown(conversation, messages)
        if format == "json":
            return self._renderer.export_json(conversation, messages)
        raise ConversationValidationError(
            "Conversation export format must be markdown or json"
        )

    def _summarize_after_commit(
        self,
        conversation: ReportConversation,
        *,
        run: ConsultationRun,
        user_message_id: str,
    ) -> None:
        prompt_identity = self._reasoning.prompt_identity(
            ReasoningTask.SUMMARIZE_REPORT_CONVERSATION
        )
        try:
            self._maybe_summarize(
                conversation,
                run=run,
                prompt_identity=prompt_identity,
            )
        except Exception as error:
            with suppress(Exception):
                self._conversations.record_error(
                    ConversationErrorRecord(
                        conversation_id=conversation.conversation_id,
                        user_message_id=user_message_id,
                        stage="summarization",
                        errors=[str(error)],
                        model_identity=self._reasoning.model_identity,
                        prompt_identities=[prompt_identity],
                    )
                )

    def _maybe_summarize(
        self,
        conversation: ReportConversation,
        *,
        run: ConsultationRun,
        prompt_identity: str,
    ) -> ReportConversation:
        latest = self._conversations.latest_summary(conversation.conversation_id)
        required = (
            budgets.SUMMARIZE_EVERY_MESSAGES
            if latest is not None
            else budgets.SUMMARIZE_AFTER_MESSAGES
        )
        through_ordinal = latest.through_ordinal if latest is not None else 0
        if conversation.message_count - through_ordinal < required:
            return conversation
        batch = self._conversations.message_batch(
            conversation.conversation_id,
            after_ordinal=through_ordinal,
            limit=required,
        )
        if len(batch) != required:
            raise ConversationValidationError(
                "The fixed conversation summary batch is incomplete"
            )
        views = [self._message_view(item) for item in batch]
        summary = self._reasoning.summarize_report_conversation(
            latest.summary if latest is not None else None,
            views,
        )

        current = latest.summary if latest is not None else None
        current_items = self._summary_items(current)
        batch_references = [
            reference
            for message in batch
            if message.retrieved_context is not None
            for reference in message.retrieved_context.evidence_references
        ]
        allowed_evidence_ids = {
            *self._retrieval.original_evidence_ids(run),
            *(item.evidence_id for item in batch_references),
            *(
                current.discussed_evidence_ids
                if current is not None
                else []
            ),
            *(
                evidence_id
                for item in current_items
                for evidence_id in item.evidence_ids
            ),
        }
        allowed_source_ordinals = {
            *(item.ordinal for item in batch),
            *(ordinal for item in current_items for ordinal in item.source_ordinals),
        }
        user_source_ordinals = {
            *(
                item.ordinal
                for item in batch
                if item.role is ConversationRole.USER
            ),
            *(ordinal for item in current_items for ordinal in item.source_ordinals),
        }
        errors = validate_conversation_summary(
            summary,
            allowed_finding_ids={
                item.finding_id
                for item in (run.report.findings if run.report is not None else [])
            },
            allowed_claim_ids={
                item.claim_id for item in self._report_claims(run)
            },
            allowed_evidence_ids=allowed_evidence_ids,
            allowed_policy_ids={
                item.policy.id
                for packet in run.focused_packets
                for item in packet.policies
            },
            allowed_source_ordinals=allowed_source_ordinals,
            user_source_ordinals=user_source_ordinals,
            max_characters=self._config.max_summary_characters,
        )
        if errors:
            raise ConversationValidationError(
                "Conversation summary validation failed: " + "; ".join(errors)
            )
        return self._conversations.update_summary(
            ConversationSummaryRevision(
                conversation_id=conversation.conversation_id,
                summary_revision=(
                    latest.summary_revision + 1 if latest is not None else 1
                ),
                through_ordinal=batch[-1].ordinal,
                summary=summary,
                model_identity=self._reasoning.model_identity,
                prompt_identity=prompt_identity,
            ),
            expected_revision=conversation.revision,
        )

    def _resolve_and_enrich_plan(
        self,
        plan: ReportQuestionPlan,
        *,
        question: str,
        findings: list[ArchitecturalFinding],
        report_policy_ids: list[str],
    ) -> tuple[ReportQuestionPlan, list[str]]:
        """Ground the classifier's plan in the pinned report.

        Intent is the classifier's: question types and retrieval actions come from the
        plan and are validated against closed allowlists downstream. The service adds
        what it can do deterministically - resolving explicit finding references
        (canonical IDs, exact titles) and projecting the selected findings' own policy
        and node evidence into the plan. It never second-guesses phrasing: the English
        keyword tables this method once carried turned ordinary wording into hard
        failures, which is the classifier's ambiguity to handle, not the service's.
        """

        normalized = " ".join(question.casefold().split())
        known_ids = {item.finding_id for item in findings}
        unknown_plan_ids = [
            item for item in plan.finding_ids if item not in known_ids
        ]
        resolved = list(
            dict.fromkeys(
                [
                    *self._resolve_finding_references(normalized, findings=findings),
                    *(item for item in plan.finding_ids if item in known_ids),
                ]
            )
        )[: self._config.max_findings]
        question_types = list(dict.fromkeys(plan.question_types))
        comparison = ReportQuestionType.COMPARE_FINDINGS in question_types
        detailed_question = bool(
            {
                ReportQuestionType.FINDING_DETAILS,
                ReportQuestionType.COMPARE_FINDINGS,
                ReportQuestionType.EVIDENCE_TRACE,
                ReportQuestionType.SOURCE_EXPLANATION,
            }
            & set(question_types)
        )

        selected = [
            finding for finding in findings if finding.finding_id in set(resolved)
        ]
        required_actions: list[ConversationRetrievalAction] = []
        if comparison and len(resolved) >= 2:
            required_actions.append(
                CompareFindingsAction(
                    kind="compare_findings",
                    finding_ids=resolved,
                )
            )
        elif detailed_question:
            required_actions.extend(
                GetFindingAction(kind="get_finding", finding_id=finding_id)
                for finding_id in resolved
            )

        allowed_policy_ids = {
            *report_policy_ids,
            *(
                policy_id
                for finding in selected
                for policy_id in finding.policy_ids
            ),
        }
        policy_ids = list(
            dict.fromkeys(
                [
                    *(
                        policy_id
                        for finding in selected
                        for policy_id in finding.policy_ids
                    ),
                    *(
                        policy_id
                        for policy_id in plan.policy_ids
                        if policy_id in allowed_policy_ids
                    ),
                ]
            )
        )[: self._config.max_policies]
        if (
            ReportQuestionType.POLICY_EXPLANATION in question_types
            and not policy_ids
        ):
            policy_ids = report_policy_ids[: self._config.max_policies]
        if (
            ReportQuestionType.POLICY_EXPLANATION in question_types
            and policy_ids
        ):
            required_actions.append(
                GetPoliciesAction(kind="get_policies", policy_ids=policy_ids)
            )

        node_ids = list(
            dict.fromkeys(
                [
                    *(
                        node_id
                        for finding in selected
                        for node_id in finding.atlas_node_ids
                    ),
                    *plan.atlas_node_ids,
                ]
            )
        )[: self._config.max_atlas_nodes]
        if ReportQuestionType.SOURCE_EXPLANATION in question_types:
            required_actions.extend(
                GetSourceExcerptAction(
                    kind="get_source_excerpt",
                    node_id=node_id,
                    max_lines=min(60, self._config.max_excerpt_lines),
                )
                for node_id in node_ids
            )
        if ReportQuestionType.EVIDENCE_TRACE in question_types:
            required_actions.extend(
                GetDependencyNeighbourhoodAction(
                    kind="get_dependency_neighbourhood",
                    node_id=node_id,
                    direction="reverse",
                    depth=self._config.max_neighbourhood_depth,
                    limit=self._config.max_atlas_nodes,
                )
                for node_id in node_ids[:1]
            )

        preserved_actions = [
            action
            for action in plan.retrieval_actions
            if not isinstance(
                action,
                (
                    CompareFindingsAction,
                    GetFindingAction,
                    GetPoliciesAction,
                    GetSourceExcerptAction,
                    ListFindingsAction,
                ),
            )
        ]
        all_actions = self._unique_actions(
            [*required_actions, *preserved_actions]
        )
        truncations: list[str] = []
        if unknown_plan_ids:
            # A hallucinated reference is dropped, not fatal - but the audit must
            # show the classified intent was narrowed.
            truncations.append(
                "The classifier referenced findings absent from the pinned report "
                f"and they were dropped: {sorted(unknown_plan_ids)}."
            )
        if len(all_actions) > self._config.max_actions_per_question:
            truncations.append(
                "Retrieval actions were clamped to the cumulative per-turn ceiling of "
                f"{self._config.max_actions_per_question}."
            )
        bounded_actions = all_actions[: self._config.max_actions_per_question]
        return (
            plan.model_copy(
                update={
                    "question_types": question_types,
                    "finding_ids": resolved,
                    "atlas_node_ids": node_ids,
                    "policy_ids": policy_ids,
                    "retrieval_actions": bounded_actions,
                }
            ),
            truncations,
        )

    @staticmethod
    def _resolve_finding_references(
        normalized: str,
        *,
        findings: list[ArchitecturalFinding],
    ) -> list[str]:
        """Resolve the references a reader stated explicitly.

        Canonical IDs and exact titles are the two forms with a deterministic answer.
        A title shared by several findings resolves to all of them - covering each
        explicitly is honest, guessing one is not. Everything softer (ordinals,
        "the former", comparison phrasing) is interpretation, which belongs to the
        classifier whose output is validated against the pinned report downstream.
        """

        known_ids = {item.finding_id.casefold(): item.finding_id for item in findings}
        resolved = [
            finding_id
            for match in re.finditer(r"\bfind-[0-9]{3}\b", normalized)
            if (finding_id := known_ids.get(match.group(0))) is not None
        ]

        title_groups: dict[str, list[str]] = {}
        for finding in findings:
            title_groups.setdefault(
                " ".join(finding.title.casefold().split()),
                [],
            ).append(finding.finding_id)
        occupied_spans: list[tuple[int, int]] = []
        title_matches: list[tuple[int, list[str]]] = []
        for title, finding_ids in sorted(
            title_groups.items(),
            key=lambda item: len(item[0]),
            reverse=True,
        ):
            match = re.search(
                rf"(?<![a-z0-9]){re.escape(title)}(?![a-z0-9])",
                normalized,
            )
            if match is None or any(
                start <= match.start() and match.end() <= end
                for start, end in occupied_spans
            ):
                continue
            title_matches.append((match.start(), finding_ids))
            occupied_spans.append(match.span())
        resolved.extend(
            finding_id
            for _, finding_ids in sorted(title_matches, key=lambda item: item[0])
            for finding_id in finding_ids
        )
        return list(dict.fromkeys(resolved))

    @staticmethod
    def _unique_actions(
        actions: list[ConversationRetrievalAction],
    ) -> list[ConversationRetrievalAction]:
        unique: dict[str, ConversationRetrievalAction] = {}
        for action in actions:
            unique.setdefault(canonical_json(action), action)
        return list(unique.values())

    @staticmethod
    def _retrieval_record(
        *,
        run: ConsultationRun,
        plan: ReportQuestionPlan,
        context: object,
        results: list[ConversationRetrievalResult],
        summary_revision: int | None,
        plan_truncations: list[str],
        context_hash: str,
    ) -> ConversationRetrievalRecord:
        from archcompass.domain.conversation import ReportConversationContext

        if not isinstance(context, ReportConversationContext):
            raise TypeError("Conversation retrieval records require an answer context")
        references = context.evidence_references
        snapshots: list[ConversationExcerptSnapshot] = []
        snapshot_notes: list[str] = []
        seen_snapshots: set[str] = set()
        source_references = [
            item
            for item in references
            if item.kind is ConversationEvidenceKind.SOURCE_EXCERPT
            and item.scope is ConversationEvidenceScope.ADDITIONAL_CONVERSATION
        ]
        for atlas_evidence in context.retrieved_atlas_evidence:
            for excerpt in atlas_evidence.excerpts:
                reference = next(
                    (
                        item
                        for item in source_references
                        if item.node_id == excerpt.node_id
                        and item.location == excerpt.location
                        and item.content_hash
                        == sha256(
                            canonical_json(excerpt).encode("utf-8")
                        ).hexdigest()
                    ),
                    None,
                )
                if (
                    reference is None
                    or reference.evidence_id in seen_snapshots
                ):
                    continue
                remaining = _SNAPSHOT_TOTAL_CHARACTERS - sum(
                    len(item.text) for item in snapshots
                )
                bounded_text, clipped = _bounded_snapshot_text(
                    excerpt.text, remaining=remaining
                )
                if bounded_text is None:
                    snapshot_notes.append(
                        f"Excerpt snapshot {reference.evidence_id} was not copied: "
                        "the durable snapshot budget for this turn is exhausted. "
                        "The excerpt itself was supplied to reasoning in full."
                    )
                    continue
                if clipped:
                    snapshot_notes.append(
                        f"Excerpt snapshot {reference.evidence_id} was clipped to fit "
                        "the durable row budget; reasoning received the full excerpt."
                    )
                snapshots.append(
                    ConversationExcerptSnapshot(
                        evidence_id=reference.evidence_id,
                        location=excerpt.location,
                        text=bounded_text,
                    )
                )
                seen_snapshots.add(reference.evidence_id)

        truncations = ReportConversationService._bounded_metadata(
            [
                *plan_truncations,
                *(
                    reason
                    for result in results
                    for reason in result.truncation_reasons
                ),
                *snapshot_notes,
            ],
            limit=16,
            marker="Additional retrieval truncation metadata was omitted.",
        )
        unavailable = ReportConversationService._bounded_metadata(
            [
                result.unavailable_reason
                for result in results
                if result.unavailable_reason is not None
            ],
            limit=8,
            marker="Additional evidence-unavailability metadata was omitted.",
        )
        return ConversationRetrievalRecord(
            consultation_run_id=run.run_id,
            case_id=run.case_id,
            case_revision=run.input_case_revision,
            atlas_version_id=run.atlas_version_id,
            policy_index_version_id=run.policy_index_version_id,
            question_plan=plan,
            retrieval_actions=plan.retrieval_actions,
            evidence_references=references,
            supplied_finding_ids=[
                item.finding_id for item in context.finding_digests
            ],
            supplied_report_claim_ids=[
                item.artifact_id
                for item in references
                if item.kind is ConversationEvidenceKind.REPORT_CLAIM
            ],
            supplied_evidence_ids=[
                item.evidence_id for item in references
            ],
            supplied_policy_ids=[
                item.artifact_id
                for item in references
                if item.kind is ConversationEvidenceKind.POLICY
            ],
            summary_revision=summary_revision,
            recent_message_ordinals=[
                item.ordinal for item in context.recent_messages
            ],
            truncations=truncations,
            unavailable_reasons=unavailable,
            excerpt_snapshots=snapshots,
            context_hash=context_hash,
        )

    @staticmethod
    def _bounded_metadata(
        values: list[str],
        *,
        limit: int,
        marker: str,
    ) -> list[str]:
        unique = list(dict.fromkeys(value for value in values if value.strip()))
        if len(unique) <= limit:
            return unique
        return [*unique[: limit - 1], marker]

    @staticmethod
    def _message_view(message: ConversationMessage) -> ConversationMessageView:
        return ConversationMessageView(
            ordinal=message.ordinal,
            role=message.role,
            text=(
                message.text
                if len(message.text) <= 2000
                else message.text[:1999].rstrip() + "…"
            ),
            relevant_finding_ids=(
                message.answer.relevant_finding_ids
                if message.answer is not None
                else []
            ),
            relevant_evidence_ids=(
                message.retrieved_context.supplied_evidence_ids[:48]
                if message.retrieved_context is not None
                else []
            ),
            uncertainty=(
                [item.text for item in message.answer.uncertainty]
                if message.answer is not None
                else []
            ),
        )

    @staticmethod
    def _summary_items(
        summary: ConversationSummary | None,
    ) -> list[ConversationSummaryItem]:
        if summary is None:
            return []
        return [
            *summary.user_corrections,
            *summary.hypotheticals,
            *summary.unresolved_questions,
        ]

    @staticmethod
    def _report_claims(run: ConsultationRun) -> list[Claim]:
        if run.report is None:
            return []
        claims = [
            *run.report.confirmed_context,
            *run.report.assumptions_and_unresolved_questions,
            *run.report.repository_observations,
            *run.report.relevant_policies,
            *run.report.evidence_appendix,
            *(
                claim
                for analysis in run.concern_analyses
                for claim in analysis.findings
            ),
        ]
        unique: dict[str, Claim] = {}
        for claim in claims:
            unique.setdefault(claim.claim_id, claim)
        return list(unique.values())

    @staticmethod
    def _validate_pins(
        conversation: ReportConversation,
        run: ConsultationRun,
    ) -> None:
        if (
            conversation.consultation_run_id != run.run_id
            or conversation.case_id != run.case_id
            or conversation.case_revision != run.input_case_revision
            or conversation.atlas_version_id != run.atlas_version_id
            or conversation.policy_index_version_id != run.policy_index_version_id
        ):
            raise ConversationValidationError(
                "Conversation identity does not match its pinned consultation run"
            )
