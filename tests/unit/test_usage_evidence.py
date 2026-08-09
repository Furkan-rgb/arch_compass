"""What a candidate says about how the flagged code is actually used.

The judge decided blind. Its payload was the candidate's metadata — names, paths, roles, a
count — and it contained no line of the repository at all, so "are these two copies one fact
or two" was answered from two identifiers that happen to be spelled the same. On a seeded
bench it called a provable coincidence a duplication and a provable duplication a
coincidence, in different runs, from the same input.

These tests pin the half of the fix that is assembly rather than reading: the application
walks the repository itself, deterministically, and attaches what consumes each copy as
participants of the candidate. Everything downstream — the excerpts, the fingerprints, the
conversation stages — already knows what a participant is, which is why usage arrives as one
and not as a field of its own.

What is asserted here is discovery, order, caps and honesty about the overflow. Whether the
verdicts improve is a question for `eval/`, not for a unit test.
"""

from __future__ import annotations

from pathlib import Path

from archcompass.application.usage_evidence import (
    MAX_USAGE_PARTICIPANTS,
    UsageEvidenceService,
)
from archcompass.domain.atlas import (
    Atlas,
    AtlasEdge,
    AtlasNode,
    AtlasVersion,
    DefinedConstant,
    EdgeType,
    FindingCandidate,
    FindingPattern,
    ModuleFacts,
    NodeType,
    SourceLocation,
)
from archcompass.domain.finding_detectors import detect_finding_candidates


def _module_node(path: str) -> AtlasNode:
    name = path.removesuffix(".py").replace("/", ".")
    return AtlasNode(
        atlas_id=f"module:{path}",
        path=path,
        symbol_name=path.rsplit("/", maxsplit=1)[-1],
        qualified_name=name,
        node_type=NodeType.MODULE,
        start_line=1,
        end_line=200,
        parser_version="test-parser",
    )


def _module_facts(path: str, constants: dict[str, int]) -> ModuleFacts:
    return ModuleFacts(
        node_id=f"module:{path}",
        path=path,
        qualified_name=path.removesuffix(".py").replace("/", "."),
        constants=[
            DefinedConstant(name=name, value_fingerprint="same", line=line)
            for name, line in sorted(constants.items())
        ],
    )


def _atlas(
    *,
    nodes: list[AtlasNode],
    edges: list[AtlasEdge] | None = None,
    module_facts: list[ModuleFacts] | None = None,
) -> Atlas:
    return Atlas(
        version=AtlasVersion(
            repository_identity="test-repository",
            root_path="/does/not/matter",
            content_fingerprint="fingerprint",
            parser_version="test-parser",
            analysis_config_hash="config",
        ),
        nodes=nodes,
        edges=edges or [],
        metrics=[],
        module_facts=module_facts or [],
    )


def _write(root: Path, path: str, text: str) -> None:
    destination = root / path
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(text, encoding="utf-8")


def _duplicated_constant_repository(tmp_path: Path) -> Atlas:
    """Two modules stating RETRY_LIMIT, two reading it, and a config file naming it."""

    _write(tmp_path, "src/checkout.py", "# The vendor allows five attempts.\nRETRY_LIMIT = 5\n")
    _write(tmp_path, "src/billing.py", "RETRY_LIMIT = 5\n")
    _write(
        tmp_path,
        "src/orders.py",
        "from src.checkout import RETRY_LIMIT\n\n\ndef place() -> int:\n    return RETRY_LIMIT\n",
    )
    _write(tmp_path, "src/reporting.py", "HEADINGS = ['orders']\n")
    _write(tmp_path, "config/settings.toml", "retries = 5  # RETRY_LIMIT\n")
    return _atlas(
        nodes=[
            _module_node("src/checkout.py"),
            _module_node("src/billing.py"),
            _module_node("src/orders.py"),
            _module_node("src/reporting.py"),
        ],
        module_facts=[
            _module_facts("src/billing.py", {"RETRY_LIMIT": 1}),
            _module_facts("src/checkout.py", {"RETRY_LIMIT": 2}),
        ],
    )


def _duplicated(candidates: list[FindingCandidate]) -> FindingCandidate:
    return next(
        item for item in candidates if item.pattern is FindingPattern.DUPLICATED_KNOWLEDGE
    )


def _augmented(atlas: Atlas, root: Path) -> list[FindingCandidate]:
    return UsageEvidenceService().augment(detect_finding_candidates(atlas), atlas, root)


def _measurement(candidate: FindingCandidate, name: str) -> float:
    return next(item.value for item in candidate.measurements if item.name == name)


def test_every_module_that_reads_a_copy_becomes_a_participant(tmp_path: Path) -> None:
    """The fact the judge was missing: somebody reads both of these, for one reason."""

    atlas = _duplicated_constant_repository(tmp_path)

    candidate = _duplicated(_augmented(atlas, tmp_path))

    added = candidate.participants[2:]
    assert [(item.qualified_name, item.location) for item in added] == [
        (
            "src.orders",
            SourceLocation(path="src/orders.py", start_line=1, end_line=1),
        ),
        (
            "src.orders",
            SourceLocation(path="src/orders.py", start_line=5, end_line=5),
        ),
    ]
    assert added[0].node_id == "module:src/orders.py"
    assert "RETRY_LIMIT" in added[0].role


