"""Ollama REST adapters with schema-constrained structured outputs."""

from __future__ import annotations

import math
from collections.abc import Callable, Mapping
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
    OLLAMA_STAGE_PROMPTS,
    PLAN_ATLAS_QUERIES,
    REPAIR_CONVERSATION_ANSWER,
    REPAIR_RECOMMENDATION_PROPOSAL,
    SUMMARIZE_REPORT_CONVERSATION,
    SYNTHESIZE_RECOMMENDATION,
    PromptContract,
)
from archcompass.configuration import EmbeddingModelConfig, ReasoningModelConfig
from archcompass.domain.base import canonical_json
from archcompass.domain.case import ArchitectureCase, CaseAlternative
from archcompass.domain.consultation import (
    ClusterQueryPlan,
    ConcernAnalysis,
    ConcernCluster,
    DesignForce,
    FocusedAnalysisPacket,
    FocusedNodeSummary,
    GlobalContext,
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
from archcompass.domain.proposals import AvailableClaim, ProposedRecommendation
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

    @property
    def model_identity(self) -> str:
        return f"{self._config.provider}:{self._config.model}"

    def prompt_identity(self, task: ReasoningTask) -> str:
        return self._PROMPTS[task]

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

    def propose_recommendation(
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
        available_claims: list[AvailableClaim],
        cluster_refs: dict[str, str],
    ) -> ProposedRecommendation:
        del clusters, packets  # Reachable only through the supplied handles.
        return self._complete(
            SYNTHESIZE_RECOMMENDATION,
            {
                "case": case.model_dump(mode="json"),
                "context": context.model_dump(mode="json"),
                "design_forces": [item.model_dump(mode="json") for item in forces],
                "concern_analyses": [item.model_dump(mode="json") for item in analyses],
                "alternatives": [item.model_dump(mode="json") for item in alternatives],
                "scenarios": [item.model_dump(mode="json") for item in scenarios],
                "available_claims": [item.model_dump(mode="json") for item in available_claims],
                "concern_clusters": [
                    {"cluster_ref": ref, "title": title}
                    for ref, title in sorted(cluster_refs.items())
                ],
            },
            ProposedRecommendation,
            runtime_instruction=self._proposal_instruction(available_claims, cluster_refs),
            schema_override=self._proposal_schema(
                claim_refs={item.ref for item in available_claims},
                cluster_refs=set(cluster_refs),
            ),
        )

    def repair_recommendation_proposal(
        self,
        proposal: ProposedRecommendation,
        errors: list[str],
        *,
        available_claims: list[AvailableClaim],
        cluster_refs: dict[str, str],
    ) -> ProposedRecommendation:
        return self._complete(
            REPAIR_RECOMMENDATION_PROPOSAL,
            {
                "proposal": proposal.model_dump(mode="json"),
                "errors": errors,
                "available_claims": [item.model_dump(mode="json") for item in available_claims],
                "concern_clusters": [
                    {"cluster_ref": ref, "title": title}
                    for ref, title in sorted(cluster_refs.items())
                ],
            },
            ProposedRecommendation,
            runtime_instruction=self._proposal_instruction(available_claims, cluster_refs),
            schema_override=self._proposal_schema(
                claim_refs={item.ref for item in available_claims},
                cluster_refs=set(cluster_refs),
            ),
            allow_repair=False,
        )

    @staticmethod
    def _proposal_instruction(
        available_claims: list[AvailableClaim],
        cluster_refs: dict[str, str],
    ) -> str:
        by_cluster: dict[str, list[str]] = {ref: [] for ref in cluster_refs}
        unscoped: list[str] = []
        for claim in available_claims:
            if claim.cluster_ref in by_cluster:
                by_cluster[claim.cluster_ref].append(claim.ref)
            else:
                unscoped.append(claim.ref)
        return (
            f"Allowed concern cluster handles: {sorted(cluster_refs)}. "
            f"Evidence claim handles by cluster: {by_cluster}. "
            f"Case-context claim handles usable anywhere: {unscoped or ['none']}. "
            "Every cluster handle must appear on at least one finding, and each finding "
            "must cite at least one evidence claim handle from its own cluster."
        )

    @staticmethod
    def _proposal_schema(
        *,
        claim_refs: set[str],
        cluster_refs: set[str],
    ) -> dict[str, object]:
        """Constrain every reference to a supplied handle so none can be invented."""

        schema = ProposedRecommendation.model_json_schema()
        definitions = _object_mapping(schema.get("$defs"))
        if definitions is None:
            return schema

        def constrain(
            definition_name: str,
            field: str,
            constraint: Mapping[str, object],
        ) -> None:
            definition = _object_mapping(definitions.get(definition_name))
            properties = None if definition is None else _object_mapping(
                definition.get("properties")
            )
            if properties is None or field not in properties:
                return
            properties[field] = dict(constraint)
            definition["properties"] = properties  # type: ignore[index]
            definitions[definition_name] = definition

        claim_list: Mapping[str, object] = {
            "type": "array",
            "minItems": 1,
            "items": {"type": "string", "enum": sorted(claim_refs)},
        }
        constrain("ProposedStatement", "claim_refs", claim_list)
        constrain("ProposedFinding", "claim_refs", claim_list)
        cluster_choice: Mapping[str, object] = {
            "type": "string",
            "enum": sorted(cluster_refs),
        }
        constrain("ProposedFinding", "cluster_ref", cluster_choice)
        schema["$defs"] = definitions
        return schema

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
            content = self._chat(
                output_type,
                messages,
                schema_override=schema_override,
                think=think,
                temperature=temperature,
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
            repaired = self._chat(
                output_type,
                repair_messages,
                schema_override=schema_override,
                think=think,
                temperature=temperature,
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
