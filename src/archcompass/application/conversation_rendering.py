"""Deterministic readable rendering for validated conversation answers and exports."""

from __future__ import annotations

import json
from collections.abc import Iterable

from archcompass.domain.conversation import (
    ConversationAnswer,
    ConversationEvidenceKind,
    ConversationEvidenceReference,
    ConversationEvidenceScope,
    ConversationMessage,
    ConversationRole,
    ReportConversation,
    ReportConversationContext,
)


class ConversationRenderer:
    def answer(
        self,
        answer: ConversationAnswer,
        context: ReportConversationContext,
    ) -> str:
        """Render only validated statements and application-owned evidence metadata."""
        sections = [answer.direct_answer.text]
        if answer.supporting_points:
            sections.append(
                "Supporting points:\n"
                + "\n".join(f"- {item.text}" for item in answer.supporting_points)
            )
        if answer.relevant_finding_ids:
            sections.append(
                "Relevant findings: " + ", ".join(answer.relevant_finding_ids)
            )
        cited_evidence_ids = {
            evidence_id
            for claim in answer.claims
            for evidence_id in claim.evidence_ids
        }
        repository_kinds = {
            ConversationEvidenceKind.ATLAS_NODE,
            ConversationEvidenceKind.ATLAS_RELATIONSHIP,
            ConversationEvidenceKind.ATLAS_METRIC,
            ConversationEvidenceKind.ATLAS_SIGNAL,
            ConversationEvidenceKind.SOURCE_EXCERPT,
            ConversationEvidenceKind.TEST,
            ConversationEvidenceKind.METRIC_DEFINITION,
        }
        original_evidence = self._evidence_lines(
            reference
            for reference in context.evidence_references
            if reference.evidence_id in cited_evidence_ids
            and reference.kind in repository_kinds
            and reference.scope is ConversationEvidenceScope.ORIGINAL_RUN
        )
        if original_evidence:
            sections.append(
                "Repository evidence retained by the original run:\n"
                + "\n".join(original_evidence)
            )
        additional_evidence = self._evidence_lines(
            reference
            for reference in context.evidence_references
            if reference.evidence_id in cited_evidence_ids
            and reference.kind in repository_kinds
            and reference.scope
            is ConversationEvidenceScope.ADDITIONAL_CONVERSATION
        )
        if additional_evidence:
            sections.append(
                "Additional repository evidence retrieved during conversation\n"
                + "\n".join(additional_evidence)
            )
        policy_ids = list(
            dict.fromkeys(
                policy_id for claim in answer.claims for policy_id in claim.policy_ids
            )
        )
        if policy_ids:
            sections.append("Policies: " + ", ".join(policy_ids))
        if answer.uncertainty:
            sections.append(
                "Uncertainty:\n"
                + "\n".join(f"- {item.text}" for item in answer.uncertainty)
            )
        if answer.suggested_follow_up_questions:
            sections.append(
                "Suggested follow-ups:\n"
                + "\n".join(
                    f"- {item}" for item in answer.suggested_follow_up_questions
                )
            )
        return "\n\n".join(sections).rstrip() + "\n"

    @staticmethod
    def _evidence_lines(
        references: Iterable[ConversationEvidenceReference],
    ) -> list[str]:
        lines: dict[str, None] = {}
        for item in references:
            identity = f"{item.kind.value}:{item.artifact_id}"
            if item.node_id is not None and item.node_id != item.artifact_id:
                identity += f" (node {item.node_id})"
            line = f"- {identity}"
            if item.location is not None:
                line += (
                    f" — {item.location.path}:{item.location.start_line}-"
                    f"{item.location.end_line}"
                )
            lines.setdefault(line, None)
        return list(lines)

    def export_markdown(
        self,
        conversation: ReportConversation,
        messages: list[ConversationMessage],
    ) -> str:
        parts = [
            f"# {conversation.title}",
            f"Conversation ID: `{conversation.conversation_id}`  \n"
            f"Consultation run: `{conversation.consultation_run_id}`  \n"
            f"Case revision: `{conversation.case_id}@{conversation.case_revision}`  \n"
            f"Atlas version: `{conversation.atlas_version_id or 'none'}`  \n"
            f"Policy index: `{conversation.policy_index_version_id or 'none'}`",
        ]
        for message in messages:
            label = "User" if message.role is ConversationRole.USER else "ArchCompass"
            parts.append(f"## {message.ordinal}. {label}\n\n{message.text}")
        return "\n\n".join(parts).rstrip() + "\n"

    def export_json(
        self,
        conversation: ReportConversation,
        messages: list[ConversationMessage],
    ) -> str:
        return json.dumps(
            {
                "conversation": conversation.model_dump(mode="json"),
                "messages": [item.model_dump(mode="json") for item in messages],
            },
            indent=2,
        )
