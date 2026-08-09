"""How the flagged code is actually used, attached to the candidate before it is judged.

A detector reports a shape: two modules state `RETRY_LIMIT`, one abstraction has one
implementation behind it. What it cannot report is the thing the verdict actually turns on
— who reads those two constants, and what depends on that seam — because that is a fact
about the rest of the repository rather than about the participants. So the judging stage
was shown a shape and asked whether it was one fact or two, which is a question about usage,
and answered it from two identifiers that happened to be spelled the same. On a seeded bench
it gave both answers to the same input on different runs (docs/plans/investigation-quality.md).

This module is the correction, and its whole design is in who does the choosing. The
application walks the repository, deterministically and with a fixed cap, and appends what
it finds as ordinary `FindingParticipant`s. Nothing about that is new machinery: excerpt
pinning, source rendering, the conversation stages and the fingerprints all already know
what a participant is, so usage inherits every one of them by being one. §12.0 needs no
amendment either — a verdict still rests on spans the application picked, and the model is
still given no way to go looking.

The fingerprint inheritance is deliberate and is the point rather than a side effect. A
candidate's boundary and content fingerprints are computed over its participants, so a
verdict cached against usage dies the moment usage changes — which is what verdict reuse
should always have meant. It also means no stored verdict survives this change, and that is
disclosed rather than shimmed (ADR 0017).

Two shapes are augmented and one is not. `scattered_concept` already records every
mentioning module as a participant — its detector's whole method is the name search this
module would otherwise repeat — so it is returned exactly as detected. `sole_implementation`
is answered from the graph, because the atlas already holds the `IMPORTS`, `CALLS` and
`REFERENCES` edges that name a dependant. Only `duplicated_knowledge` needs text, because a
constant read by name leaves no edge, and that search goes through the analyser's own file
discipline — `searchable_files` and `numbered_lines`, imported from the investigation
toolbox rather than copied — so a consumer found here is a line the analysis had also read.

Nothing here reads a *span*: it looks for a name and records where it occurred. The code at
these coordinates is read once, later, by `ReviewSourceService`, which stays the one path
that turns a recorded location into text.
"""

from __future__ import annotations

from collections import defaultdict
from pathlib import Path

