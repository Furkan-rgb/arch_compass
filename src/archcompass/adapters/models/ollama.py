"""Ollama REST adapters with schema-constrained structured outputs."""

from __future__ import annotations

import json
import math
from collections.abc import Callable, Mapping
from hashlib import sha256
from typing import ClassVar, TypeVar, cast

import httpx
from pydantic import BaseModel, ConfigDict, Field, RootModel, ValidationError

from archcompass.adapters.models.prompt_contracts import (
    ANALYZE_CONCERN_CLUSTER,
    ANSWER_REPORT_QUESTION,
    CLASSIFY_REPORT_QUESTION,
    CLUSTER_DESIGN_FORCES,
    DISCOVER_DESIGN_FORCES,
    EVALUATE_SCENARIOS,
    GENERATE_ALTERNATIVES,
    LINK_STATEMENT_SUPPORT,
    OLLAMA_STAGE_PROMPTS,
    PLAN_ATLAS_QUERIES,
    REPAIR_CONVERSATION_ANSWER,
    SUMMARIZE_REPORT_CONVERSATION,
    SYNTHESIZE_RECOMMENDATION,
    PromptContract,
)
from archcompass.configuration import EmbeddingModelConfig, ReasoningModelConfig
from archcompass.domain.base import canonical_json
from archcompass.domain.case import ArchitectureCase, CaseAlternative
from archcompass.domain.consultation import (
    Claim,
    ClaimClassification,
    ClusterQueryPlan,
    ConcernAnalysis,
    ConcernCluster,
    DesignForce,
    FocusedAnalysisPacket,
    FocusedNodeSummary,
    GlobalContext,
    RecommendationReport,
    ScenarioEvaluation,
    SupportedStatement,
)
from archcompass.domain.conversation import (
    ConversationAnswer,
    ConversationMessageView,
    ConversationSummary,
    ReportConversationContext,
    ReportQuestionPlan,
    ReportQuestionPlanningContext,
)
from archcompass.domain.diagnostics import (
    FailureDiagnostic,
    FailureDiagnosticCode,
    format_failure_diagnostic,
)
from archcompass.domain.errors import (
    ClusterPartitionError,
    ModelOutputValidationError,
    ProviderError,
)
from archcompass.domain.evidence_rules import location_within
from archcompass.domain.policy import canonical_policy_evidence
from archcompass.ports.reasoning import ReasoningTask

Item = TypeVar("Item", bound=BaseModel)


def _object_mapping(value: object) -> dict[str, object] | None:
    if not isinstance(value, Mapping):
        return None
    source = cast(Mapping[object, object], value)
    return {str(key): item for key, item in source.items()}


class ProposedDesignForce(BaseModel):
    """Model-facing force content; identity is owned by ArchCompass."""

    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=1)
    description: str = Field(min_length=1)
    importance: str = Field(min_length=1)


class ProposedDesignForceList(RootModel[list[ProposedDesignForce]]):
    root: list[ProposedDesignForce] = Field(min_length=1, max_length=8)


class ProposedConcernCluster(BaseModel):
    """Model-facing cluster content using bounded, request-local force handles."""

    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=1)
    rationale: str = Field(min_length=1)
    force_refs: list[str] = Field(min_length=1)


class ProposedConcernClusterList(RootModel[list[ProposedConcernCluster]]):
    root: list[ProposedConcernCluster]


class ConcernAnalysisList(RootModel[list[ConcernAnalysis]]):
    pass


class ClusterQueryPlanList(RootModel[list[ClusterQueryPlan]]):
    pass


class AlternativeList(RootModel[list[CaseAlternative]]):
    root: list[CaseAlternative] = Field(min_length=2, max_length=5)


class ScenarioList(RootModel[list[ScenarioEvaluation]]):
    root: list[ScenarioEvaluation] = Field(min_length=1, max_length=4)


class StatementSupportAssignment(BaseModel):
    statement_key: str = Field(min_length=1)
    supporting_claim_ids: list[str] = Field(min_length=1)


class StatementSupportPlan(RootModel[list[StatementSupportAssignment]]):
    root: list[StatementSupportAssignment] = Field(min_length=1)


class EmbeddingResponse(BaseModel):
    embeddings: list[list[float]]