def test_the_lines_that_state_the_constant_are_not_reported_as_reading_it(
    tmp_path: Path,
) -> None:
    """A definition is already a participant, and naming it twice would double the finding."""

    atlas = _duplicated_constant_repository(tmp_path)

    candidate = _duplicated(_augmented(atlas, tmp_path))

    definitions = {("src/checkout.py", 2), ("src/billing.py", 1)}
    added = [
        (item.location.path, item.location.start_line)
        for item in candidate.participants[2:]
        if item.location is not None
    ]
    assert not definitions & set(added)


def test_a_hit_in_a_file_the_atlas_does_not_hold_is_counted_rather_than_shown(
    tmp_path: Path,
) -> None:
    """A participant needs a node, and configuration is not one — so it is a number.

    Dropping it silently would report three consumers where the repository has four, and
    inventing a participant for it would put a node id in the record that no atlas contains.
    """

    atlas = _duplicated_constant_repository(tmp_path)

    candidate = _duplicated(_augmented(atlas, tmp_path))

    assert _measurement(candidate, "consumer_sites") == 3
    assert _measurement(candidate, "consumer_sites_shown") == 2


def test_a_constant_nothing_reads_says_so_rather_than_saying_nothing(tmp_path: Path) -> None:
    """"Checked and found none" and "never checked" are different facts about a candidate."""

    _write(tmp_path, "src/left.py", "UNUSED_LIMIT = 5\n")
    _write(tmp_path, "src/right.py", "UNUSED_LIMIT = 5\n")
    atlas = _atlas(
        nodes=[_module_node("src/left.py"), _module_node("src/right.py")],
        module_facts=[
            _module_facts("src/left.py", {"UNUSED_LIMIT": 1}),
            _module_facts("src/right.py", {"UNUSED_LIMIT": 1}),
        ],
    )

    candidate = _duplicated(_augmented(atlas, tmp_path))

    assert len(candidate.participants) == 2
    assert _measurement(candidate, "consumer_sites") == 0
    assert _measurement(candidate, "consumer_sites_shown") == 0


def test_the_shown_consumers_are_capped_and_the_overflow_is_stated(tmp_path: Path) -> None:
    """A constant read forty times is a finding the measurement carries, not a wall of spans."""

    _write(tmp_path, "src/left.py", "SHARED_LIMIT = 5\n")
    _write(tmp_path, "src/right.py", "SHARED_LIMIT = 5\n")
    _write(
        tmp_path,
        "src/wide.py",
        "".join(f"value_{number} = SHARED_LIMIT\n" for number in range(1, 21)),
    )
    atlas = _atlas(
        nodes=[
            _module_node("src/left.py"),
            _module_node("src/right.py"),
            _module_node("src/wide.py"),
        ],
        module_facts=[
            _module_facts("src/left.py", {"SHARED_LIMIT": 1}),
            _module_facts("src/right.py", {"SHARED_LIMIT": 1}),
        ],
    )

    candidate = _duplicated(_augmented(atlas, tmp_path))

    assert len(candidate.participants) == 2 + MAX_USAGE_PARTICIPANTS
    assert _measurement(candidate, "consumer_sites") == 20
    assert _measurement(candidate, "consumer_sites_shown") == MAX_USAGE_PARTICIPANTS
    # The first by path and line, so which six are shown is a property of the repository
    # rather than of the order the filesystem happened to answer in.
    assert [item.location.start_line for item in candidate.participants[2:] if item.location] == [
        1,
        2,
        3,
        4,
        5,
        6,
    ]


def test_the_same_repository_augments_to_the_same_candidates_twice(tmp_path: Path) -> None:
    """Nothing here may be a source of a fingerprint that changes without the code."""

    atlas = _duplicated_constant_repository(tmp_path)
    candidates = detect_finding_candidates(atlas)
    service = UsageEvidenceService()

    first = service.augment(candidates, atlas, tmp_path)
    second = service.augment(candidates, atlas, tmp_path)

    assert [item.participants for item in first] == [item.participants for item in second]


def test_the_constant_is_recovered_from_the_participants_and_not_from_the_summary(
    tmp_path: Path,
) -> None:
    """The summary is prose for a person. Parsing it back would make it a data format.

    Asserted by rewriting it to name a constant that does not exist: the consumers found are
    still RETRY_LIMIT's, because the group was matched by the node ids and spans its
    participants record.
    """

    atlas = _duplicated_constant_repository(tmp_path)
    candidates = [
        item.model_copy(update={"summary": "NOTHING_LIKE_IT is stated in 2 modules."})
        for item in detect_finding_candidates(atlas)
    ]

    candidate = _duplicated(UsageEvidenceService().augment(candidates, atlas, tmp_path))

    assert len(candidate.participants) == 4
    assert _measurement(candidate, "consumer_sites") == 3


