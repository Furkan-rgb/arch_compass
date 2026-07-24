"""Focused reasoning boundary used by the consultation application workflow."""

from __future__ import annotations

from typing import Protocol

from archcompass.domain.case import ArchitectureCase, CaseAlternative
from archcompass.domain.consultation import (
    ClusterQueryPlan,
    ConcernAnalysis,
    ConcernCluster,
    DesignForce,
    FocusedAnalysisPacket,
    FocusedNodeSummary,
    GlobalContext,
    RecommendationReport,
    ScenarioEvaluation,
)
from archcompass.domain.conversation import (
    ConversationAnswer,
    ConversationMessageView,
    ConversationSummary,
    ReportConversationContext,
    ReportQuestionPlan,
    ReportQuestionPlanningContext,
)


class ReportConversationReasoner(Protocol):
    @property
    def model_identity(self) -> str: ...

    def prompt_identity(self, task: str) -> str: ...

    def classify_report_question(
        self,
        context: ReportQuestionPlanningContext,
    ) -> ReportQuestionPlan: ...

    def answer_report_question(
        self,
        context: ReportConversationContext,
    ) -> ConversationAnswer: ...

    def summarize_report_conversation(
        self,
        current_summary: ConversationSummary | None,
        messages: list[ConversationMessageView],
    ) -> ConversationSummary: ...

    def repair_conversation_answer(
        self,
        answer: ConversationAnswer,
        errors: list[str],
        allowed_finding_ids: set[str],
        allowed_claim_ids: set[str],
        allowed_evidence_ids: set[str],
        allowed_policy_ids: set[str],
    ) -> ConversationAnswer: ...


class FocusedReasoningProvider(ReportConversationReasoner, Protocol):
    def consume_repair_actions(self) -> list[dict[str, object]]: ...

    def discover_design_forces(self, context: GlobalContext) -> list[DesignForce]: ...

    def cluster_design_forces(
        self, context: GlobalContext, forces: list[DesignForce]
    ) -> list[ConcernCluster]: ...

    def plan_atlas_queries(
        self,
        context: GlobalContext,
        forces: list[DesignForce],
        clusters: list[ConcernCluster],
        *,
        iteration: int,
        prior_results: dict[str, list[FocusedNodeSummary]],
    ) -> list[ClusterQueryPlan]: ...

    def analyze_concern_cluster(
        self,
        context: GlobalContext,
        packet: FocusedAnalysisPacket,
    ) -> ConcernAnalysis: ...

    def generate_alternatives(
        self, context: GlobalContext, analyses: list[ConcernAnalysis]
    ) -> list[CaseAlternative]: ...

    def evaluate_scenarios(
        self,
        context: GlobalContext,
        alternatives: list[CaseAlternative],
        analyses: list[ConcernAnalysis],
    ) -> list[ScenarioEvaluation]: ...

    def synthesize_recommendation(
        self,
        case: ArchitectureCase,
        context: GlobalContext,
        forces: list[DesignForce],
        clusters: list[ConcernCluster],
        analyses: list[ConcernAnalysis],
        alternatives: list[CaseAlternative],
        scenarios: list[ScenarioEvaluation],
        packets: list[FocusedAnalysisPacket],
    ) -> RecommendationReport: ...
