"""Ollama REST adapters with schema-constrained structured outputs."""

from __future__ import annotations

import json
import math
from collections.abc import Mapping
from hashlib import sha256
from typing import ClassVar, TypeVar, cast

import httpx
from pydantic import BaseModel, Field, RootModel, ValidationError

from archcompass.configuration import EmbeddingModelConfig, ReasoningModelConfig
from archcompass.domain.case import ArchitectureCase, CaseAlternative
from archcompass.domain.consultation import (
    ClusterQueryPlan,
    ConcernAnalysis,
    ConcernCluster,
    ConcernClusterList,
    DesignForce,
    FocusedAnalysisPacket,
    FocusedNodeSummary,
    GlobalContext,
    RecommendationReport,
    ScenarioEvaluation,
    SupportedStatement,
)
from archcompass.domain.errors import ModelOutputValidationError, ProviderError
from archcompass.domain.policy import PolicyEvidenceSummary

Item = TypeVar("Item", bound=BaseModel)


def _object_mapping(value: object) -> dict[str, object] | None:
    if not isinstance(value, Mapping):
        return None
    source = cast(Mapping[object, object], value)
    return {str(key): item for key, item in source.items()}


class DesignForceList(RootModel[list[DesignForce]]):
    root: list[DesignForce] = Field(min_length=1, max_length=8)


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
    _PROMPTS: ClassVar[dict[str, str]] = {
        "discover_design_forces": "discover-design-forces:v2",
        "cluster_design_forces": "cluster-design-forces:v1",
        "plan_atlas_queries": "plan-cluster-atlas-queries:v3",
        "analyze_concern_cluster": "analyze-concern:v3",
        "generate_alternatives": "generate-alternatives:v2",
        "evaluate_scenarios": "evaluate-scenarios:v2",
        "synthesize_recommendation": "synthesize-recommendation:v2",
    }

    def __init__(self, config: ReasoningModelConfig) -> None:
        self._config = config
        self._repair_actions: list[dict[str, object]] = []

    @property
    def model_identity(self) -> str:
        return f"{self._config.provider}:{self._config.model}"

    @property
    def prompt_identities(self) -> list[str]:
        return list(self._PROMPTS.values())

    def prompt_identity(self, task: str) -> str:
        return self._PROMPTS[task]

    def consume_repair_actions(self) -> list[dict[str, object]]:
        actions = list(self._repair_actions)
        self._repair_actions.clear()
        return actions

    def discover_design_forces(self, context: GlobalContext) -> list[DesignForce]:
        return self._complete(
            "Discover the important software architecture design forces. "
            "Separate confirmed facts from assumptions.",
            context,
            DesignForceList,
        ).root

    def cluster_design_forces(
        self, context: GlobalContext, forces: list[DesignForce]
    ) -> list[ConcernCluster]:
        return self._complete(
            "Group all supplied design forces into one to four focused concern clusters. "
            "Every force ID must appear exactly once and no other force ID may appear.",
            {
                "context": context.model_dump(mode="json"),
                "forces": [force.model_dump(mode="json") for force in forces],
            },
            ConcernClusterList,
        ).root

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
            "Return exactly one query plan keyed by each supplied cluster ID. Plan only "
            "focused, bounded atlas queries. Queries in one plan are executed as a batch: "
            "a search result from that plan is not available to another query until the next "
            "iteration. Node-based queries may therefore use only the corresponding cluster's "
            f"allowed node IDs from prior iterations: {allowed_node_ids}. Never invent or infer "
            "a node ID from a symbol name. When a cluster has no allowed node IDs, use only "
            "ID-free discovery queries: repository_summary, search_nodes, hotspots, or "
            "cyclic_components. Prefer documented hotspot metrics such as "
            "reverse_dependency_reach, fan_in, or cycle_size.",
            payload,
            ClusterQueryPlanList,
        ).root

    def analyze_concern_cluster(
        self,
        context: GlobalContext,
        packet: FocusedAnalysisPacket,
        *,
        validation_feedback: str | None = None,
    ) -> ConcernAnalysis:
        allowed_node_ids = sorted(packet.surfaced_node_ids)
        allowed_policy_ids = sorted(item.policy.id for item in packet.policies)
        retry_instruction = (
            ""
            if validation_feedback is None
            else (
                " This is one bounded correction attempt. The previous analysis was rejected "
                "by semantic evidence validation. Correct the complete analysis using this "
                f"feedback: {validation_feedback}"
            )
        )
        return self._complete(
            "Analyze exactly one concern cluster. "
            f"Set cluster_id exactly to {packet.cluster.cluster_id!r}. "
            f"Allowed atlas node IDs: {allowed_node_ids or ['none']}. "
            f"Allowed policy IDs: {allowed_policy_ids or ['none']}. "
            "Use no other evidence IDs. When no atlas IDs are allowed, do not classify any "
            "finding as a repository observation. When no policy IDs are allowed, do not "
            "classify any finding as policy guidance. A repository observation must cite an "
            "allowed node ID and copy a source location that lies within that node's surfaced "
            "location. If exact repository support is unavailable, omit the finding or classify "
            "it as an advisor inference without an atlas reference."
            f"{retry_instruction}",
            {"context": context.model_dump(mode="json"), "packet": packet.model_dump(mode="json")},
            ConcernAnalysis,
        )

    def generate_alternatives(
        self, context: GlobalContext, analyses: list[ConcernAnalysis]
    ) -> list[CaseAlternative]:
        return self._complete(
            "Generate between two and five credible alternatives. Include preserving the "
            "current design when justified; do not assume a new abstraction is required.",
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
        return self._complete(
            "Evaluate every alternative against at least one future scenario and its "
            "assumptions. Use the stated future changes when present. If none are stated, "
            "evaluate the baseline scenario that requirements remain stable and no credible "
            "variation appears.",
            {
                "context": context.model_dump(mode="json"),
                "alternatives": [item.model_dump(mode="json") for item in alternatives],
                "analyses": [item.model_dump(mode="json") for item in analyses],
            },
            ScenarioList,
        ).root

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
        *,
        validation_feedback: str | None = None,
    ) -> RecommendationReport:
        allowed_node_ids = sorted(
            {node_id for packet in packets for node_id in packet.surfaced_node_ids}
        )
        allowed_policy_ids = sorted(
            {retrieved.policy.id for packet in packets for retrieved in packet.policies}
        )
        policy_evidence_by_id: dict[str, PolicyEvidenceSummary] = {}
        for packet in packets:
            for retrieved in packet.policies:
                policy_evidence_by_id.setdefault(
                    retrieved.policy.id,
                    PolicyEvidenceSummary.from_retrieved(retrieved),
                )
        retry_instruction = (
            ""
            if validation_feedback is None
            else (
                " This is one bounded correction attempt after semantic validation failed. "
                "Preserve the recommendation unless an evidence correction requires changing "
                "it, return the complete report, and fix every reported error. "
                f"Validation feedback: {validation_feedback}"
            )
        )
        report = self._complete(
            "Synthesize one coherent recommendation and ADR. Never invent evidence references. "
            "Populate every required report section. Even when no code change is recommended, "
            "provide concrete steps to preserve the local design and record the decision. "
            "First create the report's classified claims with stable claim_id values. Every "
            "semantically different claim must have a globally unique claim_id across all "
            "report sections. Never reuse a claim_id for different text, classification, atlas "
            "references, or policy IDs. If evidence_appendix repeats a claim from another "
            "section, copy the entire claim object exactly. "
            "Every "
            "SupportedStatement must include a non-empty supporting_claim_ids array containing "
            "one or more exact claim_id values present in that same report; never omit this "
            "field and never return an empty array. "
            "Use these exact report-section classifications: confirmed_context only "
            "confirmed_user_requirement; assumptions_and_unresolved_questions only "
            "scenario_assumption; repository_observations only repository_observation; "
            "relevant_policies only policy_guidance. "
            f"Allowed atlas node IDs: {allowed_node_ids or ['none']}. "
            f"Allowed policy IDs: {allowed_policy_ids or ['none']}. "
            "Use no other evidence IDs. When no atlas IDs are allowed, repository_observations "
            "must be empty and no claim may contain an atlas reference. Policy-guidance claims "
            "must reference at least one allowed policy ID."
            f"{retry_instruction}",
            {
                "case": case.model_dump(mode="json"),
                "context": context.model_dump(mode="json"),
                "forces": [item.model_dump(mode="json") for item in forces],
                "clusters": [item.model_dump(mode="json") for item in clusters],
                "analyses": [item.model_dump(mode="json") for item in analyses],
                "alternatives": [item.model_dump(mode="json") for item in alternatives],
                "scenarios": [item.model_dump(mode="json") for item in scenarios],
                "packets": [item.model_dump(mode="json") for item in packets],
            },
            RecommendationReport,
            normalization_context={
                "important_design_forces": [
                    item.model_dump(mode="json") for item in forces
                ],
                "alternatives_considered": [
                    item.model_dump(mode="json") for item in alternatives
                ],
                "scenario_analysis": [
                    item.model_dump(mode="json") for item in scenarios
                ],
                "policy_evidence": [
                    item.model_dump(mode="json")
                    for item in policy_evidence_by_id.values()
                ],
            },
        )
        return self._link_report_support(report)

    def _complete(
        self,
        instruction: str,
        payload: BaseModel | Mapping[str, object],
        output_type: type[Item],
        *,
        normalization_context: Mapping[str, object] | None = None,
        schema_override: Mapping[str, object] | None = None,
    ) -> Item:
        data = payload.model_dump(mode="json") if isinstance(payload, BaseModel) else payload
        messages = [
            {
                "role": "system",
                "content": (
                    "You are ArchCompass. Return only data matching the supplied JSON "
                    "schema. Treat policies as guidance, not automatic violations."
                ),
            },
            {"role": "user", "content": f"{instruction}\n\nInput:\n{data}"},
        ]
        try:
            content = self._normalize_output(
                output_type,
                self._chat(
                    output_type,
                    messages,
                    schema_override=schema_override,
                ),
                normalization_context=normalization_context,
            )
            try:
                candidate = output_type.model_validate_json(content)
            except ValidationError as first_error:
                validation_errors = str(first_error)
            else:
                return candidate
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
            return candidate
        except (httpx.HTTPError, KeyError, TypeError, ValueError) as error:
            raise ProviderError(f"Ollama reasoning request failed: {error}") from error

    def _link_report_support(
        self,
        report: RecommendationReport,
    ) -> RecommendationReport:
        slots = self._statement_slots(report)
        claims_by_id = {
            claim.claim_id: claim
            for claim in [
                *report.confirmed_context,
                *report.assumptions_and_unresolved_questions,
                *report.repository_observations,
                *report.relevant_policies,
                *report.evidence_appendix,
            ]
        }
        payload = {
            "claims": [
                claim.model_dump(mode="json") for claim in claims_by_id.values()
            ],
            "statements": [
                {
                    "statement_key": key,
                    "text": statement.text,
                    "classification": statement.classification,
                }
                for key, statement in slots
            ],
        }
        instruction = (
            "Link every statement to one or more claims that directly support it. "
            "Return every statement_key exactly once. Use only exact claim_id values from "
            "the supplied claims. Do not create or rewrite claims or statements."
        )
        schema = self._support_plan_schema(
            statement_keys={key for key, _ in slots},
            claim_ids=set(claims_by_id),
            statement_count=len(slots),
        )
        plan = self._complete(
            instruction,
            payload,
            StatementSupportPlan,
            schema_override=schema,
        ).root
        errors = self._support_plan_errors(plan, slots, set(claims_by_id))
        if errors:
            plan = self._complete(
                instruction
                + " Correct these prior mapping errors: "
                + "; ".join(errors),
                payload,
                StatementSupportPlan,
                schema_override=schema,
            ).root
            errors = self._support_plan_errors(plan, slots, set(claims_by_id))
        if errors:
            raise ModelOutputValidationError(
                "Ollama returned an invalid statement support plan: "
                + "; ".join(errors)
            )
        assignments = {
            item.statement_key: item.supporting_claim_ids for item in plan
        }
        linked = self._apply_statement_support(report, assignments)
        self._repair_actions.append(
            {
                "kind": "linked_report_statement_support",
                "previous_support": {
                    key: statement.supporting_claim_ids
                    for key, statement in slots
                },
                "assignments": assignments,
            }
        )
        return linked

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
            return statement.model_copy(
                update={"supporting_claim_ids": assignments[key]}
            )

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
    ) -> str:
        response = httpx.post(
            f"{self._config.base_url.rstrip('/')}/api/chat",
            json={
                "model": self._config.model,
                "stream": False,
                "format": (
                    schema_override
                    if schema_override is not None
                    else output_type.model_json_schema()
                ),
                "options": {"num_predict": self._config.max_output_tokens},
                "messages": messages,
            },
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
        appendix = (
            list(cast(list[object], raw_appendix))
            if isinstance(raw_appendix, list)
            else []
        )
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
                        digest = sha256(
                            f"{claim_id}\0{serialized}\0{counter}".encode()
                        ).hexdigest()
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
