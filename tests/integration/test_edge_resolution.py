"""What the type-aware resolver changes about the atlas, and what it must not.

Two of these need mypy, which ships as an optional extra; they skip when it is absent. The
rest hold whether or not it is installed, because the property they check is that the
optional pass is genuinely optional: the atlas built without a resolver is the atlas this
project has always built, and the two are never mistaken for each other.
"""

from __future__ import annotations

from pathlib import Path
from textwrap import dedent

import pytest

from archcompass.analysis.adapters.ast_analyzer import PythonAstRepositoryAnalyzer
from archcompass.analysis.atlas import Atlas, EdgeType, NodeType
from archcompass.analysis.detectors import detect_finding_candidates
from archcompass.bootstrap import build_edge_resolver
from archcompass.ports.atlas import (
    EdgeResolutionRequest,
    EdgeResolutionResult,
    EdgeResolver,
)

AUDIOBOOK = Path(__file__).resolve().parents[2] / "examples" / "cases" / "audiobook-studio"


def _resolver() -> EdgeResolver:
    resolver = build_edge_resolver()
    if resolver is None:
        pytest.skip("the resolution extra is not installed")
    return resolver


class _SilentResolver:
    """A resolver that answers nothing — the wiring without the type checker."""

    def fingerprint(self) -> dict[str, str]:
        return {"backend": "silent"}

    def resolve(self, root: Path, request: EdgeResolutionRequest) -> EdgeResolutionResult:
        return EdgeResolutionResult()


def _implements(atlas: Atlas) -> set[tuple[str, str, str, str | None, float]]:
    names = {node.atlas_id: node.qualified_name for node in atlas.nodes}
    return {
        (
            names[edge.source_id],
            names[edge.target_id],
            edge.resolved_by,
            edge.conformance,
            edge.confidence,
        )
        for edge in atlas.edges
        if edge.edge_type == EdgeType.IMPLEMENTS
    }


def test_the_config_hash_separates_a_resolved_atlas_from_an_unresolved_one() -> None:
    """A stored atlas built without typed edges must never be read as one built with them.

    The hash is the only thing that can say so: the nodes are identical either way, and an
    atlas that compared equal would be served from the cache with its edges missing.
    """

    plain = PythonAstRepositoryAnalyzer()
    resolved = PythonAstRepositoryAnalyzer(edge_resolver=_SilentResolver())
    assert (
        plain.current_identity(AUDIOBOOK / "repository").analysis_config_hash
        != resolved.current_identity(AUDIOBOOK / "repository").analysis_config_hash
    )


def test_a_resolver_that_answers_nothing_suppresses_the_heuristic() -> None:
    """Exactly one source of structural `IMPLEMENTS` edges, never two.

    With a resolver present the heuristic is skipped even when the resolver finds nothing,
    because a reader has to be able to say which pass believed what. The two adapters
    audiobook-studio conforms structurally are the heuristic's whole output here, so their
    absence is the check.
    """

    atlas = PythonAstRepositoryAnalyzer(edge_resolver=_SilentResolver()).analyze(
        AUDIOBOOK / "repository"
    )
    assert _implements(atlas) == set()


def test_the_typed_sweep_names_the_structurally_conforming_adapters() -> None:
    atlas = PythonAstRepositoryAnalyzer(edge_resolver=_resolver()).analyze(
        AUDIOBOOK / "repository"
    )
    assert _implements(atlas) == {
        (
            "preparation.ollama.OllamaPreparer",
            "preparation.base.NarrationPreparer",
            "types",
            "strict",
            1.0,
        ),
        # Narrows `narrate`'s parameter, which is contravariance-unsafe and which mypy
        # rejects — correctly. The relaxed rule credits it, and the atlas records that it
        # did rather than presenting the edge as the checker's own answer.
        (
            "synthesis.qwen.QwenSynthesis",
            "synthesis.base.SynthesisProvider",
            "types",
            "structural",
            0.9,
        ),
    }


def test_a_zero_member_protocol_is_never_judged() -> None:
    """`Voice` has no members, so every class in the repository satisfies it.

    A sweep that judged it would wire the whole repository to one node and hand the
    sole-implementation detector a boundary with nine implementations behind it.
    """

    atlas = PythonAstRepositoryAnalyzer(edge_resolver=_resolver()).analyze(
        AUDIOBOOK / "repository"
    )
    voice = next(
        node
        for node in atlas.nodes
        if node.qualified_name == "synthesis.base.Voice"
        and node.node_type == NodeType.INTERFACE
    )
    assert not [
        edge
        for edge in atlas.edges
        if edge.edge_type == EdgeType.IMPLEMENTS and edge.target_id == voice.atlas_id
    ]


