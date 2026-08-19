"""Deterministic structural detector boundary records.

A detector answers "is this shape present, and how do I know", never "is this wrong".
Materiality depends on the case, so every candidate produced here is an input to judgement
rather than a verdict, and "this does not matter" stays a first-class answer downstream
before conversion to domain candidates.

Detection reads the graph rather than node attributes alone. A pattern established by
looking at one node in isolation is nearly always a lint; architecture is about placement,
so the evidence is a relationship — what implements what, what depends on it, what would
have to change with it.

This is derivation, not infrastructure, and it sits beside `metrics.py` for the same
reason: it is a pure function of an `Atlas`, with no I/O and no vendor in sight. Behind a
port it would be an interface with a single implementation hiding nothing — the shape
this very module reports.
"""

from __future__ import annotations

import re
from collections import defaultdict

from archcompass.analysis.atlas import (
    Atlas,
    AtlasEdge,
    AtlasNode,
    DefinedConstant,
    EdgeType,
    FindingCandidate,
    FindingMeasurement,
    FindingParticipant,
    FindingPattern,
    MetricNature,
    ModuleFacts,
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
    """Every candidate the catalogue can find in one atlas, in a stable order.

    Both directions of repeated knowledge run here. Order is by detector and then by the
    detector's own deterministic ordering, because `BR-nnn` references are assigned from
    position: the same atlas must always number the same boundary the same way.
    """

    nodes = {node.atlas_id: node for node in atlas.nodes}
    return [
        *sole_implementation_candidates(nodes, atlas.edges),
        *duplicated_knowledge_candidates(atlas.module_facts),
        *scattered_concept_candidates(nodes, atlas.edges, atlas.module_facts),
    ]


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
        # Counting it produced a live false positive: a reasoning port then extended by a
        # second protocol was reported as having exactly one implementation, which was that
        # extender. (The advisor was right that the split earned nothing — the two are one
        # protocol now.) Excluding abstractions can leave a parent with none resolvable, and
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


#: What comparing module text cannot establish, stated on every duplication candidate.
_DUPLICATED_KNOWLEDGE_LIMITS = (
    "Compared by constant name and by a fingerprint of the literal value in this snapshot. "
    "Two modules stating the same name may be describing unrelated things, a value assembled "
    "at runtime is not compared at all, and knowledge repeated without a shared name — the "
    "same rule written out twice in different words — is invisible to this method."
)

#: The same, for a concept whose name has spread beyond the module that owns it.
_SCATTERED_CONCEPT_LIMITS = (
    "Counted by name only: identifiers and string literals in this snapshot that contain the "
    "owning module's name, outside the package that owns it. Docstrings are excluded. A "
    "mention is not evidence of a dependency — a name may be a coincidence, and configuration "
    "or wiring that legitimately names a backend will appear here — and knowledge that leaked "
    "without carrying the name with it cannot be seen this way at all."
)


def duplicated_knowledge_candidates(
    module_facts: list[ModuleFacts],
) -> list[FindingCandidate]:
    """One constant stated in several modules, with no module owning it.

    The direction the sole-implementation detector cannot see. An advisor that reports only
    unnecessary abstractions becomes an advocate for copying, so this is the counterweight:
    here the advice, where the case supports one, is *give this one owner* rather than
    *remove the boundary*.

    Agreement is not the question. Two modules stating the same constant with the same value
    are a coordinated edit waiting to happen; two stating it with *different* values may have
    drifted already. Both are reported, and the measurements say which this is, because only
    the case can say whether one owner is worth introducing.
    """

    by_name: dict[str, list[tuple[ModuleFacts, DefinedConstant]]] = defaultdict(list)
    for module in module_facts:
        for constant in module.constants:
            by_name[constant.name].append((module, constant))

    candidates: list[FindingCandidate] = []
    for name, statements in sorted(by_name.items()):
        # One module stating a constant is a module owning it, which is the thing that is
        # supposed to happen.
        if len({module.node_id for module, _ in statements}) < 2:
            continue
        ordered = sorted(statements, key=lambda item: item[0].path)
        fingerprints = {constant.value_fingerprint for _, constant in ordered}
        literal = [item for item in fingerprints if item]
        agreed = len(literal) == 1 and len(fingerprints) == 1
        candidates.append(
            FindingCandidate(
                pattern=FindingPattern.DUPLICATED_KNOWLEDGE,
                summary=(
                    f"{name} is stated in {len(ordered)} modules"
                    + (
                        " with the same value."
                        if agreed
                        else " and the copies do not all hold the same value."
                        if len(literal) > 1
                        else "."
                    )
                ),
                participants=[
                    FindingParticipant(
                        node_id=module.node_id,
                        qualified_name=f"{module.qualified_name}.{name}",
                        location=SourceLocation(
                            path=module.path,
                            start_line=constant.line,
                            end_line=constant.line,
                        ),
                        role=f"States {name} at this location.",
                    )
                    for module, constant in ordered
                ],
                measurements=[
                    FindingMeasurement(
                        name="modules_stating_it",
                        value=float(len(ordered)),
                        unit="modules",
                        nature=MetricNature.MEASUREMENT,
                        definition=(
                            "Modules defining a module-level constant of this name in this "
                            "snapshot."
                        ),
                        limitations=_DUPLICATED_KNOWLEDGE_LIMITS,
                    ),
                    FindingMeasurement(
                        name="distinct_values",
                        value=float(len(literal)),
                        unit="values",
                        nature=MetricNature.MEASUREMENT,
                        definition=(
                            "Distinct literal values among those copies. One means they "
                            "agree today; more than one means they have already drifted; "
                            "zero means no copy is a literal this method can compare."
                        ),
                        limitations=_DUPLICATED_KNOWLEDGE_LIMITS,
                    ),
                ],
                relationships=[],
                limitations=_DUPLICATED_KNOWLEDGE_LIMITS,
            )
        )
    return candidates


def scattered_concept_candidates(
    nodes: dict[str, AtlasNode],
    edges: list[AtlasEdge],
    module_facts: list[ModuleFacts],
) -> list[FindingCandidate]:
    """A concept that has an owner, named in modules that go around it.

    Restricted to concepts that already have somewhere to live: the module must contain an
    implementation of an abstraction, so there is a port through which the rest of the
    repository could have reached it. That restriction is what makes the finding meaningful
    rather than a word count — the question is not "is this name used" but "is this name
    used by code that was given a boundary to use instead".

    It is still only a name. A module that names a backend may be the wiring that is
    supposed to, which is why this is a candidate and not a verdict.
    """

    module_by_path = {module.path: module for module in module_facts}
    # Each implementing module, with the vocabulary of the abstractions it implements.
    abstraction_words: dict[str, set[str]] = defaultdict(set)
    for edge in edges:
        if edge.edge_type is not EdgeType.IMPLEMENTS:
            continue
        implementor = nodes.get(edge.source_id)
        abstraction = nodes.get(edge.target_id)
        if implementor is None or abstraction is None:
            continue
        abstraction_words[implementor.path] |= _words(
            abstraction.qualified_name.rsplit(".", maxsplit=1)[-1]
        )

    candidates: list[FindingCandidate] = []
    for path in sorted(abstraction_words):
        owner = module_by_path.get(path)
        if owner is None:
            continue
        concept = path.rsplit("/", maxsplit=1)[-1].removesuffix(".py").casefold()
        if not concept or concept.startswith("_"):
            continue
        # A module named after the concept its abstraction is about is not a variant whose
        # name has escaped — it *is* the concept, and the rest of the repository naming it
        # is the domain vocabulary rather than a leak. `voices.py` behind `VoiceValidator`
        # is that; `qwen.py` behind `SpeechProvider` is not.
        if any(_shares_a_stem(concept, word) for word in abstraction_words[path]):
            continue
        package = path.rsplit("/", maxsplit=1)[0] if "/" in path else ""
        outside = sorted(
            (
                module
                for module in module_facts
                if module.mention_of(concept) is not None
                # Its own package is where the concept is supposed to be known: the port
                # beside it, and the wiring that registers it, both name it on purpose.
                and not (module.path == path or module.path.startswith(f"{package}/"))
            ),
            key=lambda module: module.path,
        )
        if not outside:
            continue
        candidates.append(
            FindingCandidate(
                pattern=FindingPattern.SCATTERED_CONCEPT,
                summary=(
                    f"{owner.qualified_name} is implemented behind an abstraction, yet "
                    f"'{concept}' is named in {len(outside)} module(s) outside its package."
                ),
                participants=[
                    FindingParticipant(
                        node_id=owner.node_id,
                        qualified_name=owner.qualified_name,
                        # The owner is the module itself rather than a use of the name, so
                        # its declaration is where it begins. Every other participant points
                        # at a line that actually contains the concept.
                        location=SourceLocation(path=owner.path, start_line=1, end_line=1),
                        role=f"Owns '{concept}' and is reachable through an abstraction.",
                    ),
                    *[
                        _naming_participant(module, concept)
                        for module in outside
                    ],
                ],
                measurements=[
                    FindingMeasurement(
                        name="modules_naming_it_from_outside",
                        value=float(len(outside)),
                        unit="modules",
                        nature=MetricNature.STRUCTURAL_PROXY,
                        definition=(
                            "Modules outside the owning package whose identifiers or string "
                            "literals contain the owning module's name."
                        ),
                        limitations=_SCATTERED_CONCEPT_LIMITS,
                    ),
                ],
                relationships=[],
                limitations=_SCATTERED_CONCEPT_LIMITS,
            )
        )
    return candidates


def _naming_participant(module: ModuleFacts, concept: str) -> FindingParticipant:
    """One module that names a concept it does not own, located where it names it.

    Pointed at the first mention rather than at the module, because a participant's span is
    what gets shown when a reader asks to see the finding. This one used to say line 1 —
    which in a Python file is the docstring, so the code delivered as evidence of a leaked
    vendor name was five docstrings that did not contain it, and the advisor said so.

    The first site and not all of them: a participant carries one span, and the count in the
    role is what says whether it is an isolated import or a name threaded through the file.
    """

    mention = module.mention_of(concept)
    if mention is None:  # pragma: no cover — callers filter on this
        raise ValueError(f"{module.path} does not name {concept}")
    elsewhere = (
        "" if len(mention.lines) == 1 else f" Named on {len(mention.lines)} lines here."
    )
    return FindingParticipant(
        node_id=module.node_id,
        qualified_name=module.qualified_name,
        location=SourceLocation(
            path=module.path, start_line=mention.first, end_line=mention.first
        ),
        role=f"Names '{concept}' from outside the package that owns it.{elsewhere}",
    )


def _words(name: str) -> set[str]:
    """The lower-case words in an identifier, split at camel-case humps and punctuation."""

    spaced = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", " ", name)
    return {word.casefold() for word in re.split(r"[^A-Za-z0-9]+", spaced) if word}


def _shares_a_stem(concept: str, word: str, *, minimum: int = 4) -> bool:
    """Whether two words are the same term, allowing for a plural or a suffix.

    Deliberately blunt — a prefix test rather than a stemmer. The question it answers is
    only "was this module named after the thing its port is about", and `voices`/`voice` is
    the shape that keeps arising. The minimum length keeps short words like `id` or `run`
    from matching everything.
    """

    if len(concept) < minimum or len(word) < minimum:
        return concept == word
    return concept.startswith(word) or word.startswith(concept)
