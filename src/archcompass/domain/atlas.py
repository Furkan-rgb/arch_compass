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
    #: Which pass named both endpoints. `parse` is the static AST resolution that always
    #: runs; `types` is the optional type-aware resolver. Defaulted rather than required, so
    #: an atlas stored before this field existed reads back as exactly what it was — every
    #: edge in it came from the parse.
    resolved_by: Literal["parse", "types"] = "parse"
    #: Which conformance rule admitted this edge, on typed `IMPLEMENTS` edges only. `strict`
    #: is the type checker's own subtyping question; `structural` is the relaxed rule that
    #: credits an adapter narrowing a parameter. Absent everywhere else, because a parse
    #: edge was never judged by either rule and recording a default would claim it was.
    conformance: Literal["strict", "structural"] | None = None


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


class NamedMention(DomainModel):
    """One name this module refers to, and where it refers to it.

    The lines were not recorded before, and their absence reached a reader. A scattered
    concept's participants are whole modules, so the detector had no span to give them and
    wrote line 1 — which in a Python file is the docstring. Asked to show a vendor name that
    had leaked into five modules, the advisor was handed five docstrings, none containing it,
    and correctly said it could not show the leak. The evidence was never taken down.

    Every line, not just the first: "named once in an import" and "named in eleven places
    through the request path" are different findings, and a count is what tells them apart.
    """

    name: str = Field(min_length=1)
    #: Ascending, deduplicated, and never empty — a mention with no site is not a mention.
    lines: list[int] = Field(min_length=1)

    @property
    def first(self) -> int:
        return self.lines[0]


class DefinedConstant(DomainModel):
    """One module-level constant, and enough of its value to compare two of them.

    The value is fingerprinted rather than stored. Two modules holding the same literal is
    the fact detection needs; the literal itself may be a credential, and an atlas that
    copied it would put it in every prompt and every stored review.
    """

    name: str = Field(min_length=1)
    #: Empty when the value is not a literal — a computed constant is still a name two
    #: modules share, but nothing can be claimed about whether they agree.
    value_fingerprint: str = ""
    line: int = Field(ge=1)


class ModuleFacts(DomainModel):
    """What one module states and what it names, as facts a detector can derive from.

    Separate from `AtlasNode` because these are properties of a file's whole text rather
    than of a symbol, and because the repetition detectors need to compare modules against
    each other — a fact stored per symbol cannot answer "which modules share this".
    """

    node_id: str = Field(min_length=1)
    path: str = Field(min_length=1)
    qualified_name: str = Field(min_length=1)
    constants: list[DefinedConstant] = Field(default_factory=list[DefinedConstant])
    #: Modules of *this* repository whose name this module's text mentions, in an
    #: identifier or a string literal, each with the lines it appears on. Bounded to names
    #: the repository actually owns, so this is a small set rather than a copy of the
    #: file's vocabulary.
    mentions: list[NamedMention] = Field(default_factory=list[NamedMention])

    def mention_of(self, name: str) -> NamedMention | None:
        """Where this module names `name`, or nothing if it does not."""

        return next((item for item in self.mentions if item.name == name), None)


class FindingPattern(StrEnum):
    """Structural shapes a detector can establish from the atlas graph.

    Named for what was observed, never for what should be done about it. Each maps to
    policies the corpus already states, because the corpus is what says which patterns
    are worth detecting at all (master plan 8A.1).

    A closed set rather than a string, because the pattern name is an application-owned key
    that reaches the model as a label (12.0).

    Both directions of master plan 8A.3 are now present, and the distinction between them
    is the point. `SOLE_IMPLEMENTATION` is indirection that may be hiding nothing — the
    advice, if any, is *remove it*. The other two are repetition with no owner — the advice,
    if any, is *give this one owner*. An advisor holding only the first becomes an advocate
    for the second, which is the failure this enum exists to keep visible.
    """

    #: An abstraction with exactly one implementation behind it.
    SOLE_IMPLEMENTATION = "sole_implementation"
    #: The same named constant stated in several modules, with no module owning it.
    DUPLICATED_KNOWLEDGE = "duplicated_knowledge"
    #: One module's concern named across modules that have no other reason to know it —
    #: a vendor, a format or a backend whose name has spread beyond the module that owns it.
    SCATTERED_CONCEPT = "scattered_concept"


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
    #: Per-module text facts, for the detectors that compare modules against each other.
    #: An atlas written by an earlier parser has none; `parser_version` makes such an atlas
    #: stale rather than quietly empty, so an absent list is never read as "nothing found".
    module_facts: list[ModuleFacts] = Field(default_factory=list[ModuleFacts])


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


class ReviewContextQuery(DomainModel):
    """The union neighbourhood around several nodes at once, asked for in one question.

    A reader opening a review's map wants the boundaries it reports and enough around them
    to see what they touch. Asked one node at a time — the only way this language offered
    before — the answer to each is the node alone, so every edge leading out of it names a
    neighbour the asker was never given and has to be discarded. What arrives is a set of
    unconnected boxes, which is the opposite of what a map is for.

    Missing ids are not an error here. The nodes come from a review of an atlas that may
    since have been rebuilt, and a reader whose file was renamed should see the rest of the
    map rather than a failure; `node_ids` on the result reports which ones were found, so
    the absence stays visible instead of being smoothed over.
    """

    kind: Literal["review_context"]
    node_ids: list[str] = Field(min_length=1, max_length=40)
    #: Neighbours per requested node, not in total — the bound has to hold per anchor, or a
    #: single densely connected boundary would consume the whole budget and leave the others
    #: as the isolated boxes this query exists to avoid.
    limit: int = Field(default=25, ge=1, le=100)


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
    | SourceExcerptQuery
    | ReviewContextQuery,
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
