"""Analysis, retrieval, and model service protocols."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol, TypeVar

from pydantic import BaseModel

from archcompass.domain.atlas import Atlas, AtlasQuery, AtlasQueryPlan, AtlasQueryResult
from archcompass.domain.case import ArchitectureCase, CaseAlternative
from archcompass.domain.consultation import (
    ConcernAnalysis,
    DesignForce,
    FocusedAnalysisPacket,
    GlobalContext,
    RecommendationReport,
    ScenarioEvaluation,
)
from archcompass.domain.policy import (
    PolicyDocument,
    PolicyIndexVersion,
    RetrievedPolicy,
)

StructuredOutput = TypeVar("StructuredOutput", bound=BaseModel)


class RepositoryAnalyzer(Protocol):
    def analyze(self, root: Path) -> Atlas: ...


class SourceReader(Protocol):
    def excerpt(
        self,
        root: Path,
        relative_path: str,
        start_line: int,
        end_line: int,
        *,
        max_lines: int,
    ) -> str: ...


class AtlasQueryService(Protocol):
    def execute(self, atlas: Atlas, query: AtlasQuery) -> AtlasQueryResult: ...


class PolicyIndex(Protocol):
    def rebuild(self, sources: list[Path]) -> PolicyIndexVersion: ...

    def ensure_current(self, sources: list[Path]) -> PolicyIndexVersion: ...

    def current_version(self) -> PolicyIndexVersion | None: ...

    def list_policies(self, version_id: str | None = None) -> list[PolicyDocument]: ...

    def get_policy(self, policy_id: str, version_id: str | None = None) -> PolicyDocument: ...


class PolicyRetriever(Protocol):
    def retrieve(
        self, query: str, *, top_k: int, version_id: str | None = None
    ) -> list[RetrievedPolicy]: ...


class EmbeddingProvider(Protocol):
    @property
    def identity(self) -> tuple[str, str, int]: ...

    def embed(self, texts: list[str]) -> list[list[float]]: ...


class ReasoningProvider(Protocol):
    @property
    def model_identity(self) -> str: ...

    @property
    def prompt_identities(self) -> list[str]: ...

    def discover_design_forces(self, context: GlobalContext) -> list[DesignForce]: ...

    def plan_atlas_queries(
        self,
        context: GlobalContext,
        forces: list[DesignForce],
        *,
        iteration: int,
        prior_results: list[AtlasQueryResult],
    ) -> AtlasQueryPlan: ...

    def analyze_concern_cluster(
        self, context: GlobalContext, packet: FocusedAnalysisPacket
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
        analyses: list[ConcernAnalysis],
        alternatives: list[CaseAlternative],
        scenarios: list[ScenarioEvaluation],
        packets: list[FocusedAnalysisPacket],
    ) -> RecommendationReport: ...
