"""Focused reasoning boundary used by the consultation application workflow."""

from __future__ import annotations

from enum import StrEnum
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


class ReasoningTask(StrEnum):
    """Every reasoning stage that carries its own versioned prompt contract.

    Stage names were previously repeated as bare strings in the prompt registry, the
    workflow call sites, and the conversation service, so a typo surfaced only as a
    runtime KeyError. Naming them once makes the set checkable.
    """

    DISCOVER_DESIGN_FORCES = "discover_design_forces"
    CLUSTER_DESIGN_FORCES = "cluster_design_forces"
    PLAN_ATLAS_QUERIES = "plan_atlas_queries"
    ANALYZE_CONCERN_CLUSTER = "analyze_concern_cluster"
    GENERATE_ALTERNATIVES = "generate_alternatives"
    EVALUATE_SCENARIOS = "evaluate_scenarios"
    SYNTHESIZE_RECOMMENDATION = "synthesize_recommendation"
    LINK_STATEMENT_SUPPORT = "link_statement_support"
    CLASSIFY_REPORT_QUESTION = "classify_report_question"
    ANSWER_REPORT_QUESTION = "answer_report_question"
    SUMMARIZE_REPORT_CONVERSATION = "summarize_report_conversation"
    REPAIR_CONVERSATION_ANSWER = "repair_conversation_answer"


class ReportConversationReasoner(Protocol):
    @property
    def model_identity(self) -> str: ...

    def prompt_identity(self, task: ReasoningTask) -> str: ...

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
