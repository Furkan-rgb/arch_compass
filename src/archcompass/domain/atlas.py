"""Repository atlas contracts and validated query language."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Annotated, Literal

from pydantic import Field, model_validator

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


class MetricNature(StrEnum):
    """How directly an atlas value represents repository structure."""

    MEASUREMENT = "objective_measurement"
    STRUCTURAL_PROXY = "structural_proxy"


class MetricScope(StrEnum):
    """The structural population used to calculate a metric."""

    LEXICAL_NODE = "lexical_node"
    OWNING_MODULE = "owning_module"
    REVERSE_STATIC_IMPACT_NEIGHBOURHOOD = "reverse_static_impact_neighbourhood"
    BOUNDED_RESOLVED_CALL_CHAIN = "bounded_resolved_call_chain"


class SourceLocation(DomainModel):
    path: str
    start_line: int = Field(ge=1)
    end_line: int = Field(ge=1)

    @model_validator(mode="after")
    def require_ordered_span(self) -> SourceLocation:
        if self.end_line < self.start_line:
            raise ValueError("Source location end line must not precede its start line")
        return self


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
    public_call_targets_in_affected_modules: int = 0
    coordinated_implementations: int = 0
    configuration_locations: int = 0
    reverse_neighbourhood_tests: int = 0


class CognitiveScopeMetrics(DomainModel):
    dependency_neighbourhood_modules: int = 0
    bounded_resolved_call_chain_nodes: int = 0
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
    nature: MetricNature = MetricNature.MEASUREMENT
    definition: str = ""
    limitations: str = ""


class FindingPattern(StrEnum):
    """Structural shapes a detector can establish from the atlas graph.

    Named for what was observed, never for what should be done about it. Each maps to
    policies the corpus already states, because the corpus is what says which patterns
    are worth detecting at all (master plan 8A.1).

    One member, deliberately: the MVP ships one detector (master plan 8A.3). It stays an
    enum rather than a string because the pattern name is an application-owned key that
    reaches the model as a label, and a closed set is how it stays one (12.0). Adding the
    second direction of the catalogue should then be a member and a function, not a
    change of type.
    """

    #: An abstraction with exactly one implementation behind it.
    SOLE_IMPLEMENTATION = "sole_implementation"


class FindingParticipant(DomainModel):
    """One node's part in a candidate, and why it is implicated."""

    node_id: str = Field(min_length=1)
    qualified_name: str = Field(min_length=1)
    location: SourceLocation | None = None
    #: What this participant contributes — the duplicated literal, the implementing
    #: method, the forwarded call. Prose, because the model reads it; never a key.
    role: str = Field(min_length=1)


class FindingMeasurement(DomainModel):
    """One quantity that establishes the pattern, with its own honesty attached."""

    name: str = Field(min_length=1)
    value: float
    unit: str = ""
    nature: MetricNature = MetricNature.MEASUREMENT
    definition: str = ""
    limitations: str = ""


class FindingCandidate(DomainModel):
    """A structural pattern that could make a policy relevant — never a violation.

    N-ary by construction: duplicated knowledge is a fact about a set of modules, and a
    type holding one node would discard the finding while appearing to record it. The
    candidate carries the relationships between its participants too, because a pattern
    judged from nodes in isolation is a lint rather than an architectural finding
    (master plan 8A.2).

    A detector states what it found and how it knows. Whether it matters here is decided
    later, against the case, and "it does not" is a first-class answer.
    """

    candidate_id: str = Field(default_factory=lambda: new_id("cand"), min_length=1)
    pattern: FindingPattern
    summary: str = Field(min_length=1)
    participants: list[FindingParticipant] = Field(min_length=1)
    measurements: list[FindingMeasurement] = Field(default_factory=list[FindingMeasurement])
    #: Edges among the participants, so blast radius is visible without a second lookup.
    relationships: list[AtlasEdge] = Field(default_factory=list[AtlasEdge])
    #: What this detection method cannot see. Always populated: a detector that claims no
    #: limitations is claiming the static view is complete, which it never is.
    limitations: str = Field(min_length=1)

    @property
    def node_ids(self) -> list[str]:
        return [participant.node_id for participant in self.participants]


class AtlasVersion(DomainModel):
    schema_version: int = Field(default=2, ge=1, le=2)
    version_id: str = Field(default_factory=lambda: new_id("atlas"))
    repository_identity: str
    root_path: str
    git_commit_sha: str | None = None
    content_fingerprint: str
    parser_version: str
    analysis_config_hash: str
    created_at: datetime = Field(default_factory=utc_now)