class OllamaEmbeddingProvider:
    def __init__(self, config: EmbeddingModelConfig) -> None:
        self._config = config

    @property
    def identity(self) -> tuple[str, str, int]:
        return (self._config.provider, self._config.model, self._config.dimensions)

    def embed(self, texts: list[str]) -> list[list[float]]:
        try:
            response = httpx.post(
                f"{self._config.base_url.rstrip('/')}/api/embed",
                json={"model": self._config.model, "input": texts},
                timeout=self._config.timeout_seconds,
            )
            response.raise_for_status()
            payload = EmbeddingResponse.model_validate_json(response.content)
            if len(payload.embeddings) != len(texts):
                raise ValueError(
                    f"Ollama returned {len(payload.embeddings)} embeddings for {len(texts)} inputs"
                )
            for index, vector in enumerate(payload.embeddings):
                if len(vector) != self._config.dimensions:
                    raise ValueError(
                        f"Ollama embedding {index} has {len(vector)} dimensions; "
                        f"expected {self._config.dimensions}"
                    )
                if any(not math.isfinite(value) for value in vector):
                    raise ValueError(f"Ollama embedding {index} contains a non-finite value")
            return payload.embeddings
        except (httpx.HTTPError, KeyError, TypeError, ValueError) as error:
            raise ProviderError(f"Ollama embedding request failed: {error}") from error


