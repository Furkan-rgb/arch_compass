"""The few atlas-derived facts more than one detector needs, derived once.

Not a home for everything a detector computes. What belongs here is narrow and has a test:
a fact that two or more patterns ask about, where each of them asking separately has already
gone wrong. Everything a single pattern needs stays with that pattern, because a measurement
that means nothing to its neighbours is not shared knowledge — it is that detector's own.

The three below earned their place by drifting apart.

`test_owned` had three definitions in this module and disagreed with itself. One asked
whether a class's path was a test module's, one asked the node's type, one asked both, and
the detector that most needed it — the one counting how far a concept's name had spread —
did not ask at all, and reported thirty-one modules naming a vendor when twenty-two of them
were tests.

`reaching` was walked twice over the whole edge list for the same question asked two ways,
and the answer to "what depends on this" then disagreed with the toolbox that exists to
name them.

`implementations` was walked a third time. It is the same index the sole-implementation
detector selects on and the same one a candidate reports.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from archcompass.analysis.atlas import (
    DEPENDS_ON_EDGES,
    IMPLEMENTS_EDGES,
    Atlas,
    AtlasEdge,
    AtlasNode,
    NodeType,
)


@dataclass(frozen=True, slots=True)
class RepositoryFacts:
    """What the detectors know about one repository before any of them looks at a pattern."""

    #: Every node that lives in the test suite, by id.
    #:
    #: Membership is by containing file rather than by node type, because a helper class or
    #: a plain function written inside a test file is recorded as a class or a function like
    #: any other — and code in a test file is test code whatever the parser called it.
    test_owned: frozenset[str]

    #: Incoming imports, references and calls, by the id of the node they reach.
    #:
    #: The edges themselves rather than a count. A count is what a judgement was given
    #: before, and it sent it looking for names the atlas already held.
    reaching: Mapping[str, Sequence[AtlasEdge]]

    #: The ids of everything that implements or subclasses a node, by that node's id.
    implementations: Mapping[str, Sequence[str]]

    @classmethod
    def over(
        cls, nodes: Mapping[str, AtlasNode], edges: Sequence[AtlasEdge]
    ) -> RepositoryFacts:
        test_paths = {
            node.path for node in nodes.values() if node.node_type is NodeType.TEST_MODULE
        }
        reaching: defaultdict[str, list[AtlasEdge]] = defaultdict(list)
        implementations: defaultdict[str, list[str]] = defaultdict(list)
        for edge in edges:
            if edge.edge_type in DEPENDS_ON_EDGES:
                reaching[edge.target_id].append(edge)
            elif edge.edge_type in IMPLEMENTS_EDGES:
                implementations[edge.target_id].append(edge.source_id)
        return cls(
            test_owned=frozenset(
                node.atlas_id
                for node in nodes.values()
                if node.path in test_paths
                or node.node_type in (NodeType.TEST_MODULE, NodeType.TEST_FUNCTION)
            ),
            reaching=dict(reaching),
            implementations=dict(implementations),
        )

    @classmethod
    def of(cls, atlas: Atlas) -> RepositoryFacts:
        return cls.over({node.atlas_id: node for node in atlas.nodes}, atlas.edges)

    def reaches(self, node_id: str) -> Sequence[AtlasEdge]:
        return self.reaching.get(node_id, ())

    def from_tests(self, node_id: str) -> list[AtlasEdge]:
        """The edges into a node whose source is test code, in a stable order.

        A resolved edge rather than a name match, which is the whole reason it is worth
        carrying beside `test_doubles_offering_its_methods`: that one asks whether anything
        is *shaped* like a substitute for this abstraction, and this one asks whether any
        test mentions this abstraction at all. A zero from the first is arguable and says so;
        a zero from this one is an observation about the snapshot.

        It is still not a substitution. A test naming an abstraction may be asserting about
        it rather than standing in for it, and nothing here can tell those apart.
        """

        return sorted(
            (edge for edge in self.reaches(node_id) if edge.source_id in self.test_owned),
            key=lambda edge: (edge.source_id, edge.edge_type.value),
        )