def _seam_atlas() -> Atlas:
    interface = AtlasNode(
        atlas_id="port",
        path="src/ports/store.py",
        symbol_name="Store",
        qualified_name="src.ports.store.Store",
        node_type=NodeType.INTERFACE,
        start_line=10,
        end_line=20,
        parser_version="test-parser",
    )
    implementor = AtlasNode(
        atlas_id="adapter",
        path="src/adapters/sqlite_store.py",
        symbol_name="SqliteStore",
        qualified_name="src.adapters.sqlite_store.SqliteStore",
        node_type=NodeType.CLASS,
        start_line=30,
        end_line=90,
        parser_version="test-parser",
    )
    return _atlas(
        nodes=[interface, implementor, _module_node("src/orders.py"), _module_node("src/api.py")],
        edges=[
            AtlasEdge(
                edge_id="implements",
                source_id="adapter",
                target_id="port",
                edge_type=EdgeType.IMPLEMENTS,
                confidence=1.0,
            ),
            AtlasEdge(
                edge_id="orders-imports",
                source_id="module:src/orders.py",
                target_id="port",
                edge_type=EdgeType.IMPORTS,
                confidence=1.0,
                location=SourceLocation(path="src/orders.py", start_line=4, end_line=4),
            ),
            AtlasEdge(
                edge_id="api-calls",
                source_id="module:src/api.py",
                target_id="adapter",
                edge_type=EdgeType.CALLS,
                confidence=1.0,
            ),
            AtlasEdge(
                edge_id="adapter-imports-port",
                source_id="adapter",
                target_id="port",
                edge_type=EdgeType.IMPORTS,
                confidence=1.0,
            ),
        ],
    )


def test_the_dependants_of_a_seam_come_from_the_edges_the_atlas_already_holds(
    tmp_path: Path,
) -> None:
    """Structure first: nothing is searched for where the graph already answers."""

    atlas = _seam_atlas()

    candidate = UsageEvidenceService().augment(
        detect_finding_candidates(atlas), atlas, tmp_path
    )[0]

    assert candidate.pattern is FindingPattern.SOLE_IMPLEMENTATION
    added = candidate.participants[2:]
    assert [item.qualified_name for item in added] == ["src.api", "src.orders"]
    assert added[1].location == SourceLocation(path="src/orders.py", start_line=4, end_line=4)
    # No recorded location on the calling edge, so the dependant's own declaration stands in.
    assert added[0].location == SourceLocation(path="src/api.py", start_line=1, end_line=200)
    assert _measurement(candidate, "dependant_sites") == 2
    assert _measurement(candidate, "dependant_sites_shown") == 2


def test_a_participant_of_the_seam_is_not_also_a_dependant_of_it(tmp_path: Path) -> None:
    """The implementation imports the abstraction it implements. That is the finding, not usage."""

    atlas = _seam_atlas()

    candidate = UsageEvidenceService().augment(
        detect_finding_candidates(atlas), atlas, tmp_path
    )[0]

    assert "adapter" not in [item.node_id for item in candidate.participants[2:]]


def test_a_scattered_concept_is_returned_exactly_as_the_detector_wrote_it(
    tmp_path: Path,
) -> None:
    """Its detector already records the mentioning sites, so there is nothing to add."""

    owner = AtlasNode(
        atlas_id="qwen-class",
        path="src/qwen.py",
        symbol_name="QwenSpeech",
        qualified_name="src.qwen.QwenSpeech",
        node_type=NodeType.CLASS,
        start_line=5,
        end_line=40,
        parser_version="test-parser",
    )
    port = AtlasNode(
        atlas_id="speech-port",
        path="src/ports/speech.py",
        symbol_name="SpeechProvider",
        qualified_name="src.ports.speech.SpeechProvider",
        node_type=NodeType.INTERFACE,
        start_line=3,
        end_line=12,
        parser_version="test-parser",
    )
    facts = ModuleFacts(
        node_id="module:src/qwen.py",
        path="src/qwen.py",
        qualified_name="src.qwen",
    )
    caller = ModuleFacts(
        node_id="module:api/routes.py",
        path="api/routes.py",
        qualified_name="api.routes",
        mentions=[{"name": "qwen", "lines": [7]}],  # type: ignore[list-item]
    )
    atlas = _atlas(
        nodes=[owner, port],
        edges=[
            AtlasEdge(
                edge_id="qwen-implements",
                source_id="qwen-class",
                target_id="speech-port",
                edge_type=EdgeType.IMPLEMENTS,
                confidence=1.0,
            )
        ],
        module_facts=[facts, caller],
    )
    detected = [
        item
        for item in detect_finding_candidates(atlas)
        if item.pattern is FindingPattern.SCATTERED_CONCEPT
    ]

    augmented = UsageEvidenceService().augment(detected, atlas, tmp_path)

    assert augmented == detected