class OllamaReasoningProvider:
    _PROMPTS: ClassVar[dict[ReasoningTask, str]] = {
        task: contract.identity for task, contract in OLLAMA_STAGE_PROMPTS.items()
    }

    def __init__(self, config: ReasoningModelConfig) -> None:
        self._config = config
        self._repair_actions: list[dict[str, object]] = []

    @property
    def model_identity(self) -> str:
        return f"{self._config.provider}:{self._config.model}"

    def prompt_identity(self, task: ReasoningTask) -> str:
        return self._PROMPTS[task]

    def consume_repair_actions(self) -> list[dict[str, object]]:
        actions = list(self._repair_actions)
        self._repair_actions.clear()
        return actions

    def discover_design_forces(self, context: GlobalContext) -> list[DesignForce]:
        proposed = self._complete(
            DISCOVER_DESIGN_FORCES,
            context,
            ProposedDesignForceList,
        ).root
        forces: list[DesignForce] = []
        known_ids: set[str] = set()
        for item in proposed:
            force = DesignForce(
                title=item.title,
                description=item.description,
                importance=item.importance,
            )
            while force.force_id in known_ids:
                force = DesignForce(
                    title=item.title,
                    description=item.description,
                    importance=item.importance,
                )
            known_ids.add(force.force_id)
            forces.append(force)
        return forces

    def cluster_design_forces(
        self, context: GlobalContext, forces: list[DesignForce]
    ) -> list[ConcernCluster]:
        if len({force.force_id for force in forces}) != len(forces):
            raise ValueError("Design force IDs must be unique before clustering")
        handled_forces = [(f"F{index}", force) for index, force in enumerate(forces, start=1)]
        ids_by_handle = {handle: force.force_id for handle, force in handled_forces}
        proposed = self._complete(
            CLUSTER_DESIGN_FORCES,
            {
                "context": context.model_dump(mode="json"),
                "forces": [
                    {
                        "force_ref": handle,
                        "title": force.title,
                        "description": force.description,
                        "importance": force.importance,
                    }
                    for handle, force in handled_forces
                ],
            },
            ProposedConcernClusterList,
            runtime_instruction=(
                "Use only the supplied force_ref handles in force_refs. "
                f"Allowed force handles: {list(ids_by_handle)}. "
                "Assign every handle exactly once across all clusters. "
                "ArchCompass owns internal force and cluster IDs; do not create or copy them."
            ),
            schema_override=self._cluster_proposal_schema(set(ids_by_handle)),
            candidate_validator=lambda candidate: self._force_handle_partition_errors(
                candidate.root,
                set(ids_by_handle),
            ),
            candidate_error_factory=lambda candidate: ClusterPartitionError(
                self._force_handle_partition_diagnostics(
                    candidate.root,
                    set(ids_by_handle),
                )
            ),
        ).root
        return [
            ConcernCluster(
                title=cluster.title,
                rationale=cluster.rationale,
                design_force_ids=[ids_by_handle[force_ref] for force_ref in cluster.force_refs],
            )
            for cluster in proposed
        ]

    def plan_atlas_queries(
        self,
        context: GlobalContext,
        forces: list[DesignForce],
        clusters: list[ConcernCluster],
        *,
        iteration: int,
        prior_results: dict[str, list[FocusedNodeSummary]],
    ) -> list[ClusterQueryPlan]:
        payload: dict[str, object] = {
            "context": context.model_dump(mode="json"),
            "forces": [force.model_dump(mode="json") for force in forces],
            "clusters": [cluster.model_dump(mode="json") for cluster in clusters],
            "iteration": iteration,
            "prior_results": {
                cluster_id: [result.model_dump(mode="json") for result in results]
                for cluster_id, results in prior_results.items()
            },
        }
        allowed_node_ids = {
            cluster.cluster_id: sorted(
                summary.node_id for summary in prior_results.get(cluster.cluster_id, [])
            )
            for cluster in clusters
        }
        return self._complete(
            PLAN_ATLAS_QUERIES,
            payload,
            ClusterQueryPlanList,
            runtime_instruction=f"Allowed node IDs by cluster: {allowed_node_ids}.",
        ).root

    def analyze_concern_cluster(
        self,
        context: GlobalContext,
        packet: FocusedAnalysisPacket,
    ) -> ConcernAnalysis:
        allowed_node_ids = sorted(packet.surfaced_node_ids)
        allowed_policy_ids = sorted(item.policy.id for item in packet.policies)
        return self._complete(
            ANALYZE_CONCERN_CLUSTER,
            {"context": context.model_dump(mode="json"), "packet": packet.model_dump(mode="json")},
            ConcernAnalysis,
            runtime_instruction=(
                f"Set cluster_id exactly to {packet.cluster.cluster_id!r}. "
                f"Allowed atlas node IDs: {allowed_node_ids or ['none']}. "
                f"Allowed policy IDs: {allowed_policy_ids or ['none']}. "
                "Use no other evidence IDs. When no atlas IDs are allowed, do not classify a "
                "finding as a repository observation. When no policy IDs are allowed, do not "
                "classify a finding as policy guidance."
            ),
        )

    def generate_alternatives(
        self, context: GlobalContext, analyses: list[ConcernAnalysis]
    ) -> list[CaseAlternative]:
        return self._complete(
            GENERATE_ALTERNATIVES,
            {
                "context": context.model_dump(mode="json"),
                "analyses": [item.model_dump(mode="json") for item in analyses],
            },
            AlternativeList,
        ).root

    def evaluate_scenarios(
        self,
        context: GlobalContext,
        alternatives: list[CaseAlternative],
        analyses: list[ConcernAnalysis],
    ) -> list[ScenarioEvaluation]:
        alternative_handles = {
            f"A{ordinal}": item.id
            for ordinal, item in enumerate(alternatives, start=1)
        }
        completed = self._complete(
            EVALUATE_SCENARIOS,
            {
                "context": context.model_dump(mode="json"),
                "alternatives": [
                    {
                        "alternative_ref": handle,
                        "title": alternative.title,
                        "summary": alternative.summary,
                    }
                    for handle, alternative in zip(
                        alternative_handles,
                        alternatives,
                        strict=True,
                    )
                ],
                "analyses": [item.model_dump(mode="json") for item in analyses],
            },
            ScenarioList,
            runtime_instruction=(
                "Every alternative_results object must contain exactly these keys, "
                f"once each, with no aliases or replacements: "
                f"{list(alternative_handles)}."
            ),
            candidate_validator=lambda candidate: self._scenario_coverage_errors(
                candidate.root,
                allowed_alternative_ids=set(alternative_handles),
            ),
        ).root
        return [
            scenario.model_copy(
                update={
                    "alternative_results": {
                        alternative_handles[handle]: result
                        for handle, result in scenario.alternative_results.items()
                    }
                }
            )
            for scenario in completed
        ]

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
    ) -> RecommendationReport:
        allowed_node_ids = sorted(
            {node_id for packet in packets for node_id in packet.surfaced_node_ids}
        )
        allowed_policy_ids = sorted(
            {retrieved.policy.id for packet in packets for retrieved in packet.policies}
        )
        policy_evidence = canonical_policy_evidence(
            retrieved for packet in packets for retrieved in packet.policies
        )
        report = self._complete(
            SYNTHESIZE_RECOMMENDATION,
            {
                "case": case.model_dump(mode="json"),
                "context": context.model_dump(mode="json"),
                "forces": [item.model_dump(mode="json") for item in forces],
                "clusters": [item.model_dump(mode="json") for item in clusters],
                "analyses": [item.model_dump(mode="json") for item in analyses],
                "alternatives": [item.model_dump(mode="json") for item in alternatives],
                "scenarios": [item.model_dump(mode="json") for item in scenarios],
                "policy_evidence": [item.model_dump(mode="json") for item in policy_evidence],
            },
            RecommendationReport,
            runtime_instruction=(
                f"Allowed atlas node IDs: {allowed_node_ids or ['none']}. "
                f"Allowed policy IDs: {allowed_policy_ids or ['none']}. "
                "Use no other evidence IDs. When no atlas IDs are allowed, "
                "repository_observations must be empty and no claim may contain an atlas "
                "reference. Every policy-guidance claim must reference at least one allowed "
                "policy ID."
            ),
            normalization_context={
                "important_design_forces": [item.model_dump(mode="json") for item in forces],
                "alternatives_considered": [item.model_dump(mode="json") for item in alternatives],
                "scenario_analysis": [item.model_dump(mode="json") for item in scenarios],
                "policy_evidence": [item.model_dump(mode="json") for item in policy_evidence],
            },
        )
        return self._link_report_support(report, packets=packets)

    def classify_report_question(
        self,
        context: ReportQuestionPlanningContext,
    ) -> ReportQuestionPlan:
        return self._complete(
            CLASSIFY_REPORT_QUESTION,
            context,
            ReportQuestionPlan,
            runtime_instruction=(
                "Allowed finding IDs: "
                f"{[item.finding_id for item in context.finding_digests]}. "
                "Use no more than eight retrieval actions."
            ),
            think=False,
            temperature=0,
        )

    def answer_report_question(
        self,
        context: ReportConversationContext,
    ) -> ConversationAnswer:
        allowed_finding_ids = {
            item.finding_id for item in context.finding_digests
        }
        allowed_claim_ids = {item.claim_id for item in context.retrieved_claims}
        allowed_evidence_ids = {
            item.evidence_id for item in context.evidence_references
        }
        allowed_policy_ids = {item.policy.id for item in context.retrieved_policies}

        return self._complete(
            ANSWER_REPORT_QUESTION,
            {
                "question": context.question,
                "context": context.model_dump(mode="json"),
            },
            ConversationAnswer,
            runtime_instruction=(
                f"Allowed finding IDs: {sorted(allowed_finding_ids)}. "
                f"Allowed report claim IDs: {sorted(allowed_claim_ids)}. "
                f"Allowed exact evidence IDs: {sorted(allowed_evidence_ids)}. "
                f"Allowed policy IDs: {sorted(allowed_policy_ids)}."
            ),
            allow_repair=False,
            think=False,
            temperature=0,
        )

    def summarize_report_conversation(
        self,
        current_summary: ConversationSummary | None,
        messages: list[ConversationMessageView],
    ) -> ConversationSummary:
        return self._complete(
            SUMMARIZE_REPORT_CONVERSATION,
            {
                "current_summary": current_summary,
                "messages": [item.model_dump(mode="json") for item in messages],
            },
            ConversationSummary,
            think=False,
            temperature=0,
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
        return self._complete(
            REPAIR_CONVERSATION_ANSWER,
            {
                "answer": answer.model_dump(mode="json"),
                "errors": errors,
                "allowed_finding_ids": sorted(allowed_finding_ids),
                "allowed_claim_ids": sorted(allowed_claim_ids),
                "allowed_evidence_ids": sorted(allowed_evidence_ids),
                "allowed_policy_ids": sorted(allowed_policy_ids),
            },
            ConversationAnswer,
            allow_repair=False,
            think=False,
            temperature=0,
        )

    def _complete(
        self,
        contract: PromptContract,
        payload: BaseModel | Mapping[str, object],
        output_type: type[Item],
        *,
        runtime_instruction: str = "",
        normalization_context: Mapping[str, object] | None = None,
        schema_override: Mapping[str, object] | None = None,
        candidate_validator: Callable[[Item], list[str]] | None = None,
        candidate_error_factory: (Callable[[Item], ModelOutputValidationError] | None) = None,
        allow_repair: bool = True,
        think: bool | str | None = None,
        temperature: float | None = None,
    ) -> Item:
        data = payload.model_dump(mode="json") if isinstance(payload, BaseModel) else dict(payload)
        instruction = contract.request
        if runtime_instruction:
            instruction = f"{instruction}\n\nRun-specific constraints:\n{runtime_instruction}"
        messages = [
            {
                "role": "system",
                "content": contract.system_prompt,
            },
            {
                "role": "user",
                "content": f"{instruction}\n\nInput:\n{canonical_json(data)}",
            },
        ]
        try:
            content = self._normalize_output(
                output_type,
                self._chat(
                    output_type,
                    messages,
                    schema_override=schema_override,
                    think=think,
                    temperature=temperature,
                ),
                normalization_context=normalization_context,
            )
            try:
                candidate = output_type.model_validate_json(content)
            except ValidationError as first_error:
                validation_errors = str(first_error)
            else:
                candidate_errors = (
                    candidate_validator(candidate) if candidate_validator is not None else []
                )
                if not candidate_errors:
                    return candidate
                validation_errors = "; ".join(candidate_errors)
            if not allow_repair:
                raise ModelOutputValidationError(
                    "Ollama returned invalid structured output: "
                    f"{validation_errors}"
                )
            repair_messages = [
                *messages,
                {"role": "assistant", "content": content},
                {
                    "role": "user",
                    "content": (
                        "The previous JSON failed validation. Return the complete corrected "
                        "JSON object only, under the same schema. Do not omit valid content. "
                        f"Validation errors:\n{validation_errors}"
                    ),
                },
            ]
            repaired = self._normalize_output(
                output_type,
                self._chat(
                    output_type,
                    repair_messages,
                    schema_override=schema_override,
                    think=think,
                    temperature=temperature,
                ),
                normalization_context=normalization_context,
            )
            try:
                candidate = output_type.model_validate_json(repaired)
            except ValidationError as final_error:
                raise ModelOutputValidationError(
                    "Ollama returned invalid structured output after one repair pass: "
                    f"{final_error}"
                ) from final_error
            candidate_errors = (
                candidate_validator(candidate) if candidate_validator is not None else []
            )
            if candidate_errors:
                if candidate_error_factory is not None:
                    raise candidate_error_factory(candidate)
                raise ModelOutputValidationError(
                    "Ollama returned invalid structured output after one repair pass: "
                    + "; ".join(candidate_errors)
                )
            return candidate
        except httpx.HTTPStatusError as error:
            detail = error.response.text.strip()
            if len(detail) > 1000:
                detail = detail[:999].rstrip() + "…"
            suffix = f": {detail}" if detail else ""
            raise ProviderError(
                f"Ollama reasoning request failed with HTTP {error.response.status_code}{suffix}"
            ) from error
        except (httpx.HTTPError, KeyError, TypeError, ValueError) as error:
            raise ProviderError(f"Ollama reasoning request failed: {error}") from error

    @staticmethod
    def _scenario_coverage_errors(
        scenarios: list[ScenarioEvaluation],
        *,
        allowed_alternative_ids: set[str],
    ) -> list[str]:
        errors: list[str] = []
        for ordinal, scenario in enumerate(scenarios, start=1):
            actual = set(scenario.alternative_results)
            missing = sorted(allowed_alternative_ids - actual)
            unknown = sorted(actual - allowed_alternative_ids)
            if missing:
                errors.append(
                    f"Scenario {ordinal} omits alternative IDs: {missing}"
                )
            if unknown:
                errors.append(
                    f"Scenario {ordinal} invents alternative IDs: {unknown}"
                )
        return errors

    @staticmethod
    def _cluster_proposal_schema(allowed_refs: set[str]) -> dict[str, object]:
        """Constrain model-visible references without exposing domain identifiers."""

        return {
            "type": "array",
            "minItems": 1,
            "maxItems": 4,
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["title", "rationale", "force_refs"],
                "properties": {
                    "title": {"type": "string", "minLength": 1},
                    "rationale": {"type": "string", "minLength": 1},
                    "force_refs": {
                        "type": "array",
                        "minItems": 1,
                        "items": {
                            "type": "string",
                            "enum": sorted(allowed_refs),
                        },
                    },
                },
            },
        }

    @staticmethod
    def _force_handle_partition_errors(
        clusters: list[ProposedConcernCluster],
        allowed_handles: set[str],
    ) -> list[str]:
        return [
            format_failure_diagnostic(diagnostic)
            for diagnostic in OllamaReasoningProvider._force_handle_partition_diagnostics(
                clusters,
                allowed_handles,
            )
        ]

    @staticmethod
    def _force_handle_partition_diagnostics(
        clusters: list[ProposedConcernCluster],
        allowed_handles: set[str],
    ) -> list[FailureDiagnostic]:
        assigned = [force_ref for cluster in clusters for force_ref in cluster.force_refs]
        actual = set(assigned)
        diagnostics: list[FailureDiagnostic] = []
        unknown_count = sum(force_handle not in allowed_handles for force_handle in assigned)
        missing = sorted(allowed_handles - actual)
        duplicates = sorted(
            force_handle
            for force_handle in actual & allowed_handles
            if assigned.count(force_handle) > 1
        )
        if not 1 <= len(clusters) <= 4:
            diagnostics.append(
                FailureDiagnostic(
                    code=FailureDiagnosticCode.CLUSTER_COUNT_OUT_OF_RANGE,
                    count=len(clusters),
                )
            )
        if unknown_count:
            diagnostics.append(
                FailureDiagnostic(
                    code=FailureDiagnosticCode.UNKNOWN_FORCE_REFERENCES,
                    count=unknown_count,
                )
            )
        if missing:
            diagnostics.append(
                FailureDiagnostic(
                    code=FailureDiagnosticCode.MISSING_FORCE_REFERENCES,
                    force_handles=missing,
                )
            )
        if duplicates:
            diagnostics.append(
                FailureDiagnostic(
                    code=FailureDiagnosticCode.DUPLICATE_FORCE_REFERENCES,
                    force_handles=duplicates,
                )
            )
        return diagnostics

    def _link_report_support(
        self,
        report: RecommendationReport,
        *,
        packets: list[FocusedAnalysisPacket],
    ) -> RecommendationReport:
        slots = self._statement_slots(report)
        nodes_by_id = {node.node_id: node for packet in packets for node in packet.node_summaries}
        allowed_policy_ids = {
            retrieved.policy.id for packet in packets for retrieved in packet.policies
        }
        report_claims = [
            *report.confirmed_context,
            *report.assumptions_and_unresolved_questions,
            *report.repository_observations,
            *report.relevant_policies,
            *report.evidence_appendix,
        ]
        claims_by_id = {
            claim.claim_id: claim
            for claim in report_claims
            if self._claim_can_survive_evidence_repair(
                claim,
                nodes_by_id=nodes_by_id,
                allowed_policy_ids=allowed_policy_ids,
            )
        }
        excluded_claim_ids = sorted({claim.claim_id for claim in report_claims} - set(claims_by_id))
        if excluded_claim_ids:
            self._repair_actions.append(
                {
                    "kind": "excluded_invalid_statement_support_claims",
                    "claim_ids": excluded_claim_ids,
                }
            )
        if not claims_by_id:
            raise ModelOutputValidationError(
                "The synthesized report contains no claims that can survive evidence validation"
            )
        payload = {
            "claims": [claim.model_dump(mode="json") for claim in claims_by_id.values()],
            "statements": [
                {
                    "statement_key": key,
                    "text": statement.text,
                    "classification": statement.classification,
                }
                for key, statement in slots
            ],
        }
        schema = self._support_plan_schema(
            statement_keys={key for key, _ in slots},
            claim_ids=set(claims_by_id),
            statement_count=len(slots),
        )
        plan = self._complete(
            LINK_STATEMENT_SUPPORT,
            payload,
            StatementSupportPlan,
            schema_override=schema,
        ).root
        errors = self._support_plan_errors(plan, slots, set(claims_by_id))
        if errors:
            plan = self._complete(
                LINK_STATEMENT_SUPPORT,
                payload,
                StatementSupportPlan,
                runtime_instruction=("Correct these prior mapping errors: " + "; ".join(errors)),
                schema_override=schema,
            ).root
            errors = self._support_plan_errors(plan, slots, set(claims_by_id))
        if errors:
            raise ModelOutputValidationError(
                "Ollama returned an invalid statement support plan: " + "; ".join(errors)
            )
        assignments = {item.statement_key: item.supporting_claim_ids for item in plan}
        linked = self._apply_statement_support(report, assignments)
        self._repair_actions.append(
            {
                "kind": "linked_report_statement_support",
                "previous_support": {
                    key: statement.supporting_claim_ids for key, statement in slots
                },
                "assignments": assignments,
            }
        )
        return linked

    @staticmethod
    def _claim_can_survive_evidence_repair(
        claim: Claim,
        *,
        nodes_by_id: dict[str, FocusedNodeSummary],
        allowed_policy_ids: set[str],
    ) -> bool:
        if claim.classification == ClaimClassification.POLICY_GUIDANCE:
            return any(policy_id in allowed_policy_ids for policy_id in claim.policy_ids)
        if claim.classification != ClaimClassification.REPOSITORY_OBSERVATION:
            return True
        if not claim.atlas_references:
            return False
        if any(policy_id not in allowed_policy_ids for policy_id in claim.policy_ids):
            return False
        return all(
            location_within(
                node.location if (node := nodes_by_id.get(reference.node_id)) else None,
                reference.location,
            )
            for reference in claim.atlas_references
        )

    @staticmethod
    def _support_plan_schema(
        *,
        statement_keys: set[str],
        claim_ids: set[str],
        statement_count: int,
    ) -> dict[str, object]:
        return {
            "type": "array",
            "minItems": statement_count,
            "maxItems": statement_count,
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["statement_key", "supporting_claim_ids"],
                "properties": {
                    "statement_key": {
                        "type": "string",
                        "enum": sorted(statement_keys),
                    },
                    "supporting_claim_ids": {
                        "type": "array",
                        "minItems": 1,
                        "items": {
                            "type": "string",
                            "enum": sorted(claim_ids),
                        },
                    },
                },
            },
        }

    @staticmethod
    def _statement_slots(
        report: RecommendationReport,
    ) -> list[tuple[str, SupportedStatement]]:
        slots = [
            ("decision_summary", report.decision_summary),
            ("recommended_architecture", report.recommended_architecture),
            (
                "change_amplification_analysis",
                report.change_amplification_analysis,
            ),
            ("adr.decision", report.adr.decision),
        ]
        for field in (
            "responsibility_allocation",
            "conceptual_interfaces",
            "trade_offs",
            "implementation_sequence",
            "reversal_conditions",
            "revisit_triggers",
        ):
            slots.extend(
                (f"{field}.{index}", statement)
                for index, statement in enumerate(getattr(report, field))
            )
        slots.extend(
            (f"adr.consequences.{index}", statement)
            for index, statement in enumerate(report.adr.consequences)
        )
        return slots

    @staticmethod
    def _support_plan_errors(
        plan: list[StatementSupportAssignment],
        slots: list[tuple[str, SupportedStatement]],
        known_claim_ids: set[str],
    ) -> list[str]:
        expected = {key for key, _ in slots}
        actual = [item.statement_key for item in plan]
        errors: list[str] = []
        if set(actual) != expected or len(actual) != len(set(actual)):
            errors.append(
                "Statement keys must match exactly; "
                f"missing={sorted(expected - set(actual))}, "
                f"extra={sorted(set(actual) - expected)}"
            )
        unknown = sorted(
            {
                claim_id
                for item in plan
                for claim_id in item.supporting_claim_ids
                if claim_id not in known_claim_ids
            }
        )
        if unknown:
            errors.append(
                f"Support plan references unknown claim IDs {unknown}; "
                f"allowed={sorted(known_claim_ids)}"
            )
        return errors

    @staticmethod
    def _apply_statement_support(
        report: RecommendationReport,
        assignments: dict[str, list[str]],
    ) -> RecommendationReport:
        def linked(key: str, statement: SupportedStatement) -> SupportedStatement:
            return statement.model_copy(update={"supporting_claim_ids": assignments[key]})

        adr = report.adr.model_copy(
            update={
                "decision": linked("adr.decision", report.adr.decision),
                "consequences": [
                    linked(f"adr.consequences.{index}", statement)
                    for index, statement in enumerate(report.adr.consequences)
                ],
            }
        )
        updates: dict[str, object] = {
            "decision_summary": linked("decision_summary", report.decision_summary),
            "recommended_architecture": linked(
                "recommended_architecture",
                report.recommended_architecture,
            ),
            "change_amplification_analysis": linked(
                "change_amplification_analysis",
                report.change_amplification_analysis,
            ),
            "adr": adr,
        }
        for field in (
            "responsibility_allocation",
            "conceptual_interfaces",
            "trade_offs",
            "implementation_sequence",
            "reversal_conditions",
            "revisit_triggers",
        ):
            updates[field] = [
                linked(f"{field}.{index}", statement)
                for index, statement in enumerate(getattr(report, field))
            ]
        return report.model_copy(update=updates)

    def _chat(
        self,
        output_type: type[Item],
        messages: list[dict[str, str]],
        *,
        schema_override: Mapping[str, object] | None = None,
        think: bool | str | None = None,
        temperature: float | None = None,
    ) -> str:
        options: dict[str, object] = {
            "num_ctx": self._config.context_window_tokens,
            "num_predict": self._config.max_output_tokens,
        }
        if temperature is not None:
            options["temperature"] = temperature
        request: dict[str, object] = {
            "model": self._config.model,
            "stream": False,
            "format": (
                schema_override if schema_override is not None else output_type.model_json_schema()
            ),
            "options": options,
            "messages": messages,
        }
        if think is not None:
            request["think"] = think
        response = httpx.post(
            f"{self._config.base_url.rstrip('/')}/api/chat",
            json=request,
            timeout=self._config.timeout_seconds,
        )
        response.raise_for_status()
        content = response.json()["message"]["content"]
        if not isinstance(content, str):
            raise TypeError("Ollama response content is not text")
        return content

    def _normalize_output(
        self,
        output_type: type[Item],
        content: str,
        *,
        normalization_context: Mapping[str, object] | None = None,
    ) -> str:
        if output_type is not RecommendationReport:
            return content
        try:
            decoded: object = json.loads(content)
        except (TypeError, ValueError):
            return content
        payload = _object_mapping(decoded)
        if payload is None:
            return content

        if normalization_context is not None:
            for field in (
                "important_design_forces",
                "alternatives_considered",
                "scenario_analysis",
                "policy_evidence",
            ):
                canonical = normalization_context.get(field)
                if canonical is None or payload.get(field) == canonical:
                    continue
                self._repair_actions.append(
                    {
                        "kind": "restored_canonical_synthesis_artifact",
                        "field": field,
                        "model_output": payload.get(field),
                        "canonical_input": canonical,
                    }
                )
                payload[field] = canonical

        section_classifications = {
            "confirmed_context": "confirmed_user_requirement",
            "assumptions_and_unresolved_questions": "scenario_assumption",
            "repository_observations": "repository_observation",
            "relevant_policies": "policy_guidance",
        }
        raw_appendix = payload.get("evidence_appendix")
        appendix = list(cast(list[object], raw_appendix)) if isinstance(raw_appendix, list) else []
        payload["evidence_appendix"] = appendix
        appendix_ids = {
            item.get("claim_id")
            for raw_item in appendix
            if (item := _object_mapping(raw_item)) is not None
            and isinstance(item.get("claim_id"), str)
        }

        for section, expected in section_classifications.items():
            raw_claims = payload.get(section)
            if not isinstance(raw_claims, list):
                continue
            retained: list[object] = []
            for raw_claim in cast(list[object], raw_claims):
                claim = _object_mapping(raw_claim)
                if claim is None or claim.get("classification") == expected:
                    retained.append(raw_claim)
                    continue
                claim_id = claim.get("claim_id")
                if isinstance(claim_id, str) and claim_id not in appendix_ids:
                    appendix.append(claim)
                    appendix_ids.add(claim_id)
                self._repair_actions.append(
                    {
                        "kind": "moved_misclassified_report_claim",
                        "section": section,
                        "expected_classification": expected,
                        "claim": claim,
                    }
                )
            payload[section] = retained

        registry: dict[str, str] = {}
        reassignments: dict[tuple[str, str], str] = {}
        occupied_ids: set[str] = set()
        for section in (
            "confirmed_context",
            "assumptions_and_unresolved_questions",
            "repository_observations",
            "relevant_policies",
            "evidence_appendix",
        ):
            raw_claims = payload.get(section)
            if not isinstance(raw_claims, list):
                continue
            normalized_claims: list[object] = []
            for raw_claim in cast(list[object], raw_claims):
                claim = _object_mapping(raw_claim)
                claim_id = None if claim is None else claim.get("claim_id")
                if claim is None or not isinstance(claim_id, str):
                    normalized_claims.append(raw_claim)
                    continue
                serialized = json.dumps(claim, sort_keys=True)
                replacement = reassignments.get((claim_id, serialized))
                prior = registry.get(claim_id)
                if replacement is None and prior is not None and prior != serialized:
                    digest = sha256(f"{claim_id}\0{serialized}".encode()).hexdigest()
                    replacement = f"claim_{digest[:32]}"
                    counter = 1
                    while replacement in occupied_ids:
                        digest = sha256(f"{claim_id}\0{serialized}\0{counter}".encode()).hexdigest()
                        replacement = f"claim_{digest[:32]}"
                        counter += 1
                    reassignments[(claim_id, serialized)] = replacement
                    self._repair_actions.append(
                        {
                            "kind": "reassigned_duplicate_report_claim_id",
                            "section": section,
                            "from_claim_id": claim_id,
                            "to_claim_id": replacement,
                            "claim": claim,
                        }
                    )
                if replacement is not None:
                    claim["claim_id"] = replacement
                else:
                    registry[claim_id] = serialized
                    occupied_ids.add(claim_id)
                normalized_claims.append(claim)
            payload[section] = normalized_claims
        return json.dumps(payload)
