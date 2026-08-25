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
    FindingRelation,
    MetricNature,
    ModuleFacts,
    NodeType,
    SourceLocation,
)
from archcompass.analysis.repository_facts import RepositoryFacts

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
    # Derived once and handed down. Three detectors used to ask the same questions of the
    # same graph separately, and the answers drifted — see `repository_facts`.
    facts = RepositoryFacts.over(nodes, atlas.edges)
    return [
        *sole_implementation_candidates(nodes, atlas.edges, facts),
        *duplicated_knowledge_candidates(nodes, atlas.module_facts, facts),
        *scattered_concept_candidates(nodes, atlas.edges, atlas.module_facts, facts),
    ]


def sole_implementation_candidates(
    nodes: dict[str, AtlasNode],
    edges: list[AtlasEdge],
    facts: RepositoryFacts,
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

    doubles = _test_doubles(nodes, facts)

    candidates: list[FindingCandidate] = []
    for interface_id, implementor_ids in sorted(facts.implementations.items()):
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
        reaching = facts.reaches(interface_id)
        offered = _offering(interface, nodes, doubles)
        from_tests = facts.from_tests(interface_id)
        # Conformance first and then everything that reaches the abstraction, so the shape
        # reads in the order the verdict needs it: what implements this, then what would have
        # to change with it.
        relationships = [
            *(
                edge
                for edge in edges
                if edge.target_id == interface_id and edge.source_id == implementor.atlas_id
            ),
            *sorted(reaching, key=lambda edge: (edge.source_id, edge.edge_type.value)),
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
                        name="test_doubles_offering_its_methods",
                        value=float(len(offered)),
                        unit="classes",
                        nature=MetricNature.STRUCTURAL_PROXY,
                        definition=(
                            "Classes declared in test modules that offer every method this "
                            "abstraction declares. The corpus's exception for a single "
                            "implementation is usually substitution in tests, and nothing "
                            "else in this candidate speaks to it."
                        ),
                        limitations=(
                            "Matched by method name only, so a class offering the right "
                            "names is not proof it stands in for this abstraction — an "
                            "abstraction declaring one common method may be matched by a "
                            "double written for something else. What this method sees is "
                            "classes: a double that is a function, a lambda or a mock built "
                            "at run time is outside it. Zero therefore means none was "
                            "observed by this method, which is what it says and no more — "
                            "read it beside the resolved test references below rather than "
                            "as licence to assume an unobserved one."
                        ),
                    ),
                    FindingMeasurement(
                        name="test_references_to_abstraction",
                        value=float(len(from_tests)),
                        unit="references",
                        nature=MetricNature.MEASUREMENT,
                        definition=(
                            "Resolved imports, references and calls into this abstraction "
                            "whose source is inside a test module. Unlike the count above "
                            "this is an edge the parser resolved rather than a match on "
                            "method names, and it is about this abstraction rather than "
                            "about anything shaped like it."
                        ),
                        limitations=(
                            "A reference is not a substitution: a test naming an abstraction "
                            "may be asserting about it rather than standing in for it, and "
                            "this counts either the same. Zero is what this analysis "
                            "observed — no test module in this snapshot names this "
                            "abstraction at all — and it is a fact about the snapshot rather "
                            "than a claim about every way a test could reach it."
                        ),
                    ),
                    FindingMeasurement(
                        name="dependants_of_abstraction",
                        value=float(len(reaching)),
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
                derived_relations=[
                    FindingRelation(
                        source_id=node_id,
                        target_id=interface_id,
                        kind="offers-its-methods",
                        established_by="matching declared method names",
                    )
                    for node_id in offered
                ],
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


def _test_doubles(
    nodes: dict[str, AtlasNode], facts: RepositoryFacts
) -> list[tuple[str, frozenset[str]]]:
    """The method surface of every class declared in a test module.

    Computed once for the repository rather than per candidate: it is a fact about the test
    suite, and fifty candidates otherwise ask the same question of the same nodes fifty
    times.

    A method of a class inside a test module is recorded as a test function rather than a
    method, so both are read here. Dunders are left out — every class has `__init__`, and a
    surface that includes it matches on nothing.

    The node id travels with the surface because the candidate names the doubles it counted.
    A count on its own sent judgements looking for them: `test_doubles_offering_its_methods`
    said three and nothing said which three, and no lookup available to an investigation can
    answer it — the match is this detector's own, not an edge anyone can query.
    """

    children: dict[str, set[str]] = defaultdict(set)
    for node in nodes.values():
        if node.parent_id is None:
            continue
        if node.node_type not in (NodeType.METHOD, NodeType.TEST_FUNCTION):
            continue
        if node.symbol_name.startswith("__"):
            continue
        children[node.parent_id].add(node.symbol_name)

    return [
        (node.atlas_id, frozenset(children[node.atlas_id]))
        for node in nodes.values()
        if node.node_type is NodeType.CLASS
        and node.atlas_id in facts.test_owned
        and children[node.atlas_id]
    ]


def _offering(
    interface: AtlasNode,
    nodes: dict[str, AtlasNode],
    doubles: list[tuple[str, frozenset[str]]],
) -> list[str]:
    """Which test-module classes offer everything this abstraction declares.

    Named rather than counted, and the count taken from the length. One double is a seam and
    six are a suite built on one, so the number still says something — but the number alone
    is unanswerable downstream, because this match is not an edge and no lookup can retrieve
    the classes it matched.

    An abstraction that declares nothing is answered with nothing rather than with every
    class in the test suite: the empty set is a subset of all of them, which is true and
    useless.
    """

    declared = {
        node.symbol_name
        for node in nodes.values()
        if node.parent_id == interface.atlas_id
        and node.node_type in (NodeType.METHOD, NodeType.TEST_FUNCTION)
        and not node.symbol_name.startswith("__")
    }
    if not declared:
        return []
    return sorted(node_id for node_id, surface in doubles if declared <= surface)


def duplicated_knowledge_candidates(
    nodes: dict[str, AtlasNode],
    module_facts: list[ModuleFacts],
    facts: RepositoryFacts,
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

    Tests count, and a set of tests on its own does not. The sole-implementation detector
    already leaves tests out of its count and says so; this one counted them, so five test
    modules each fixing their own `FIXTURE` path arrived as knowledge with no owner. It is
    the opposite: a test stating its own setup is a test that can be read on its own, and
    giving those five one owner would couple them. A copy shared with code that is not a
    test is still reported, because a test hard-coding a value production owns is exactly
    the drift this pattern is for.
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
        if all(module.node_id in facts.test_owned for module, _ in statements):
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
    facts: RepositoryFacts,
) -> list[FindingCandidate]:
    """A concept that has an owner, named in modules that go around it.

    Restricted to concepts that already have somewhere to live: the module must contain an
    implementation of an abstraction, so there is a port through which the rest of the
    repository could have reached it. That restriction is what makes the finding meaningful
    rather than a word count — the question is not "is this name used" but "is this name
    used by code that was given a boundary to use instead".

    It is still only a name. A module that names a backend may be the wiring that is
    supposed to, which is why this is a candidate and not a verdict.

    What the name cannot say, the graph can, so the graph is carried beside it. Naming a
    module and reaching it are different facts and the count conflates them: a module that
    imports the owner is using a dependency, and one that spells the name with no edge to
    it at all has the name written into it — a literal, or a type named after something it
    does not depend on. Both were "a module naming it from outside" and nothing downstream
    could tell them apart, so the judge inferred which it was and had no way to be right.
    """

    module_by_path = {module.path: module for module in module_facts}
    # Which module reaches which, and by what kind of edge. Built once over the whole edge
    # list rather than per candidate, because it is a fact about the repository and every
    # candidate asks the same question of it.
    reach: dict[tuple[str, str], list[AtlasEdge]] = defaultdict(list)
    for edge in edges:
        source, target = nodes.get(edge.source_id), nodes.get(edge.target_id)
        if source is None or target is None or source.path == target.path:
            continue
        if edge.edge_type is EdgeType.CONTAINS:
            continue
        reach[(source.path, target.path)].append(edge)
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
        # A module whose word never qualifies anything is named for the kind of thing it
        # holds, not for a thing that could leak. `qwen.py` declares `QwenSpeechProvider`
        # and `northwind.py` declares `NorthwindFeed`, so the word is a proper noun that
        # modifies — a use of it elsewhere is a use of *this*. `nodes.py` declares
        # `load_context_node` and `report.py` declares `compose_markdown_report`, where the
        # word is the category the file belongs to; the repository is then full of it for
        # unrelated reasons, and every one of them matched.
        if not _names_things_after_itself(concept, path, nodes):
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
        reaching = [module for module in outside if reach.get((module.path, path))]
        from_tests = [module for module in outside if module.node_id in facts.test_owned]
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
                    FindingMeasurement(
                        name="of_those_that_are_tests",
                        value=float(len(from_tests)),
                        unit="modules",
                        nature=MetricNature.MEASUREMENT,
                        definition=(
                            "Of the modules above, those in the test suite. A vendor's name "
                            "written into twenty test modules and five production ones is a "
                            "different fact from the same name in twenty-five production "
                            "modules, and the count above cannot tell them apart."
                        ),
                        limitations=(
                            "A test naming a backend may be exercising the seam that keeps "
                            "it contained, or may be reaching around it exactly as "
                            "production code would. Which of the two it is cannot be seen "
                            "by counting."
                        ),
                    ),
                    FindingMeasurement(
                        name="of_those_that_reach_it",
                        value=float(len(reaching)),
                        unit="modules",
                        nature=MetricNature.MEASUREMENT,
                        definition=(
                            "Of the modules above, those with a resolved import, call, "
                            "reference, inheritance or implementation edge into the owning "
                            "module. The rest name it without reaching it: the name is "
                            "written into them rather than depended on."
                        ),
                        limitations=(
                            "Resolved statically. An edge made at run time — a dynamic "
                            "import, a registry lookup, a name assembled from parts — is "
                            "not here, so a module counted as naming without reaching may "
                            "still reach it by a route this cannot see."
                        ),
                    ),
                ],
                relationships=_reaching_edges(outside, path, reach),
                limitations=_SCATTERED_CONCEPT_LIMITS,
            )
        )
    return candidates


