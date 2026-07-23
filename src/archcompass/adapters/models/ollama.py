"""Ollama REST adapters with schema-constrained structured outputs."""

from __future__ import annotations

import math
from collections.abc import Mapping
from typing import ClassVar, TypeVar

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
)
from archcompass.domain.errors import ModelOutputValidationError, ProviderError

Item = TypeVar("Item", bound=BaseModel)


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
        "plan_atlas_queries": "plan-cluster-atlas-queries:v2",
        "analyze_concern_cluster": "analyze-concern:v2",
        "generate_alternatives": "generate-alternatives:v2",
        "evaluate_scenarios": "evaluate-scenarios:v2",
        "synthesize_recommendation": "synthesize-recommendation:v2",
    }

    def __init__(self, config: ReasoningModelConfig) -> None:
        self._config = config

    @property
    def model_identity(self) -> str:
        return f"{self._config.provider}:{self._config.model}"

    @property
    def prompt_identities(self) -> list[str]:
        return list(self._PROMPTS.values())

    def prompt_identity(self, task: str) -> str:
        return self._PROMPTS[task]

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
        return self._complete(
            "Return exactly one query plan keyed by each supplied cluster ID. Plan only "
            "focused, bounded atlas queries and use only node IDs already surfaced.",
            payload,
            ClusterQueryPlanList,
        ).root

    def analyze_concern_cluster(
        self, context: GlobalContext, packet: FocusedAnalysisPacket
    ) -> ConcernAnalysis:
        allowed_node_ids = sorted(packet.surfaced_node_ids)
        allowed_policy_ids = sorted(item.policy.id for item in packet.policies)
        return self._complete(
            "Analyze one concern cluster. "
            f"Allowed atlas node IDs: {allowed_node_ids or ['none']}. "
            f"Allowed policy IDs: {allowed_policy_ids or ['none']}. "
            "Use no other evidence IDs. When no atlas IDs are allowed, do not classify any "
            "finding as a repository observation. When no policy IDs are allowed, do not "
            "classify any finding as policy guidance.",
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
    ) -> RecommendationReport:
        allowed_node_ids = sorted(
            {node_id for packet in packets for node_id in packet.surfaced_node_ids}
        )
        allowed_policy_ids = sorted(
            {retrieved.policy.id for packet in packets for retrieved in packet.policies}
        )
        return self._complete(
            "Synthesize one coherent recommendation and ADR. Never invent evidence references. "
            "Populate every required report section. Even when no code change is recommended, "
            "provide concrete steps to preserve the local design and record the decision. "
            "Every substantive SupportedStatement must cite claim IDs present in the report. "
            f"Allowed atlas node IDs: {allowed_node_ids or ['none']}. "
            f"Allowed policy IDs: {allowed_policy_ids or ['none']}. "
            "Use no other evidence IDs. When no atlas IDs are allowed, repository_observations "
            "must be empty and no claim may contain an atlas reference. Policy-guidance claims "
            "must reference at least one allowed policy ID.",
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
        )

    def _complete(
        self,
        instruction: str,
        payload: BaseModel | Mapping[str, object],
        output_type: type[Item],
    ) -> Item:
        data = payload.model_dump(mode="json") if isinstance(payload, BaseModel) else payload
        try:
            response = httpx.post(
                f"{self._config.base_url.rstrip('/')}/api/chat",
                json={
                    "model": self._config.model,
                    "stream": False,
                    "format": output_type.model_json_schema(),
                    "options": {"temperature": self._config.temperature},
                    "messages": [
                        {
                            "role": "system",
                            "content": (
                                "You are ArchCompass. Return only data matching the supplied JSON "
                                "schema. Treat policies as guidance, not automatic violations."
                            ),
                        },
                        {"role": "user", "content": f"{instruction}\n\nInput:\n{data}"},
                    ],
                },
                timeout=self._config.timeout_seconds,
            )
            response.raise_for_status()
            content = response.json()["message"]["content"]
            return output_type.model_validate_json(content)
        except ValidationError as error:
            raise ModelOutputValidationError(
                f"Ollama returned invalid structured output: {error}"
            ) from error
        except (httpx.HTTPError, KeyError, TypeError, ValueError) as error:
            raise ProviderError(f"Ollama reasoning request failed: {error}") from error
