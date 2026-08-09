"""Two read-only tools over one analysed repository, and the bounds that keep them small.

What this exists for is a defect in the questions a review asks. `elicit_questions` is shown
the verdicts, the case and the pinned excerpts, and from that it composes what to put to a
person — while its own contract tells it not to ask anything the repository would settle.
With no way to look, it asks anyway: how a flagged symbol is used, whether two constants
really state one fact, whether a configuration value is read at all. Every one of those is a
question for the code, and a reader handed one learns that the review did not check.

So the stage may check. `search_source` finds where a name occurs and `read_source` shows
the lines around it, and between them they answer the three kinds of question above. There
is deliberately no third tool: a listing, a symbol index or a git log would each widen this
from "confirm the thing you are about to ask about" into browsing, and browsing is where a
bounded investigation turns into an agent loop nobody budgeted for.

Every bound here is a bound on one turn of a conversation that carries all of them at once.
A search reports at most `MAX_SEARCH_HITS` lines and says when it cut, a read serves at most
`MAX_READ_LINES`, each matched line is clamped and so is each whole result — because the
model sees every result it has asked for in the next request, and a single unbounded answer
would spend the context the questions themselves need.

Reading is through the same `SourceReader` the excerpts go through, so path traversal is
refused by machinery that already exists and is already tested; the search does its own file
discovery because there is nothing to point it at, and applies the analyser's own rules —
the same ignored directories, the same suffixes, symlinks skipped, one file open at a time.
A search that reported a match the analysis had never read would be describing a repository
that was not the one judged.
"""

from __future__ import annotations

from collections.abc import Iterator, Mapping, Sequence
from pathlib import Path

from archcompass.domain.errors import PathValidationError
from archcompass.domain.scope import CONFIG_SUFFIXES, IGNORED_DIRECTORIES
from archcompass.ports.atlas import SourceReader
from archcompass.ports.investigation import RecordedLookup, ToolSpec

#: How many matching lines one search reports. A symbol worth investigating occurs a handful
#: of times; a name that occurs two hundred times is a common word, and the answer to that
#: is the count and the first few, not the list.
MAX_SEARCH_HITS = 30

#: How much of a matched line is shown. A minified bundle or a long data literal is one line
#: and would otherwise spend a whole result on itself, and what the model needs from a hit is
#: enough context to decide whether to read the span properly.
MAX_SEARCH_LINE_CHARACTERS = 200

#: How many lines one read serves, counted from the line asked for. Larger than a detector's
#: span and far smaller than a module: the question being answered is "what does this
#: function actually do with it", and a whole file asked for as one span would crowd out the
#: questions this investigation exists to improve.
MAX_READ_LINES = 80

#: The ceiling on any one result, whichever tool produced it. Applied last and to the text
#: rather than to the lines, because the per-tool bounds multiply — thirty clamped hits is
#: six thousand characters — and it is the total the next request has to carry.
MAX_RESULT_CHARACTERS = 4_000

#: Files above this are not searched. The same reasoning as the analyser's own file cap and
#: the same measurement point: asked of the directory entry, so an oversized file is never
#: read at all rather than read and then discarded.
MAX_SEARCHED_FILE_BYTES = 1_048_576

_SEARCH_SOURCE = "search_source"
_READ_SOURCE = "read_source"


class _Refused(Exception):
    """A lookup that cannot be carried out, carrying the sentence the model will read.

    An exception internally and never at the boundary: `call` catches it and returns its
    text. It exists so an argument check deep in a helper can decline without every caller
    above it having to thread a failure back by hand.
    """


def _text_argument(arguments: Mapping[str, object], name: str) -> str:
    value = arguments.get(name)
    if not isinstance(value, str) or not value:
        raise _Refused(f"This tool needs a non-empty string {name!r}, and was given {value!r}.")
    return value


def _line_argument(arguments: Mapping[str, object], name: str) -> int:
    value = arguments.get(name)
    # `bool` is an `int` in Python, and `True` as a line number is a mistake rather than
    # line 1 — a model that sent it meant something else entirely.
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise _Refused(
            f"This tool needs a positive whole-number {name!r}, and was given {value!r}."
        )
    return value