def _reaching_edges(
    outside: list[ModuleFacts],
    owner_path: str,
    reach: dict[tuple[str, str], list[AtlasEdge]],
) -> list[AtlasEdge]:
    """One edge per naming module per kind, into the module that owns the name.

    Bounded that way because the reader and the judge want placement, not traffic: that a
    module imports the owner is the fact, and that it imports it eleven times is a number
    neither of them is being asked about. Eleven lines saying the same thing would push the
    modules that reach it *nowhere* — the ones the finding is actually about — off the end
    of a prompt.

    Deterministic in both directions: the modules in the order the candidate lists them,
    the kinds sorted, and the first edge of each kind. Two runs over one repository state
    the same relationships in the same order or the fingerprint over them is noise.
    """

    chosen: list[AtlasEdge] = []
    for module in outside:
        found = reach.get((module.path, owner_path), [])
        by_kind: dict[str, AtlasEdge] = {}
        for edge in found:
            by_kind.setdefault(edge.edge_type.value, edge)
        chosen.extend(by_kind[kind] for kind in sorted(by_kind))
    return chosen


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

    Deliberately blunt — a shared prefix rather than a stemmer. The question it answers is
    only "is this the same word", and `voices`/`voice` is the shape that keeps arising. The
    minimum length keeps short words like `id` or `run` from matching everything.

    A shared prefix rather than one word starting with the other, because the two endings
    can both be suffixes: `investigation` and `investigator` are the same term and neither
    contains the other. This admits everything the containment test admitted — a contained
    word shares its whole length as a prefix — so it can only ever treat more pairs as one
    word, which is the safe direction for a guard that suppresses candidates.
    """

    if len(concept) < minimum or len(word) < minimum:
        return concept == word
    return concept[:minimum] == word[:minimum]


def _names_things_after_itself(
    concept: str, path: str, nodes: dict[str, AtlasNode]
) -> bool:
    """Whether the owning module declares anything its own name *qualifies*.

    The test for "is this word a name, or the kind of thing this file holds". It is a
    grammatical question and the grammar is the evidence: a proper noun modifies, and the
    word it modifies is the subject. `QwenSpeechProvider` is a speech provider that is
    Qwen's; `NorthwindFeed` is a feed that is Northwind's. Every use of those elsewhere is
    a use of this vendor, because nothing else in the repository would have said the word.

    A category noun is the other way round — it is what gets modified. `nodes.py` declares
    `load_context_node` and `report.py` declares `compose_markdown_report`: the word is the
    head, the file is named for the kind of thing inside it, and the repository is full of
    the word for reasons that have nothing to do with this module. `atlas.py` declaring
    `AtlasNode` is not `workflow/nodes.py` leaking.

    So the position is what is read, not the presence. Presence alone kept every one of
    those, because a module of `*_node` functions does carry its own name — as the part of
    the name that says nothing.

    A declaration that is only the word — a class called `Qwen` — counts. It cannot be
    modifying anything, but a file's whole subject being its name is the strongest form of
    the thing this is looking for, not a weaker one.
    """

    return any(
        node.node_type
        in (NodeType.CLASS, NodeType.INTERFACE, NodeType.FUNCTION, NodeType.METHOD)
        and _leads_with(concept, node.symbol_name)
        for node in nodes.values()
        if node.path == path
    )


def _leads_with(concept: str, name: str) -> bool:
    """Whether an identifier opens with a word, reading it as a reader would.

    Ordered, where `_words` is a set: the whole question here is which word came first.
    """

    spaced = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", " ", name)
    words = [word for word in re.split(r"[^A-Za-z0-9]+", spaced) if word]
    return bool(words) and _shares_a_stem(concept, words[0].casefold())