def test_the_typed_sweep_resolves_calls_the_parse_could_not() -> None:
    root = AUDIOBOOK / "repository"
    plain = PythonAstRepositoryAnalyzer().analyze(root)
    typed = PythonAstRepositoryAnalyzer(edge_resolver=_resolver()).analyze(root)
    calls = {
        atlas.version.version_id: sum(
            1 for edge in atlas.edges if edge.edge_type == EdgeType.CALLS
        )
        for atlas in (plain, typed)
    }
    assert calls[typed.version.version_id] > calls[plain.version.version_id]
    unresolved = {
        atlas.version.version_id: sum(
            1 for signal in atlas.signals if signal.code == "unresolved-call"
        )
        for atlas in (plain, typed)
    }
    assert unresolved[typed.version.version_id] < unresolved[plain.version.version_id]
    # An edge to a symbol outside the repository is not an edge: every typed edge lands on
    # a node this atlas holds.
    ids = {node.atlas_id for node in typed.nodes}
    assert all(edge.target_id in ids for edge in typed.edges)


def test_two_runs_on_one_commit_produce_the_same_atlas() -> None:
    """Byte-identical but for the fields that are meant to differ per run.

    The version id and creation time are minted per build by design; everything the atlas
    asserts about the repository has to be identical or the content-fingerprint cache is
    serving a different answer each time it misses.
    """

    resolver = _resolver()
    analyzer = PythonAstRepositoryAnalyzer(edge_resolver=resolver)
    first = analyzer.analyze(AUDIOBOOK / "repository")
    second = analyzer.analyze(AUDIOBOOK / "repository")
    fields = {"exclude": {"version": {"version_id", "created_at"}}}
    assert first.model_dump_json(**fields) == second.model_dump_json(**fields)  # type: ignore[arg-type]


def test_the_sole_implementation_detector_sees_the_structural_adapter() -> None:
    """The acceptance case: the adapter that names no port is still its implementation."""

    atlas = PythonAstRepositoryAnalyzer(edge_resolver=_resolver()).analyze(
        AUDIOBOOK / "repository"
    )
    found = {
        candidate.participants[1].qualified_name
        for candidate in detect_finding_candidates(atlas)
    }
    assert "synthesis.qwen.QwenSynthesis" in found


def test_a_class_with_an_unfollowed_base_is_never_judged(tmp_path: Path) -> None:
    """Third-party bases are left unfollowed, and an unfollowed base answers yes to anything.

    This is the failure that would have shipped silently: on this project's own `src/` the
    sweep found 10,176 conformance pairs instead of 38, because every pydantic model in it
    satisfied every protocol in it. A boundary with two hundred implementations behind it
    is not reported wrongly — it drops out of the sole-implementation detector entirely.
    """

    root = tmp_path / "vendored"
    root.mkdir()
    (root / "shapes.py").write_text(
        dedent(
            """
            from typing import Protocol

            from vendor.sdk import BaseWidget


            class Port(Protocol):
                def alpha(self, value: int) -> str: ...
                def beta(self) -> None: ...


            class Widget(BaseWidget):
                def unrelated(self) -> None:
                    return None
            """
        ),
        encoding="utf-8",
    )
    atlas = PythonAstRepositoryAnalyzer(edge_resolver=_resolver()).analyze(root)
    assert _implements(atlas) == set()


def test_a_repository_the_backend_cannot_build_still_yields_an_atlas(tmp_path: Path) -> None:
    """A syntax error aborts mypy's build; it must not abort indexing.

    The parse already produced nodes and edges for the files it could read, and a
    repository that does not type-check is exactly the kind this advisor is pointed at.
    """

    root = tmp_path / "broken"
    root.mkdir()
    (root / "good.py").write_text(
        dedent(
            """
            def alpha() -> int:
                return 1
            """
        ),
        encoding="utf-8",
    )
    (root / "bad.py").write_text("def broken(\n", encoding="utf-8")
    atlas = PythonAstRepositoryAnalyzer(edge_resolver=_resolver()).analyze(root)
    assert any(node.qualified_name == "good.alpha" for node in atlas.nodes)
    assert any(signal.code == "parse-error" for signal in atlas.signals)