class RepositoryInvestigator:
    """The two tools, bound to one repository root, recording as they go.

    Built per elicitation, at the call site, after the repository has been confirmed fresh.
    That is why there is no freshness logic here: the run that constructs this has already
    established that the code on disk is the code the verdicts were reached against, and a
    second check would be asking a question already answered — with the added cost that this
    one would have to answer it mid-investigation, where the only honest reply is to abandon
    the whole thing.
    """

    def __init__(self, *, root: Path, source_reader: SourceReader) -> None:
        self._root = root
        self._source_reader = source_reader
        self._transcript: list[RecordedLookup] = []
        self._closing = ""
        self._abandoned = ""

    @property
    def tools(self) -> Sequence[ToolSpec]:
        """Both tools, described for the model that has to choose between them.

        The descriptions say when *not* to call as well as what the call does. A tool
        described only by its mechanism gets called speculatively, and every speculative call
        is a turn spent and a result the next request has to carry.
        """

        return (
            ToolSpec(
                name=_SEARCH_SOURCE,
                description=(
                    "Find every line in this repository containing an exact piece of text — "
                    "a symbol, a constant's name, a configuration key. The match is literal "
                    "and case-sensitive, and each result is given as path:line: text so it "
                    "can be read properly with read_source. Use it to find out where "
                    "something is used before asking about it. Only source and configuration "
                    f"files are searched, and at most {MAX_SEARCH_HITS} lines are reported."
                ),
                parameters={
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": (
                                "The exact text to look for. A bare identifier finds more "
                                "than a phrase does."
                            ),
                        }
                    },
                    "required": ["query"],
                    "additionalProperties": False,
                },
            ),
            ToolSpec(
                name=_READ_SOURCE,
                description=(
                    "Read a span of one file of this repository, given its path relative to "
                    "the repository root. Use it after a search, to see what the code around "
                    f"a match actually does. At most {MAX_READ_LINES} lines are served, "
                    "counted from the line asked for."
                ),
                parameters={
                    "type": "object",
                    "properties": {
                        "path": {
                            "type": "string",
                            "description": (
                                "Path relative to the repository root, as a search result "
                                "reports it."
                            ),
                        },
                        "start_line": {"type": "integer", "minimum": 1},
                        "end_line": {"type": "integer", "minimum": 1},
                    },
                    "required": ["path", "start_line", "end_line"],
                    "additionalProperties": False,
                },
            ),
        )

    @property
    def transcript(self) -> Sequence[RecordedLookup]:
        return tuple(self._transcript)

    @property
    def closing(self) -> str:
        return self._closing

    @property
    def abandoned(self) -> str:
        return self._abandoned

    def conclude(self, closing: str, abandoned: str) -> None:
        """Take the loop's account of how the investigation ended and hold it.

        Held rather than acted on: nothing here reads either value, and the toolbox goes on
        answering calls afterwards exactly as it did before. It is a place to put the two
        facts the caller that stores this record cannot get from anywhere else — the run
        that built the investigator is not the loop that ended it, and the rendering the
        loop produces is spent on one request and gone.

        Both are read-only from outside, so an investigation cannot be given a closing it
        never reached, and the last call wins if the loop is ever driven twice.
        """

        self._closing = closing
        self._abandoned = abandoned

    def call(self, name: str, arguments: Mapping[str, object]) -> str:
        """One lookup, bounded, recorded, and never raised out of.

        The recording happens here rather than in each tool so it cannot be forgotten by
        whichever tool is added next, and it records the clamped text — what the model was
        actually shown — rather than what the tool produced before the bound was applied.
        """

        result = _clamped(self._answer(name, arguments))
        self._transcript.append(RecordedLookup(tool=name, arguments=dict(arguments), result=result))
        return result

    def _answer(self, name: str, arguments: Mapping[str, object]) -> str:
        try:
            if name == _SEARCH_SOURCE:
                return self._search(_text_argument(arguments, "query"))
            if name == _READ_SOURCE:
                return self._read(
                    _text_argument(arguments, "path"),
                    _line_argument(arguments, "start_line"),
                    _line_argument(arguments, "end_line"),
                )
        except _Refused as refusal:
            return str(refusal)
        return (
            f"There is no tool called {name!r}. The tools available are "
            f"{_SEARCH_SOURCE} and {_READ_SOURCE}."
        )

    def _search(self, query: str) -> str:
        """Every line containing this text, one file at a time, up to the hit ceiling.

        Counting past the ceiling rather than stopping at it, because "the first thirty of
        thirty-seven" and "all thirty" are different findings and a model shown the second
        when the first is true will quote the number. The extra work is a scan of text
        already being opened.
        """

        hits: list[str] = []
        beyond = 0
        for path in searchable_files(self._root):
            relative = path.relative_to(self._root).as_posix()
            for number, line in numbered_lines(path):
                if query not in line:
                    continue
                if len(hits) < MAX_SEARCH_HITS:
                    hits.append(f"{relative}:{number}: {_clipped(line)}")
                else:
                    beyond += 1
        if not hits:
            return f"No line in this repository's source or configuration files contains {query!r}."
        if beyond:
            hits.append(f"… {beyond} more matches not shown.")
        return "\n".join(hits)

    def _read(self, relative_path: str, start_line: int, end_line: int) -> str:
        """The asked-for span, clamped, headed by the span that was actually served.

        The header is not decoration. A request for eight hundred lines comes back as
        eighty, and a model that does not know which eighty will report the file as ending
        where its result did — the same failure a clipped excerpt carries a caption for.
        """

        try:
            text = self._source_reader.excerpt(
                root=self._root,
                relative_path=relative_path,
                start_line=start_line,
                end_line=end_line,
                max_lines=MAX_READ_LINES,
            )
        except (PathValidationError, OSError, UnicodeDecodeError) as error:
            return f"{relative_path} could not be read: {error}"
        shown = len(text.splitlines())
        if not shown:
            return (
                f"{relative_path} has no lines between {start_line} and {end_line}; the "
                "file is shorter than that."
            )
        return f"{relative_path}:{start_line}-{start_line + shown - 1}\n{text}"