from archcompass.application.investigation import numbered_lines, searchable_files
from archcompass.domain.atlas import (
    Atlas,
    AtlasNode,
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

#: How many usage participants one candidate may gain. A boundary read in forty places is a
#: finding in its own right, and the measurement is where that finding belongs: forty spans
#: would spend the judging payload on repetition of the same fact, and the caps on excerpts
#: downstream would then decide which of them the model saw.
MAX_USAGE_PARTICIPANTS = 6

#: The edge kinds that make a node a dependant of a seam. `IMPLEMENTS` and `INHERITS` are
#: absent on purpose: they are what the candidate already reports, not what depends on it.
_DEPENDANT_EDGES = (EdgeType.IMPORTS, EdgeType.CALLS, EdgeType.REFERENCES)

_DEPENDANT_VERBS = {
    EdgeType.IMPORTS: "Imports",
    EdgeType.CALLS: "Calls",
    EdgeType.REFERENCES: "References",
}

#: What a name search cannot establish, stated on the measurement it produced.
_CONSUMER_LIMITS = (
    "Counted by exact name over the source and configuration files of this snapshot, "
    "excluding the lines that state the constant. A line containing the name is not proof "
    "that it reads this constant — a comment, a docstring or a longer identifier containing "
    "it counts — and a copy reached through an alias or an attribute of an imported module "
    "is not counted at all."
)

_DEPENDANT_LIMITS = (
    "Counted from statically resolved imports, calls and references reaching either side of "
    "the boundary in this snapshot. A dependant wired at runtime is not visible, and a "
    "reference is not evidence that the indirection is or is not earning its place."
)


class UsageEvidenceService:
    """Attach usage to candidates, as participants and as counts, before anything judges them.

    No dependencies, and that is worth stating because it looks like an omission. Discovery
    here is a scan for a name and a walk over edges the atlas already holds; the reading of
    code at a span — the part that must never escape the analysed repository — happens in
    `ReviewSourceService` through the one `SourceReader`, from the locations this records.
    Handing this a second reader would create a second path that reads source, which is the
    thing there is deliberately only one of.
    """

    def augment(
        self,
        candidates: list[FindingCandidate],
        atlas: Atlas,
        root: Path,
    ) -> list[FindingCandidate]:
        """The same candidates, each carrying who uses it, in the order they arrived.

        New values rather than edits, because a candidate is frozen — and because the
        detectors stay pure derivations over an atlas, which is what lets them be tested
        without a repository on disk.

        The repository is read here, so this runs where the caller already knows the atlas
        matches what is on disk: `ReviewService.review` has just checked freshness, and a
        second check would be asking a question already answered.
        """

        names = _constant_names(atlas.module_facts)
        nodes = {node.atlas_id: node for node in atlas.nodes}
        modules_by_path = {
            node.path: node for node in atlas.nodes if node.node_type is NodeType.MODULE
        }
        # One sweep of the repository for every constant at once. A review routinely detects
        # a dozen duplicated constants and the files are the same files each time, so a scan
        # per candidate would open the whole repository a dozen times to answer one question
        # per pass.
        wanted = set(names.values())
        occurrences = _occurrences(root, wanted) if wanted else {}
        return [
            self._augmented(candidate, atlas, nodes, modules_by_path, names, occurrences)
            for candidate in candidates
        ]

    def _augmented(
        self,
        candidate: FindingCandidate,
        atlas: Atlas,
        nodes: dict[str, AtlasNode],
        modules_by_path: dict[str, AtlasNode],
        names: dict[tuple[tuple[str, str, int], ...], str],
        occurrences: dict[str, list[tuple[str, int]]],
    ) -> FindingCandidate:
        if candidate.pattern is FindingPattern.DUPLICATED_KNOWLEDGE:
            name = names.get(_signature(candidate))
            if name is None:
                # A duplication candidate whose group this cannot recover. It can only mean
                # the atlas and the candidate came from different runs, and the honest
                # answer is to leave the candidate exactly as detected rather than attach
                # somebody else's consumers to it.
                return candidate
            return _with_consumers(
                candidate, name, occurrences.get(name, []), modules_by_path
            )
        if candidate.pattern is FindingPattern.SOLE_IMPLEMENTATION:
            return _with_dependants(candidate, atlas, nodes)
        # scattered_concept, unchanged and deliberately so: its detector's method *is* a name
        # search across modules, and every module it found is already a participant with the
        # line it names the concept on. Adding usage here would be running the same search
        # twice and reporting the second run's hits as new evidence.
        return candidate


def _constant_names(
    module_facts: list[ModuleFacts],
) -> dict[tuple[tuple[str, str, int], ...], str]:
    """Each duplication group's identity, mapped to the constant name behind it.

    The grouping is `duplicated_knowledge_candidates`' grouping, repeated rather than shared,
    because what is needed here is the inverse of what the detector returns: it produces
    candidates and discards the name, and this has a candidate and needs the name back.

    Recovered through the participants and never by reading the summary. The summary is prose
    written for a person — it names a count and says whether the copies agree — and parsing it
    back would quietly make it a data format, so a better sentence in it would change which
    consumers a candidate is judged with.
    """

    by_name: dict[str, list[tuple[str, str, int]]] = defaultdict(list)
    for module in module_facts:
        for constant in module.constants:
            by_name[constant.name].append((module.node_id, module.path, constant.line))

    groups: dict[tuple[tuple[str, str, int], ...], str] = {}
    for name, statements in sorted(by_name.items()):
        if len({node_id for node_id, _, _ in statements}) < 2:
            continue
        groups[tuple(sorted(statements, key=lambda item: (item[1], item[2])))] = name
    return groups


def _signature(candidate: FindingCandidate) -> tuple[tuple[str, str, int], ...]:
    """The same identity, read off a candidate's participants."""

    return tuple(
        sorted(
            (
                (participant.node_id, participant.location.path, participant.location.start_line)
                for participant in candidate.participants
                if participant.location is not None
            ),
            key=lambda item: (item[1], item[2]),
        )
    )


def _occurrences(root: Path, names: set[str]) -> dict[str, list[tuple[str, int]]]:
    """Every line of the repository containing each name, as (path, line), in path order.

    One pass, all names, because the cost here is opening the files rather than testing the
    text. Definition lines are still in this result — the caller knows which of them are its
    own, and a sweep shared between candidates cannot.
    """

    found: dict[str, list[tuple[str, int]]] = {name: [] for name in names}
    for path in searchable_files(root):
        relative = path.relative_to(root).as_posix()
        for number, line in numbered_lines(path):
            for name in names:
                if name in line:
                    found[name].append((relative, number))
    return found


def _with_consumers(
    candidate: FindingCandidate,
    name: str,
    occurrences: list[tuple[str, int]],
    modules_by_path: dict[str, AtlasNode],
) -> FindingCandidate:
    """The candidate, plus the modules that read one of its copies.

    A hit in a file the atlas holds no module node for — a TOML settings file, a shell
    script's configuration block — is counted and not shown. It has no node id and no
    qualified name, so a participant made from it would put a node in the record that the
    atlas cannot resolve; the count is what keeps it from disappearing, and the measurement's
    two values are what make "three found, two shown" a fact the reader of the payload has.
    """

    definitions = {
        (participant.location.path, participant.location.start_line)
        for participant in candidate.participants
        if participant.location is not None
    }
    consuming = [site for site in sorted(occurrences) if site not in definitions]
    shown = [
        FindingParticipant(
            node_id=modules_by_path[path].atlas_id,
            qualified_name=modules_by_path[path].qualified_name,
            location=SourceLocation(path=path, start_line=line, end_line=line),
            role=f"Names {name} on line {line} — a consumer of one of the copies.",
        )
        for path, line in consuming
        if path in modules_by_path
    ][:MAX_USAGE_PARTICIPANTS]
    return candidate.model_copy(
        update={
            "participants": [*candidate.participants, *shown],
            "measurements": [
                *candidate.measurements,
                *_shown_of_found(
                    name="consumer_sites",
                    unit="lines",
                    found=len(consuming),
                    shown=len(shown),
                    definition=(
                        "Lines outside the copies themselves that name this constant, as a "
                        "proxy for what reads it. Copies read by the same code are evidence "
                        "the copies are one fact; copies read by unrelated code are evidence "
                        "they only share a name."
                    ),
                    caveat=(
                        "A line in a file the atlas holds no module for — configuration, "
                        "most often — is counted here and cannot be shown as a participant."
                    ),
                    limitations=_CONSUMER_LIMITS,
                ),
            ],
        }
    )


def _with_dependants(
    candidate: FindingCandidate,
    atlas: Atlas,
    nodes: dict[str, AtlasNode],
) -> FindingCandidate:
    """The candidate, plus what depends on either side of the seam.

    Either side, not only the abstraction. A caller that reaches past the port and names the
    adapter is the strongest evidence there is that the indirection is not doing its job, and
    counting only the abstraction's dependants would leave it invisible.

    One participant per dependant node rather than per edge: a module that imports the port
    and calls it three times is one dependant, and four spans of it would spend the cap on
    one module.
    """

    sides = {participant.node_id for participant in candidate.participants}
    named = {
        participant.node_id: participant.qualified_name
        for participant in candidate.participants
    }
    first_edge: dict[str, tuple[EdgeType, str, SourceLocation | None]] = {}
    for edge in atlas.edges:
        if edge.edge_type not in _DEPENDANT_EDGES or edge.target_id not in sides:
            continue
        if edge.source_id in sides or edge.source_id not in nodes:
            continue
        if edge.source_id in first_edge:
            continue
        first_edge[edge.source_id] = (
            edge.edge_type,
            named[edge.target_id],
            # The edge's own location where it has one, because that is where the dependency
            # is written; the dependant's declaration otherwise, so a participant always has
            # somewhere for its code to be read from.
            edge.location or _declaration(nodes[edge.source_id]),
        )
    dependants = sorted(
        (
            FindingParticipant(
                node_id=node_id,
                qualified_name=nodes[node_id].qualified_name,
                location=location,
                role=f"{_DEPENDANT_VERBS[edge_type]} {target} — a dependant of this seam.",
            )
            for node_id, (edge_type, target, location) in first_edge.items()
        ),
        key=_ordering,
    )
    return candidate.model_copy(
        update={
            "participants": [*candidate.participants, *dependants[:MAX_USAGE_PARTICIPANTS]],
            "measurements": [
                *candidate.measurements,
                *_shown_of_found(
                    name="dependant_sites",
                    unit="modules",
                    found=len(dependants),
                    shown=len(dependants[:MAX_USAGE_PARTICIPANTS]),
                    definition=(
                        "Nodes that import, call or reference either the abstraction or its "
                        "one implementation, as a proxy for how much code the indirection "
                        "sits in front of. A dependant naming the implementation directly is "
                        "code the seam is not standing between."
                    ),
                    caveat="",
                    limitations=_DEPENDANT_LIMITS,
                ),
            ],
        }
    )


def _declaration(node: AtlasNode) -> SourceLocation | None:
    if node.start_line is None or node.end_line is None:
        return None
    return SourceLocation(path=node.path, start_line=node.start_line, end_line=node.end_line)


def _ordering(participant: FindingParticipant) -> tuple[str, int]:
    """By path and then line, so which participants a cap keeps is a fact about the code.

    A participant with no recorded span sorts last under an empty path, which is where a
    thing with no coordinates belongs when the cap has to choose.
    """

    if participant.location is None:
        return ("￿", 0)
    return (participant.location.path, participant.location.start_line)


def _shown_of_found(
    *,
    name: str,
    unit: str,
    found: int,
    shown: int,
    definition: str,
    caveat: str,
    limitations: str,
) -> list[FindingMeasurement]:
    """Two measurements, because "five of forty" is two numbers and neither implies the other.

    Always both, and always even when the answer is zero. A candidate carrying no usage
    measurement at all is one nobody checked; a candidate saying zero is one that was checked
    and found nothing, and a stage that cannot tell those apart will treat the first as the
    second every time.
    """

    return [
        FindingMeasurement(
            name=name,
            value=float(found),
            unit=unit,
            nature=MetricNature.STRUCTURAL_PROXY,
            definition=" ".join(filter(None, (definition, caveat))),
            limitations=limitations,
        ),
        FindingMeasurement(
            name=f"{name}_shown",
            value=float(shown),
            unit=unit,
            nature=MetricNature.MEASUREMENT,
            definition=(
                f"How many of those are attached to this candidate as participants, with "
                f"their code. Ordered by path and line and capped at {MAX_USAGE_PARTICIPANTS}"
                ", so a boundary used far more than that is stated in full above and shown "
                "in part."
            ),
            limitations=(
                "The unshown remainder is a number and nothing else: no claim is made here "
                "about what the sites this did not attach contain."
            ),
        ),
    ]
