"""Repository atlas contracts and validated query language."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Annotated, Literal

from pydantic import Field

from archcompass.domain.base import DomainModel, new_id, utc_now


class NodeType(StrEnum):
    REPOSITORY = "repository"
    PACKAGE = "package"
    MODULE = "module"
    CLASS = "class"
    FUNCTION = "function"
    METHOD = "method"
    INTERFACE = "interface"
    TEST_MODULE = "test_module"
    TEST_FUNCTION = "test_function"
    CONFIGURATION = "configuration"


class EdgeType(StrEnum):
    CONTAINS = "contains"
    IMPORTS = "imports"
    CALLS = "calls"
    INHERITS = "inherits"
    IMPLEMENTS = "implements"
    REFERENCES = "references"
    TESTS = "tests"
    CONFIGURES = "configures"


class SourceLocation(DomainModel):
    path: str
    start_line: int = Field(ge=1)
    end_line: int = Field(ge=1)


class AtlasNode(DomainModel):
    atlas_id: str
    path: str
    symbol_name: str
    qualified_name: str
    node_type: NodeType
    start_line: int | None = Field(default=None, ge=1)
    end_line: int | None = Field(default=None, ge=1)
    parent_id: str | None = None
    is_public: bool | None = None
    has_docstring: bool = False
    language: Literal["python", "configuration"] = "python"
    parser_version: str


class AtlasEdge(DomainModel):
    edge_id: str
    source_id: str
    target_id: str
    edge_type: EdgeType
    confidence: float = Field(ge=0, le=1)
    location: SourceLocation | None = None


class LocalStructuralMetrics(DomainModel):
    physical_lines: int = 0
    logical_statements: int = 0
    branch_count: int = 0
    maximum_nesting_depth: int = 0
    parameter_count: int = 0
    public_symbol_count: int = 0
    imported_module_count: int = 0
    outgoing_static_calls: int = 0
    incoming_known_callers: int = 0


class DependencyMetrics(DomainModel):
    fan_in: int = 0
    fan_out: int = 0
    direct_dependencies: list[str] = Field(default_factory=list[str])
    direct_dependants: list[str] = Field(default_factory=list[str])
    forward_dependency_reach: int = 0
    reverse_dependency_reach: int = 0
    dependency_depth: int = 0
    strongly_connected_component: str | None = None
    cycle_size: int = 0
    interface_implementations: int = 0
    public_interface_callers: int = 0
    directly_associated_tests: int = 0
    transitively_affected_test_modules: int = 0


class ChangeAmplificationMetrics(DomainModel):
    likely_affected_modules: int = 0
    public_interfaces_crossed: int = 0
    coordinated_implementations: int = 0
    configuration_locations: int = 0
    reverse_neighbourhood_tests: int = 0


class CognitiveScopeMetrics(DomainModel):
    dependency_neighbourhood_modules: int = 0
    symbols_in_representative_path: int = 0
    abstraction_boundaries: int = 0
    related_configuration_locations: int = 0
    local_control_flow_complexity: int = 0
    public_api_surface: int = 0


class MetricProfile(DomainModel):
    node_id: str
    local: LocalStructuralMetrics = Field(default_factory=LocalStructuralMetrics)
    dependency: DependencyMetrics = Field(default_factory=DependencyMetrics)
    change_amplification: ChangeAmplificationMetrics = Field(
        default_factory=ChangeAmplificationMetrics
    )
    cognitive_scope: CognitiveScopeMetrics = Field(default_factory=CognitiveScopeMetrics)


class ObscuritySignal(DomainModel):
    code: str
    message: str
    node_id: str
    location: SourceLocation | None = None


class AtlasVersion(DomainModel):
    version_id: str = Field(default_factory=lambda: new_id("atlas"))
    repository_identity: str
    root_path: str
    git_commit_sha: str | None = None
    content_fingerprint: str
    parser_version: str
    analysis_config_hash: str
    created_at: datetime = Field(default_factory=utc_now)


class Atlas(DomainModel):
    version: AtlasVersion
    nodes: list[AtlasNode]
    edges: list[AtlasEdge]
    metrics: list[MetricProfile]
    signals: list[ObscuritySignal] = Field(default_factory=list[ObscuritySignal])


class RepositorySummaryQuery(DomainModel):
    kind: Literal["repository_summary"]
    limit: int = Field(default=20, ge=1, le=100)


class SubsystemSummaryQuery(DomainModel):
    kind: Literal["subsystem_summary"]
    node_id: str
    limit: int = Field(default=20, ge=1, le=100)


class NodeDetailsQuery(DomainModel):
    kind: Literal["node_details"]
    node_id: str


class RelationQuery(DomainModel):
    kind: Literal[
        "direct_dependencies",
        "direct_dependants",
        "known_callers",
        "implementations",
        "related_tests",
    ]
    node_id: str
    limit: int = Field(default=30, ge=1, le=100)


class NeighbourhoodQuery(DomainModel):
    kind: Literal["forward_neighbourhood", "reverse_neighbourhood"]
    node_id: str
    depth: int = Field(default=2, ge=1, le=5)
    limit: int = Field(default=30, ge=1, le=100)


class ShortestPathQuery(DomainModel):
    kind: Literal["shortest_dependency_path"]
    source_id: str
    target_id: str


class CyclesQuery(DomainModel):
    kind: Literal["cyclic_components"]
    limit: int = Field(default=30, ge=1, le=100)


class HotspotsQuery(DomainModel):
    kind: Literal["hotspots"]
    metric: str
    limit: int = Field(default=10, ge=1, le=100)


class SearchNodesQuery(DomainModel):
    kind: Literal["search_nodes"]
    terms: list[str] = Field(min_length=1, max_length=10)
    limit: int = Field(default=20, ge=1, le=100)


class SourceExcerptQuery(DomainModel):
    kind: Literal["source_excerpt"]
    node_id: str
    context_lines: int = Field(default=3, ge=0, le=20)
    max_lines: int = Field(default=80, ge=1, le=200)


AtlasQuery = Annotated[
    RepositorySummaryQuery
    | SubsystemSummaryQuery
    | NodeDetailsQuery
    | RelationQuery
    | NeighbourhoodQuery
    | ShortestPathQuery
    | CyclesQuery
    | HotspotsQuery
    | SearchNodesQuery
    | SourceExcerptQuery,
    Field(discriminator="kind"),
]


class AtlasQueryPlan(DomainModel):
    iteration: int = Field(ge=1, le=10)
    rationale: str
    queries: list[AtlasQuery] = Field(max_length=20)


class SourceExcerpt(DomainModel):
    node_id: str
    location: SourceLocation
    text: str


class AtlasQueryResult(DomainModel):
    query: AtlasQuery
    node_ids: list[str] = Field(default_factory=list[str])
    summary: str = ""
    excerpts: list[SourceExcerpt] = Field(default_factory=list[SourceExcerpt])
