"""Folding an atlas to the map the conversation stages carry.

The property under test throughout: trimming is explicit. A map that quietly dropped a
module would read as "that module does not exist", so every degradation level must leave a
count behind — and the same atlas must fold to the same map every time, because a
conversation re-assembles its evidence on every turn.
"""

from __future__ import annotations

import pytest

from archcompass.domain.atlas import (
    Atlas,
    AtlasEdge,
    AtlasNode,
    AtlasVersion,
    EdgeType,
    NodeType,
)
from archcompass.domain.atlas_map import AtlasMap, compact_atlas_map

_PARSER = "test-parser"


def _node(
    atlas_id: str,
    path: str,
    node_type: NodeType,
    qualified_name: str | None = None,
    start_line: int | None = None,
) -> AtlasNode:
    return AtlasNode(
        atlas_id=atlas_id,
        path=path,
        symbol_name=atlas_id,
        qualified_name=qualified_name or atlas_id,
        node_type=node_type,
        start_line=start_line,
        parser_version=_PARSER,
    )


def _atlas(nodes: list[AtlasNode], edges: list[AtlasEdge]) -> Atlas:
    return Atlas(
        version=AtlasVersion(
            repository_identity="repo",
            root_path="/repository",
            content_fingerprint="fingerprint",
            parser_version=_PARSER,
            analysis_config_hash="config",
        ),
        nodes=nodes,
        edges=edges,
        metrics=[],
    )


def _two_modules() -> Atlas:
    return _atlas(
        [
            _node("pkg.a", "pkg/a.py", NodeType.MODULE),
            _node("pkg.a.Port", "pkg/a.py", NodeType.CLASS, "pkg.a.Port", 3),
            _node("pkg.a.helper", "pkg/a.py", NodeType.FUNCTION, "pkg.a.helper", 40),
            _node("pkg.a.Port.run", "pkg/a.py", NodeType.METHOD, "pkg.a.Port.run", 5),
            _node("pkg.b", "pkg/b.py", NodeType.MODULE),
            _node("pkg.b.Adapter", "pkg/b.py", NodeType.CLASS, "pkg.b.Adapter", 8),
        ],
        [
            AtlasEdge(
                edge_id="contains",
                source_id="pkg.a",
                target_id="pkg.a.Port",
                edge_type=EdgeType.CONTAINS,
                confidence=1.0,
            ),
            AtlasEdge(
                edge_id="implements",
                source_id="pkg.b.Adapter",
                target_id="pkg.a.Port",
                edge_type=EdgeType.IMPLEMENTS,
                confidence=1.0,
            ),
            AtlasEdge(
                edge_id="imports",
                source_id="pkg.b",
                target_id="pkg.a",
                edge_type=EdgeType.IMPORTS,
                confidence=1.0,
            ),
        ],
    )


def test_modules_group_their_members_in_declaration_order() -> None:
    folded = compact_atlas_map(_two_modules())

    assert [module.path for module in folded.modules] == ["pkg/a.py", "pkg/b.py"]
    first = folded.modules[0]
    assert first.members == [
        "class pkg.a.Port",
        "method pkg.a.Port.run",
        "function pkg.a.helper",
    ]
    assert first.members_omitted == 0


def test_edges_aggregate_to_module_pairs_without_contains() -> None:
    folded = compact_atlas_map(_two_modules())

    assert len(folded.relations) == 1
    relation = folded.relations[0]
    assert (relation.source_module, relation.target_module) == ("pkg/b.py", "pkg/a.py")
    assert relation.kinds == "implements(1), imports(1)"
    assert folded.relations_omitted == 0


def test_the_same_atlas_folds_to_the_same_map() -> None:
    assert compact_atlas_map(_two_modules()) == compact_atlas_map(_two_modules())


def test_degradation_under_the_cap_is_counted_at_every_level() -> None:
    """Methods go first and are counted per module; a map squeezed to nothing still says
    how many modules it folded away rather than presenting an empty repository."""

    folded = compact_atlas_map(_two_modules(), max_characters=190)
    dropped_methods = folded.modules[0]
    assert "method pkg.a.Port.run" not in dropped_methods.members
    assert dropped_methods.members_omitted == 1

    crushed = compact_atlas_map(_two_modules(), max_characters=1)
    assert crushed.modules_omitted + len(crushed.modules) == 2
    assert crushed.modules_omitted > 0


def test_the_cap_is_respected_on_a_pathological_atlas() -> None:
    sprawling = _atlas(
        [
            node
            for index in range(200)
            for node in (
                _node(f"pkg.m{index}", f"pkg/m{index}.py", NodeType.MODULE),
                _node(
                    f"pkg.m{index}.Widget",
                    f"pkg/m{index}.py",
                    NodeType.CLASS,
                    f"pkg.m{index}.WidgetWithAConsiderablyLongName",
                    1,
                ),
            )
        ],
        [],
    )

    folded = compact_atlas_map(sprawling, max_characters=2_000)

    assert folded.character_estimate() <= 2_000
    assert folded.modules_omitted + len(folded.modules) == 200


def test_a_map_carries_content_or_a_reason_never_both() -> None:
    with pytest.raises(ValueError, match="not both"):
        AtlasMap(
            modules=compact_atlas_map(_two_modules()).modules,
            unavailable="The atlas this review pinned is no longer available.",
        )
