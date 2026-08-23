"""Five read-only questions about one analysed repository, and the bounds that keep them small.

What this exists for is a defect in the questions a review asks. A judgement is shown the
candidate, the case and the pinned excerpts, and its own contract tells it not to hinge on
anything the repository would settle. With no way to look, it hinges anyway: whether a port
has a second implementation, whether anything calls the thing it flagged, whether a seam is
tested. Every one of those is a question for the code, and a person handed one learns that
the review did not check.

So the review may check. The five tools below answer the structural questions an
architecture verdict actually turns on — who implements this, who depends on it, what tests
it — and one of them reads the code at a node when the structure is not enough. There is
deliberately no repository-wide overview, no hotspot listing and no cycle report: a hinge is
about a named thing, and a tool that describes the whole repository is where a bounded check
turns into browsing nobody budgeted for.

Every bound here is a bound on one turn of a conversation that carries all of them at once.
A search reports at most `MAX_ROWS` rows and says when it cut, and every whole result is
clamped to `MAX_RESULT_CHARACTERS` — because the model sees every result it has asked for in
the next request, and one unbounded answer would spend the context the verdict needs.

The atlas is the one this review analysed, passed in rather than fetched. A review never
persists its atlas, so a toolbox reading the latest *indexed* one could answer about a
different snapshot than the verdicts were reached against.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping, Sequence
from typing import cast

from pydantic import ValidationError

from archcompass.analysis.analyzer import analysis_atlas
from archcompass.analysis.atlas import (
    Atlas,
    AtlasEdge,
    AtlasMetricValue,
    AtlasNode,
    AtlasNodeSummary,
    AtlasQuery,
    AtlasQueryResult,
    NodeDetailsQuery,
    ObscuritySignal,
    RelationQuery,
    SearchNodesQuery,
    SignalsQuery,
    SourceExcerpt,
    SourceExcerptQuery,
)
from archcompass.analysis.ports import AtlasQueryService
from archcompass.domain import RepositoryAtlas, RepositoryRef
from archcompass.domain.errors import ArchCompassError
from archcompass.reasoning.ports import (
    OfferedInvestigator,
    RecordedLookup,
    ToolSpec,
)

#: How many rows one lookup reports. A symbol worth investigating participates in a handful
#: of relationships; a name that matches two hundred nodes is a common word, and the answer
#: to that is the count and the first few, not the list.
MAX_ROWS = 25

#: The ceiling on any one result, whichever tool produced it. Applied last and to the text
#: rather than to the rows, because the per-tool bounds multiply and it is the total the
#: next request has to carry.
MAX_RESULT_CHARACTERS = 2_500

#: How many lines one `read_code` serves. Larger than a detector's span and far smaller than
#: a module: the question being answered is "what does this actually do", and a whole file
#: asked for as one span would crowd out the judgement this lookup exists to improve.
MAX_READ_LINES = 80

_SEARCH_CODE = "search_code"
_DESCRIBE_CODE = "describe_code"
_RELATED_CODE = "related_code"
_READ_CODE = "read_code"
_FLAGGED_SIGNALS = "flagged_signals"

_RELATION_KINDS = (
    "direct_dependencies",
    "direct_dependants",
    "known_callers",
    "implementations",
    "related_tests",
)


class _Refused(Exception):
    """A lookup that cannot be carried out, carrying the sentence the model will read.

    An exception internally and never at the boundary: `call` catches it and returns its
    text. It exists so an argument check deep in a helper can decline without every caller
    above it having to thread a failure back by hand.
    """


def _text_argument(arguments: Mapping[str, object], name: str) -> str:
    value = arguments.get(name)
    if not isinstance(value, str) or not value.strip():
        raise _Refused(
            f"This tool needs a non-empty string {name!r}, and was given {value!r}."
        )
    return value.strip()


def _node_summary_text(node: AtlasNodeSummary) -> str:
    """One node, named the way the tools take it and with no internal handle in sight.

    The id used to lead this line, because it was what the next call needed. Nothing the
    model can call takes one now, so printing it would only teach the shape it no longer has.
    """

    where = node.path
    if node.location is not None:
        where += f":{node.location.start_line}-{node.location.end_line}"
    return f"  {node.qualified_name}  [{node.node_type.value}]  {where}"


def _edge_text(edge: AtlasEdge, names: Mapping[str, str]) -> str:
    source = names.get(edge.source_id, edge.source_id)
    target = names.get(edge.target_id, edge.target_id)
    # `resolved_by` is carried because it is the difference between "the parser saw this
    # call" and "the type checker established this conformance", and a verdict that rests
    # on the second is standing on firmer ground than one resting on the first.
    return f"  {source} --{edge.edge_type.value}--> {target}  (by {edge.resolved_by})"


def _metric_text(metric: AtlasMetricValue) -> str:
    line = f"  {metric.metric} = {metric.value} [{metric.nature.value}]"
    if metric.definition:
        line += f"; counts {metric.definition}"
    if metric.limitations:
        line += f"; cannot see {metric.limitations}"
    return line


def _signal_text(signal: ObscuritySignal) -> str:
    return f"  {signal.code}: {signal.message}"


def _excerpt_text(excerpt: SourceExcerpt) -> str:
    return (
        f"  {excerpt.location.path}:{excerpt.location.start_line}-"
        f"{excerpt.location.end_line}\n{excerpt.text}"
    )


def _rows(lines: list[str]) -> list[str]:
    """At most `MAX_ROWS` of them, and a line saying so when there were more.

    Said per list rather than once for the whole answer: a query that returns thirty nodes
    and two edges cut only the nodes, and one note covering both would leave a reader
    guessing which.
    """

    if len(lines) <= MAX_ROWS:
        return lines
    return [*lines[:MAX_ROWS], f"  ... and {len(lines) - MAX_ROWS} more."]


def _result_text(result: AtlasQueryResult, names: Mapping[str, str]) -> str:
    """One query's answer as text the model reads, rather than as a serialised record.

    A Pydantic dump of `AtlasQueryResult` is mostly nulls — every query fills a few of its
    fields and leaves the rest empty — so it would spend the budget on schema. The summary
    is already a sentence the query service wrote for a reader; everything under it is the
    rows that sentence is about.
    """

    blocks = [
        *([result.summary] if result.summary else []),
        *_rows([_node_summary_text(node) for node in result.node_summaries]),
        *_rows([_edge_text(edge, names) for edge in result.relationships]),
        *_rows([_metric_text(item) for item in result.metric_values]),
        *_rows([_signal_text(item) for item in result.signals]),
        *[_excerpt_text(item) for item in result.excerpts],
    ]
    return "\n".join(blocks) if blocks else "Nothing matched."


class AtlasInvestigator:
    """The five tools, bound to one review's atlas, recording as they go.

    Built per investigation, at the call site, from the atlas the run has already analysed.
    That is why there is no freshness logic here for the structural questions: they are
    answered from records in memory, and the records are the ones the verdicts were reached
    against. Only `read_code` touches the disk, and the query service asks about freshness
    on that branch itself.

    The model never sees an atlas node id. It names things the way the review already names
    them — `ports.TaskStore` — and `_resolve` turns that into the id, against this atlas and
    no other. Node ids used to be the model's to carry: `find_code` handed them out and every
    other tool demanded one back, so an investigation could not begin without spending a turn
    converting a name it already had into a handle. Measured on a live run, a model spent six
    of its six turns discovering that convention, having reasonably tried the only ids it had
    been shown. The handle is internal now, which is what it always was.
    """

    def __init__(
        self,
        queries: AtlasQueryService,
        atlas: Atlas,
        repository: RepositoryRef,
    ) -> None:
        self._queries = queries
        self._atlas = atlas
        self._repository = repository
        self._transcript: list[RecordedLookup] = []
        self._closing = ""
        self._abandoned = ""
        self._by_name: defaultdict[str, list[AtlasNode]] = defaultdict(list)
        for node in atlas.nodes:
            self._by_name[node.qualified_name].append(node)
        # Every node, not only the ones an answer lists: an edge's far end is usually not in
        # the rows above it, and rendering that end as an id was the last place an internal
        # handle reached the model.
        self._names = {node.atlas_id: node.qualified_name for node in atlas.nodes}

    def _resolve(self, arguments: Mapping[str, object]) -> str:
        """One qualified name, against this atlas, to exactly one node or to a refusal.

        Exact, unique, pinned — or fail. Never a close match, never the first of several,
        never a node from a rebuilt atlas: a name that resolves to the wrong thing is
        recorded for ever as a correct lookup, which is the failure the whole identifier
        rule exists to prevent. Ambiguity is reported with the choices, because a model
        cannot pick between candidates it has not been shown.
        """

        name = _text_argument(arguments, "qualified_name")
        found = self._by_name.get(name, [])
        kind = arguments.get("kind")
        if isinstance(kind, str) and kind.strip():
            found = [node for node in found if node.node_type.value == kind.strip()]
        if not found:
            raise _Refused(
                f"Nothing in this repository is called {name!r}. Names are exact and "
                f"qualified, like 'ports.TaskStore' or 'adapters.SqliteTaskStore.save'. "
                f"If you do not know the exact name, use {_SEARCH_CODE} to find it."
            )
        if len(found) > 1:
            choices = ", ".join(
                sorted(f"kind={node.node_type.value!r}" for node in found)
            )
            raise _Refused(
                f"{name!r} is the name of more than one thing here. Ask again with one of: "
                f"{choices}."
            )
        return found[0].atlas_id

    @property
    def tools(self) -> Sequence[ToolSpec]:
        """The five, described for the model that has to choose between them.

        The descriptions say when *not* to call as well as what the call does. A tool
        described only by its mechanism gets called speculatively, and every speculative call
        is a turn spent and a result the next request has to carry.

        Four of the five take a qualified name, which is what the finding under investigation
        already calls things. `search_code` is the fallback for when the exact name is not
        known — search when you do not know, inspect when you do — rather than the mandatory
        first step it was when the others wanted an internal handle.
        """

        return (
            ToolSpec(
                name=_SEARCH_CODE,
                description=(
                    "Search this repository for parts whose name or path matches a piece of "
                    "text — a class, a function, a module. Use it only when you do not "
                    "already know the exact qualified name: the other tools take the name "
                    "directly, so there is nothing to look up first. Do not call it with a "
                    "phrase or a sentence; a bare identifier matches more. At most "
                    f"{MAX_ROWS} rows are reported."
                ),
                parameters={
                    "type": "object",
                    "properties": {
                        "name": {
                            "type": "string",
                            "description": (
                                "The name to look for. Matched against symbol names, "
                                "qualified names and paths, ignoring case."
                            ),
                        }
                    },
                    "required": ["name"],
                    "additionalProperties": False,
                },
            ),
            ToolSpec(
                name=_DESCRIBE_CODE,
                description=(
                    "Describe one part of this repository: what kind of thing it is, where "
                    "it is written, what was measured about it and what the analysis flagged "
                    "on it. Use it when you need to know what something is before deciding "
                    "what its relationships mean."
                ),
                parameters={
                    "type": "object",
                    "properties": {
                        "qualified_name": {
                            "type": "string",
                            "description": (
                                "The exact qualified name, as the candidate under "
                                "investigation writes it: 'ports.TaskStore', "
                                "'adapters.SqliteTaskStore.save'. Not a search term."
                            ),
                        },
                        "kind": {
                            "type": "string",
                            "description": (
                                "Only needed when a name turns out to mean more than one "
                                "thing; the refusal says so and names the kinds."
                            ),
                        },
                    },
                    "required": ["qualified_name"],
                    "additionalProperties": False,
                },
            ),
            ToolSpec(
                name=_RELATED_CODE,
                description=(
                    "Ask what stands in a given relationship to one part of this repository. "
                    "'implementations' answers whether an abstraction has one implementation "
                    "or several; 'direct_dependants' and 'known_callers' answer whether "
                    "anything actually uses it; 'related_tests' answers whether it is tested; "
                    "'direct_dependencies' answers what it reaches for. This is the tool that "
                    "settles most hinges."
                ),
                parameters={
                    "type": "object",
                    "properties": {
                        "qualified_name": {
                            "type": "string",
                            "description": (
                                "The exact qualified name, as the candidate under "
                                "investigation writes it: 'ports.TaskStore'."
                            ),
                        },
                        "relation": {"type": "string", "enum": list(_RELATION_KINDS)},
                        "kind": {
                            "type": "string",
                            "description": (
                                "Only needed when a name turns out to mean more than one "
                                "thing; the refusal says so and names the kinds."
                            ),
                        },
                    },
                    "required": ["qualified_name", "relation"],
                    "additionalProperties": False,
                },
            ),
            ToolSpec(
                name=_READ_CODE,
                description=(
                    "Read the source of one part of this repository. Use it only when the "
                    "structure does not settle your question and what the code actually does "
                    "would — not to confirm something a relationship already told you. At "
                    f"most {MAX_READ_LINES} lines are served."
                ),
                parameters={
                    "type": "object",
                    "properties": {
                        "qualified_name": {
                            "type": "string",
                            "description": (
                                "The exact qualified name, as the candidate under "
                                "investigation writes it: 'ports.TaskStore', "
                                "'adapters.SqliteTaskStore.save'. Not a search term."
                            ),
                        },
                        "kind": {
                            "type": "string",
                            "description": (
                                "Only needed when a name turns out to mean more than one "
                                "thing; the refusal says so and names the kinds."
                            ),
                        },
                    },
                    "required": ["qualified_name"],
                    "additionalProperties": False,
                },
            ),
            ToolSpec(
                name=_FLAGGED_SIGNALS,
                description=(
                    "List what the deterministic analysis already flagged across this "
                    "repository, optionally narrowed to particular codes. Use it to find out "
                    "whether the thing you are judging is one instance of something wider. "
                    "Takes no name."
                ),
                parameters={
                    "type": "object",
                    "properties": {
                        "codes": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Signal codes to narrow to. Omit for all of them.",
                        }
                    },
                    "required": [],
                    "additionalProperties": False,
                },
            ),
        )

    def call(self, name: str, arguments: Mapping[str, object]) -> str:
        """Run one lookup and return what it found. This never raises — see the port."""

        try:
            result = self._answer(name, arguments)
        except _Refused as refusal:
            result = str(refusal)
        except ArchCompassError as error:
            # Every application error is already written for a reader, so it is handed on
            # as it stands. A stale repository is the one that matters: it means the source
            # cannot be read, and the model has to be told that rather than left to read a
            # refusal as "there is nothing there".
            result = str(error)
        except ValidationError as error:
            result = f"That request was not a valid lookup: {error.error_count()} problems."
        # Clamped here, once, so it cannot be forgotten by whichever tool is added next, and
        # recorded clamped because the clamped text is what the model was actually shown.
        if len(result) > MAX_RESULT_CHARACTERS:
            note = "\n... truncated: this result was cut at "
            keep = MAX_RESULT_CHARACTERS - len(note) - 20
            result = result[:keep] + note + f"{MAX_RESULT_CHARACTERS} characters."
        self._transcript.append(RecordedLookup(name, dict(arguments), result))
        return result

    def _answer(self, name: str, arguments: Mapping[str, object]) -> str:
        if name == _SEARCH_CODE:
            return self._execute(
                SearchNodesQuery(
                    kind="search_nodes",
                    terms=[_text_argument(arguments, "name")],
                    limit=MAX_ROWS,
                )
            )
        if name == _DESCRIBE_CODE:
            return self._execute(
                NodeDetailsQuery(kind="node_details", node_id=self._resolve(arguments))
            )
        if name == _RELATED_CODE:
            relation = _text_argument(arguments, "relation")
            if relation not in _RELATION_KINDS:
                raise _Refused(
                    f"There is no relationship called {relation!r}. The relationships this "
                    f"repository can be asked about are {', '.join(_RELATION_KINDS)}."
                )
            return self._execute(
                RelationQuery(
                    kind=relation,  # pyright: ignore[reportArgumentType]
                    node_id=self._resolve(arguments),
                    limit=MAX_ROWS,
                )
            )
        if name == _READ_CODE:
            return self._execute(
                SourceExcerptQuery(
                    kind="source_excerpt",
                    node_id=self._resolve(arguments),
                    max_lines=MAX_READ_LINES,
                )
            )
        if name == _FLAGGED_SIGNALS:
            requested = arguments.get("codes")
            codes: list[object] = (
                list(cast("list[object]", requested)) if isinstance(requested, list) else []
            )
            return self._execute(
                SignalsQuery(
                    kind="signals",
                    # Coerced rather than validated: a model that sent a number for a
                    # signal code meant a code, and refusing the call would spend a turn
                    # teaching it something the empty result already teaches.
                    codes=[str(item) for item in codes][:10],
                    limit=MAX_ROWS,
                )
            )
        offered = ", ".join(spec.name for spec in self.tools)
        raise _Refused(f"There is no tool called {name!r}. The tools available are {offered}.")

    def _execute(self, query: AtlasQuery) -> str:
        return _result_text(self._queries.execute(self._atlas, query), self._names)

    @property
    def transcript(self) -> Sequence[RecordedLookup]:
        return tuple(self._transcript)

    def conclude(self, closing: str, abandoned: str) -> None:
        self._closing = closing
        self._abandoned = abandoned

    @property
    def closing(self) -> str:
        return self._closing

    @property
    def abandoned(self) -> str:
        return self._abandoned


class AtlasInvestigatorSource:
    """A toolbox over whichever atlas a review is holding, or the reason there is none."""

    def __init__(self, queries: AtlasQueryService) -> None:
        self._queries = queries

    def for_review(
        self, repository: RepositoryRef, atlas: RepositoryAtlas
    ) -> OfferedInvestigator:
        if not atlas.nodes:
            return OfferedInvestigator(
                withheld=(
                    "This review holds no analysed structure, so nothing could be looked "
                    "up. Index the repository and run the review again."
                )
            )
        try:
            analysed = analysis_atlas(atlas)
        except ValidationError:
            # An atlas an earlier parser wrote, whose records this build can no longer
            # read. Named rather than raised: the review is mid-flight and its verdicts are
            # sound, and the honest outcome is a hinge that says nobody could check it.
            return OfferedInvestigator(
                withheld=(
                    "This review's stored structure was written by an earlier version of "
                    "ArchCompass and cannot be read, so nothing could be looked up. Index "
                    "the repository again to restore lookups."
                )
            )
        return OfferedInvestigator(AtlasInvestigator(self._queries, analysed, repository))