def searchable_files(root: Path) -> Iterator[Path]:
    """The files an analysis of this repository would have read, in path order.

    The analyser's discipline rather than a copy of it: the same ignored directories and
    the same suffixes, imported. A search that answered from a `.git` object or a
    vendored bundle would be describing a repository nobody judged, and a search that
    missed a file the atlas holds would report a symbol as unused when it is not.

    Module-level and public because the model's search is no longer the only sweep over a
    repository's text: `application.usage_evidence` walks the same files to find what
    consumes a flagged constant, and two sweeps disagreeing about which files exist would
    let a candidate be judged against a repository the investigation cannot see.
    """

    for path in sorted(root.rglob("*")):
        relative_parts = path.relative_to(root).parts
        if any(part in IGNORED_DIRECTORIES for part in relative_parts):
            continue
        if path.is_symlink() or not path.is_file():
            continue
        # `.env` is matched by name because it has no suffix, exactly as the analyser
        # matches it. Included here without the analyser's opt-out: this reads the same
        # repository the atlas was built from, so a workspace that took `.env` files in
        # has already decided they are part of what a review may point at.
        if (
            path.suffix != ".py"
            and path.name != ".env"
            and path.suffix.casefold() not in CONFIG_SUFFIXES
        ):
            continue
        try:
            if path.stat().st_size > MAX_SEARCHED_FILE_BYTES:
                continue
        except OSError:
            continue
        yield path


def numbered_lines(path: Path) -> Iterator[tuple[int, str]]:
    """One file's lines, numbered, without holding the file in memory.

    A repository is searched whole, so the whole repository must never be resident at once
    (ADR 0015). A file that is not text at the encoding the analysis assumes contributes
    nothing rather than failing the search: it was never a file a review could quote.
    """

    try:
        with path.open(encoding="utf-8") as handle:
            for number, line in enumerate(handle, start=1):
                yield number, line.rstrip("\n")
    except (OSError, UnicodeDecodeError):
        return


def _clipped(line: str) -> str:
    stripped = line.strip()
    if len(stripped) <= MAX_SEARCH_LINE_CHARACTERS:
        return stripped
    # The ellipsis is counted inside the budget rather than added past it, so the bound is
    # the length of what is shown and not one character more.
    return stripped[: MAX_SEARCH_LINE_CHARACTERS - 1] + "…"


def _clamped(result: str) -> str:
    """One result cut to the ceiling, saying that it was cut.

    Said rather than left silent, for the reason a clipped excerpt says so: text that stops
    without explanation is read as text that ended, and the model would go on to report the
    absence of whatever came after it as a fact about the repository.
    """

    if len(result) <= MAX_RESULT_CHARACTERS:
        return result
    note = f"\n… truncated: this result was cut at {MAX_RESULT_CHARACTERS} characters."
    return result[: MAX_RESULT_CHARACTERS - len(note)] + note
