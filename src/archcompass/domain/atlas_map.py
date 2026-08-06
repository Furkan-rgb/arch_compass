"""The whole repository's structure, compact enough to hand to a conversation stage.

The talking stages are shown the boundaries a review detected and the code under them, and
nothing else — so a question about any module no detector flagged was answered with "I was
not shown that". The review's atlas has always known the answer at the structural level:
which modules exist, what each declares, which module depends on which. This is that
knowledge, folded down to a size a prompt can carry.

It is a map and not evidence. It carries no verdicts, no code and no judgement, so showing
it to a stage that is otherwise scoped — a question discussion running while a first pass
withholds its verdicts — widens nothing that scoping protects.

Trimming is explicit, never silent. A map that quietly dropped a module would read as "that
module does not exist", which is worse than no map at all; every level of degradation
leaves a count behind saying what was folded away.
"""

from __future__ import annotations

from collections import Counter

from pydantic import Field, model_validator

from archcompass.domain.atlas import Atlas, EdgeType, NodeType
from archcompass.domain.base import DomainModel

#: Roughly 10k tokens at the estimator's 4 chars/token — a bounded share of even the
#: smallest provider's budget, sitting beside a ~25k-character review and a ~45k-character
#: policy corpus.
MAX_MAP_CHARACTERS = 40_000

#: The kinds listed as a module's members. Containers (repository, package, module) are the
#: grouping itself, and methods are folded into their class's line when space runs short
#: before they are dropped entirely.
_MEMBER_KINDS = frozenset(
    {
        NodeType.CLASS,
        NodeType.FUNCTION,
        NodeType.METHOD,
        NodeType.INTERFACE,
        NodeType.TEST_FUNCTION,
    }
)

#: Dropped first under the character cap, in this order: the deepest detail goes before
#: anything a reader would call a missing symbol.
_DROP_FIRST = (NodeType.METHOD, NodeType.TEST_FUNCTION)


class AtlasMapModule(DomainModel):
    path: str
    #: Rendered `"kind qualified_name"`, in declaration order, so the module reads the way
    #: the file does.
    members: list[str] = Field(default_factory=list[str])
    members_omitted: int = 0


class AtlasMapRelation(DomainModel):
    source_module: str
    target_module: str
    #: Aggregated, e.g. `"imports(2), calls(12)"` — which way the coupling runs and how
    #: much of it there is, without one line per edge.
    kinds: str


class AtlasMap(DomainModel):
    modules: list[AtlasMapModule] = Field(default_factory=list[AtlasMapModule])
    relations: list[AtlasMapRelation] = Field(default_factory=list[AtlasMapRelation])
    modules_omitted: int = 0
    relations_omitted: int = 0
    #: Why there is no map, when there is none — the pinned atlas gone from the workspace,
    #: never a trimming artefact. Mirrors `BoundaryExcerpt.unavailable`.
    unavailable: str = ""

    @model_validator(mode="after")
    def a_map_has_content_or_says_why_not(self) -> AtlasMap:
        if self.unavailable and (self.modules or self.relations):
            raise ValueError("A map carries its modules or a reason it has none, not both")
        return self

    def character_estimate(self) -> int:
        """How much of a prompt this map will occupy, roughly and deterministically."""

        return (
            sum(
                len(module.path) + sum(len(member) + 4 for member in module.members) + 24
                for module in self.modules
            )
            + sum(
                len(item.source_module) + len(item.target_module) + len(item.kinds) + 12
                for item in self.relations
            )
            + len(self.unavailable)
        )


def compact_atlas_map(atlas: Atlas, *, max_characters: int = MAX_MAP_CHARACTERS) -> AtlasMap:
    """Fold one atlas down to modules, their declared members, and module-level coupling.

    Grouping is by file path — the one thing every node carries and every reader can find —
    with members in declaration order. Edges are aggregated to module pairs, `contains`
    excluded because the grouping already says it.

    Degradation under the cap is deterministic and counted at every level: first the
    deepest member kinds go (methods, then test functions), then the busiest relations
    keep their place while the tail is folded into a count, then whole modules go largest
    first. The counts are part of the value — a map that has been trimmed must say so.
    """

    containers = {NodeType.REPOSITORY, NodeType.PACKAGE, NodeType.MODULE, NodeType.TEST_MODULE}
    module_of: dict[str, str] = {node.atlas_id: node.path for node in atlas.nodes}

    members_by_path: dict[str, list[tuple[int, str, NodeType]]] = {}
    for node in atlas.nodes:
        if node.node_type in containers or node.node_type not in _MEMBER_KINDS:
            continue
        members_by_path.setdefault(node.path, []).append(
            (node.start_line or 0, f"{node.node_type.value} {node.qualified_name}", node.node_type)
        )
    # Every analysed file appears, even one declaring nothing at module level: absence of
    # members is a fact about the file, not grounds to unlist it.
    paths = sorted(
        {node.path for node in atlas.nodes if node.node_type in containers}
        | set(members_by_path)
    )

    pair_kinds: dict[tuple[str, str], Counter[str]] = {}
    for edge in atlas.edges:
        if edge.edge_type is EdgeType.CONTAINS:
            continue
        source = module_of.get(edge.source_id)
        target = module_of.get(edge.target_id)
        if source is None or target is None or source == target:
            continue
        pair_kinds.setdefault((source, target), Counter())[edge.edge_type.value] += 1

    def build(dropped_kinds: frozenset[NodeType], relation_limit: int | None) -> AtlasMap:
        modules: list[AtlasMapModule] = []
        for path in paths:
            recorded = sorted(members_by_path.get(path, []))
            kept = [text for _, text, kind in recorded if kind not in dropped_kinds]
            modules.append(
                AtlasMapModule(
                    path=path,
                    members=kept,
                    members_omitted=len(recorded) - len(kept),
                )
            )
        # Busiest coupling first, so a trimmed tail loses the one-off references before
        # the dependencies a reader would ask about; path order breaks ties stably.
        ranked = sorted(
            pair_kinds.items(), key=lambda item: (-sum(item[1].values()), item[0])
        )
        kept_pairs = ranked if relation_limit is None else ranked[:relation_limit]
        return AtlasMap(
            modules=modules,
            relations=[
                AtlasMapRelation(
                    source_module=source,
                    target_module=target,
                    kinds=", ".join(
                        f"{kind}({count})" for kind, count in sorted(counts.items())
                    ),
                )
                for (source, target), counts in kept_pairs
            ],
            relations_omitted=len(ranked) - len(kept_pairs),
        )

    candidate = build(frozenset(), None)
    dropped: frozenset[NodeType] = frozenset()
    for kind in _DROP_FIRST:
        if candidate.character_estimate() <= max_characters:
            return candidate
        dropped = dropped | {kind}
        candidate = build(dropped, None)
    while candidate.character_estimate() > max_characters and candidate.relations:
        candidate = build(dropped, max(0, len(candidate.relations) // 2))
    while candidate.character_estimate() > max_characters and candidate.modules:
        # Largest module first: it buys the most room per omission, and the count keeps
        # the omission visible.
        largest = max(
            candidate.modules, key=lambda module: sum(len(m) for m in module.members)
        )
        candidate = candidate.model_copy(
            update={
                "modules": [m for m in candidate.modules if m.path != largest.path],
                "modules_omitted": candidate.modules_omitted + 1,
            }
        )
    return candidate