class Atlas(DomainModel):
    schema_version: int = Field(default=2, ge=1, le=2)
    version: AtlasVersion
    nodes: list[AtlasNode]
    edges: list[AtlasEdge]
    metrics: list[MetricProfile]
    signals: list[ObscuritySignal] = Field(default_factory=list[ObscuritySignal])


class RepositoryContentIdentity(DomainModel):
    root_path: str
    content_fingerprint: str
    git_commit_sha: str | None = None
    parser_version: str | None = None
    analysis_config_hash: str | None = None


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


class SignalsQuery(DomainModel):
    kind: Literal["signals"]
    codes: list[str] = Field(default_factory=list[str], max_length=10)
    limit: int = Field(default=20, ge=1, le=100)


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
    | SignalsQuery
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


class AtlasNodeSummary(DomainModel):
    node_id: str
    qualified_name: str
    node_type: NodeType
    path: str
    location: SourceLocation | None = None
    is_public: bool | None = None


class AtlasMetricValue(DomainModel):
    node_id: str
    metric: str
    value: int | float
    rank: int | None = Field(default=None, ge=1)
    nature: MetricNature = MetricNature.MEASUREMENT
    scope: MetricScope = MetricScope.LEXICAL_NODE
    definition: str = ""
    limitations: str = ""


class AtlasSelectionReasonKind(StrEnum):
    OVERVIEW = "overview"
    METRIC_RANK = "metric_rank"
    NAME_MATCH = "name_match"
    RELATION = "relation"
    NEIGHBOURHOOD = "neighbourhood"
    PATH = "path"
    CYCLE = "cycle"
    SIGNAL = "signal"
    EXCERPT = "excerpt"
    EXPLICIT_DETAILS = "explicit_details"


class AtlasSelectionReason(DomainModel):
    kind: AtlasSelectionReasonKind
    explanation: str = Field(min_length=1)
    metric: str | None = None
    related_node_id: str | None = None


class AtlasNodeEvidence(DomainModel):
    """A self-describing, bounded view of one surfaced atlas node."""

    node: AtlasNodeSummary
    reasons: list[AtlasSelectionReason] = Field(default_factory=list[AtlasSelectionReason])
    metrics: list[AtlasMetricValue] = Field(default_factory=list[AtlasMetricValue])
    signals: list[ObscuritySignal] = Field(default_factory=list[ObscuritySignal])


class AtlasRelationshipEvidence(DomainModel):
    """An atlas relationship with resolved endpoint identities."""

    edge_id: str
    edge_type: EdgeType
    source: AtlasNodeSummary
    target: AtlasNodeSummary
    confidence: float = Field(ge=0, le=1)
    location: SourceLocation | None = None


class AtlasOverview(DomainModel):
    """Small deterministic repository map supplied before focused investigation."""

    atlas_version_id: str
    repository_identity: str
    node_count: int = Field(ge=0)
    edge_count: int = Field(ge=0)
    signal_count: int = Field(ge=0)
    node_type_counts: dict[str, int] = Field(default_factory=dict[str, int])
    edge_type_counts: dict[str, int] = Field(default_factory=dict[str, int])
    signal_code_counts: dict[str, int] = Field(default_factory=dict[str, int])
    signals: list[ObscuritySignal] = Field(
        default_factory=list[ObscuritySignal],
        max_length=20,
    )
    top_level_nodes: list[AtlasNodeSummary] = Field(
        default_factory=list[AtlasNodeSummary],
        max_length=20,
    )
    hotspots: list[AtlasNodeEvidence] = Field(
        default_factory=list[AtlasNodeEvidence],
        max_length=12,
    )
    limitations: list[str] = Field(default_factory=list[str])


class AtlasQueryResult(DomainModel):
    query: AtlasQuery
    node_ids: list[str] = Field(default_factory=list[str])
    summary: str = ""
    node_summaries: list[AtlasNodeSummary] = Field(default_factory=list[AtlasNodeSummary])
    metric_values: list[AtlasMetricValue] = Field(default_factory=list[AtlasMetricValue])
    relationships: list[AtlasEdge] = Field(default_factory=list[AtlasEdge])
    test_ids: list[str] = Field(default_factory=list[str])
    signals: list[ObscuritySignal] = Field(default_factory=list[ObscuritySignal])
    excerpts: list[SourceExcerpt] = Field(default_factory=list[SourceExcerpt])
