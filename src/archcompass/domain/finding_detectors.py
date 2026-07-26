"""Detect structural patterns that could make a policy relevant.

A detector answers "is this shape present, and how do I know", never "is this wrong".
Materiality depends on the case, so every candidate produced here is an input to judgement
rather than a verdict, and "this does not matter" stays a first-class answer downstream
(master plan 8A).

Detection reads the graph rather than node attributes alone. A pattern established by
looking at one node in isolation is nearly always a lint; architecture is about placement,
so the evidence is a relationship — what implements what, what depends on it, what would
have to change with it.

This is domain code, beside `atlas_metrics`, because it is a pure derivation over an
`Atlas` with no I/O and no vendor in sight. Behind a port it would be an interface with a
single implementation hiding nothing — the shape this very module reports.
"""

from __future__ import annotations

from collections import defaultdict

from archcompass.domain.atlas import (
    Atlas,
    AtlasEdge,
    AtlasNode,
    EdgeType,
    FindingCandidate,
    FindingMeasurement,
    FindingParticipant,
    FindingPattern,
    MetricNature,
    NodeType,
    SourceLocation,
)

#: What counting implementations from a static parse cannot establish. Stated on every
#: candidate: a detector claiming no limitations claims the static view is complete.
_SOLE_IMPLEMENTATION_LIMITS = (
    "Counted from statically resolvable inheritance and structural conformance in this "
    "snapshot. Implementations registered dynamically, supplied by another repository, or "
    "planned but unwritten are not visible, and an abstraction may be deliberate at a port "
    "boundary where only one adapter exists today."
)


def _location(node: AtlasNode) -> SourceLocation | None:
    if node.start_line is None or node.end_line is None:
        return None
    return SourceLocation(path=node.path, start_line=node.start_line, end_line=node.end_line)


def detect_finding_candidates(atlas: Atlas) -> list[FindingCandidate]:
    """Every candidate the MVP catalogue can find in one atlas.

    One detector today (master plan 8A.3). Consumers call this rather than the detector
    directly, so adding the second pattern is a line here instead of a change at every
    call site.
    """

    nodes = {node.atlas_id: node for node in atlas.nodes}
    return sole_implementation_candidates(nodes, atlas.edges)


def sole_implementation_candidates(
    nodes: dict[str, AtlasNode],
    edges: list[AtlasEdge],
) -> list[FindingCandidate]:
    """Abstractions with exactly one implementation behind them.

    The shape an agent produces when it reaches for an interface at a decision point that
    had no credible variation: a boundary is added, nothing is hidden behind it, and every
    caller now traverses indirection to reach one concrete thing.

    Deliberately not a violation. A port with a single adapter is often correct — this
    codebase does it on purpose — so the candidate reports the count and the surrounding
    dependency shape and leaves the verdict to a stage that can see the case. Detecting
    only the opposite pattern would make the advisor an advocate for abstraction, which is
    the failure it exists to correct.
    """

    implementations: dict[str, list[str]] = defaultdict(list)
    for edge in edges:
        if edge.edge_type in (EdgeType.IMPLEMENTS, EdgeType.INHERITS):
            implementations[edge.target_id].append(edge.source_id)

    dependants: dict[str, int] = defaultdict(int)
    for edge in edges:
        if edge.edge_type in (EdgeType.IMPORTS, EdgeType.REFERENCES, EdgeType.CALLS):
            dependants[edge.target_id] += 1

    candidates: list[FindingCandidate] = []
    for interface_id, implementor_ids in sorted(implementations.items()):
        interface = nodes.get(interface_id)
        if interface is None or interface.node_type is not NodeType.INTERFACE:
            continue
        # An abstraction extending another abstraction is composition, not implementation.
        # Counting it produced a live false positive: `ReportConversationReasoner` was
        # reported as having exactly one implementation, which was the protocol that
        # extends it. Excluding abstractions can leave a parent with none resolvable, and
        # it then drops out rather than being described wrongly — the safer of the two
        # failures for a stage whose output is advice.
        unique = sorted(
            item
            for item in {item for item in implementor_ids if item in nodes}
            if nodes[item].node_type is not NodeType.INTERFACE
        )
        if len(unique) != 1:
            continue
        implementor = nodes[unique[0]]

        participants = [
            FindingParticipant(
                node_id=interface.atlas_id,
                qualified_name=interface.qualified_name,
                location=_location(interface),
                role="Declares the abstraction.",
            ),
            FindingParticipant(
                node_id=implementor.atlas_id,
                qualified_name=implementor.qualified_name,
                location=_location(implementor),
                role="The only implementation of it in this repository.",
            ),
        ]
        relationships = [
            edge
            for edge in edges
            if edge.target_id == interface_id and edge.source_id == implementor.atlas_id
        ]
        candidates.append(
            FindingCandidate(
                pattern=FindingPattern.SOLE_IMPLEMENTATION,
                summary=(
                    f"{interface.qualified_name} is implemented only by "
                    f"{implementor.qualified_name}."
                ),
                participants=participants,
                measurements=[
                    FindingMeasurement(
                        name="implementations",
                        value=1,
                        unit="implementations",
                        nature=MetricNature.MEASUREMENT,
                        definition=(
                            "Statically resolvable implementations or subclasses of the "
                            "abstraction in this snapshot."
                        ),
                        limitations=_SOLE_IMPLEMENTATION_LIMITS,
                    ),
                    FindingMeasurement(
                        name="dependants_of_abstraction",
                        value=float(dependants.get(interface_id, 0)),
                        unit="references",
                        nature=MetricNature.STRUCTURAL_PROXY,
                        definition=(
                            "Imports, references and calls that reach the abstraction, as a "
                            "proxy for how much code the indirection currently sits in front of."
                        ),
                        limitations=(
                            "Counts static references only, and a reference is not evidence "
                            "that the indirection is or is not earning its place."
                        ),
                    ),
                ],
                relationships=relationships,
                limitations=_SOLE_IMPLEMENTATION_LIMITS,
            )
        )
    return candidates
