"""The toolbox a review may put questions to, and the bounds that keep it small."""

from __future__ import annotations

from pathlib import Path

from archcompass.analysis.adapters.query_service import DeterministicAtlasQueryService
from archcompass.analysis.adapters.source_reader import SafeSourceReader
from archcompass.analysis.analyzer import (
    DataclassRepositoryAnalyzer,
    analysis_atlas,
)
from archcompass.analysis.atlas import AtlasQueryResult
from archcompass.analysis.investigation import (
    MAX_RESULT_CHARACTERS,
    AtlasInvestigator,
    AtlasInvestigatorSource,
)
from archcompass.analysis.ports import AtlasSource
from archcompass.domain import RepositoryAtlas, RepositoryRef


class _NoScopes:
    def get(self, root: str) -> tuple[str, ...] | None:
        del root
        return None

    def set(self, root: str, excluded_paths: tuple[str, ...]) -> None:
        del root, excluded_paths


def _repository(tmp_path: Path) -> Path:
    root = tmp_path / "project"
    (root / "app").mkdir(parents=True)
    (root / "app" / "__init__.py").write_text("", encoding="utf-8")
    (root / "app" / "ports.py").write_text(
        "from typing import Protocol\n\n\nclass Sink(Protocol):\n"
        "    def write(self, value: str) -> None: ...\n",
        encoding="utf-8",
    )
    (root / "app" / "sinks.py").write_text(
        # `BATCH_SIZE` is here so the constant search has something to find. A module-level
        # constant is not an atlas node, and two of the three detectors are about constants,
        # so a toolbox that could not reach one could not investigate the candidates it is
        # most often asked about.
        "from app.ports import Sink\n\nBATCH_SIZE = 200\n\n\nclass FileSink:\n"
        "    def write(self, value: str) -> None:\n        print(value)\n",
        encoding="utf-8",
    )
    # A caller and a test, so that `known_callers` and `related_tests` have an answer to
    # give. Every relation kind needs something in the repository to point at or its test
    # proves only that the tool did not raise.
    (root / "app" / "service.py").write_text(
        "from app.sinks import FileSink\n\n\ndef run(value: str) -> None:\n"
        "    FileSink().write(value)\n",
        encoding="utf-8",
    )
    (root / "tests").mkdir()
    (root / "tests" / "__init__.py").write_text("", encoding="utf-8")
    (root / "tests" / "test_sinks.py").write_text(
        "from app.sinks import FileSink\n\n\ndef test_writes() -> None:\n"
        "    FileSink().write('x')\n",
        encoding="utf-8",
    )
    return root


def _investigator(tmp_path: Path) -> AtlasInvestigator:
    from archcompass.analysis.adapters.ast_analyzer import PythonAstRepositoryAnalyzer

    source: AtlasSource = PythonAstRepositoryAnalyzer()
    root = _repository(tmp_path)
    reference = RepositoryRef("repo", root, "branch", "content")
    atlas = DataclassRepositoryAnalyzer(source, _NoScopes()).analyze(reference)
    queries = DeterministicAtlasQueryService(SafeSourceReader())
    return AtlasInvestigator(queries, analysis_atlas(atlas), reference)


def test_a_lookup_takes_the_name_the_candidate_already_carries(tmp_path: Path) -> None:
    """No conversion step. A candidate names `app.ports.Sink`; the tools take that.

    This is the whole of the identifier change. Every tool but the search used to want an
    atlas node id, which only `find_code` handed out — so an investigation could not start
    without spending a turn turning a name it already had into a handle. Measured on a live
    run, a model spent its entire six-turn budget discovering that, having reasonably tried
    the only ids it had been shown.
    """

    investigator = _investigator(tmp_path)

    described = investigator.call("describe_code", {"qualified_name": "app.ports.Sink"})
    related = investigator.call(
        "related_code",
        {"qualified_name": "app.ports.Sink", "relation": "implementations"},
    )

    assert "app.ports.Sink" in described
    assert "app.sinks.FileSink" in related


def test_no_lookup_ever_shows_the_model_an_atlas_id(tmp_path: Path) -> None:
    """The handle is internal, and a result that printed one would teach the old shape."""

    investigator = _investigator(tmp_path)

    answers = [
        investigator.call("search_code", {"name": "Sink"}),
        investigator.call("describe_code", {"qualified_name": "app.ports.Sink"}),
        investigator.call(
            "related_code",
            {"qualified_name": "app.ports.Sink", "relation": "implementations"},
        ),
    ]

    assert not any("node_" in answer for answer in answers), answers


def test_a_name_that_means_two_things_is_refused_with_the_choices(tmp_path: Path) -> None:
    """A package and its own `__init__.py` are the one real collision, and it is visible.

    Never resolved by picking one: a name that quietly resolves to the wrong node is
    recorded for ever as a correct lookup, which is exactly what the identifier rule is for.
    """

    investigator = _investigator(tmp_path)

    answer = investigator.call("describe_code", {"qualified_name": "app"})

    assert "more than one thing" in answer
    assert "kind=" in answer
    # And the disambiguator the refusal named actually works.
    resolved = investigator.call(
        "describe_code", {"qualified_name": "app", "kind": "package"}
    )
    assert "more than one thing" not in resolved


def test_a_module_constant_is_findable_through_the_module_that_defines_it(
    tmp_path: Path,
) -> None:
    """The lookup two of the three detectors depend on, and it used to find nothing.

    Atlas nodes are modules, classes and functions — a module-level constant is none of
    those, so searching node names could not reach one. That is not an edge: a
    `duplicated_knowledge` or `scattered_concept` candidate *is* a constant, and
    so a candidate of either pattern names something the atlas holds no node for. That is
    what `search_code` is for, and why the refusal for an unresolvable name points at it:
    the module is where the constant is defined, and the module *is* a node.
    """

    investigator = _investigator(tmp_path)

    # The name the candidate carries resolves to nothing, and says what to do about it.
    refused = investigator.call("describe_code", {"qualified_name": "app.sinks.BATCH_SIZE"})
    assert "search_code" in refused, refused

    answer = investigator.call("search_code", {"name": "BATCH_SIZE"})

    assert "app.sinks" in answer, answer
    # Still a search and not a catch-all: a name nothing defines finds nothing.
    assert "0 name/path matches" in investigator.call("search_code", {"name": "PAGE_SIZE"})


def test_a_lookup_is_recorded_whether_or_not_it_answered_anything(tmp_path: Path) -> None:
    """A pass that asked and was refused kept its hinge from nothing.

    Without the refused calls the record would show an investigation that never happened
    as one that looked and found nothing to say, and those are opposite facts.
    """

    investigator = _investigator(tmp_path)

    investigator.call("search_code", {"name": "NothingIsCalledThis"})

    assert [item.tool for item in investigator.transcript] == ["search_code"]
    assert investigator.transcript[0].result


def test_an_unknown_tool_comes_back_as_a_sentence_naming_the_ones_that_exist(
    tmp_path: Path,
) -> None:
    investigator = _investigator(tmp_path)

    answer = investigator.call("grep", {"query": "Sink"})

    assert "There is no tool called 'grep'" in answer
    assert "search_code" in answer
    assert len(investigator.transcript) == 1


def test_an_argument_of_the_wrong_type_is_declined_rather_than_raised(
    tmp_path: Path,
) -> None:
    investigator = _investigator(tmp_path)

    answer = investigator.call("describe_code", {"qualified_name": None})

    assert "needs a non-empty string 'qualified_name'" in answer


def test_an_unknown_relationship_names_the_ones_this_repository_answers_to(
    tmp_path: Path,
) -> None:
    investigator = _investigator(tmp_path)

    answer = investigator.call(
        "related_code", {"qualified_name": "app.ports.Sink", "relation": "inherits"}
    )

    assert "There is no relationship called 'inherits'" in answer
    assert "implementations" in answer


def test_a_name_that_does_not_exist_is_answered_rather_than_raised(
    tmp_path: Path,
) -> None:
    """A model guessing at an identifier must not be able to fail a review.

    And the refusal has to say how to recover, not only that it failed. The old one read
    `Unknown atlas node ID: candidate_b5e4…` — accurate, and useless to the only reader it
    has. With an agent, the quality of a refusal is a reasoning budget.
    """

    investigator = _investigator(tmp_path)

    answer = investigator.call("describe_code", {"qualified_name": "app.NothingHere"})

    assert "Nothing in this repository is called 'app.NothingHere'" in answer
    assert "search_code" in answer
    assert len(investigator.transcript) == 1


class _Oversized:
    """A query service whose every answer is far past the per-result ceiling.

    A real repository small enough to build in a test cannot produce one, and a search term
    long enough to look oversized returns "0 matches" — so asserting against a real atlas
    here would pass with the clamp deleted.
    """

    def execute(self, atlas: object, query: object) -> AtlasQueryResult:
        del atlas
        return AtlasQueryResult(
            query=query,  # pyright: ignore[reportArgumentType]
            summary="y" * (MAX_RESULT_CHARACTERS * 3),
        )


def test_a_result_larger_than_the_ceiling_says_that_it_was_cut(tmp_path: Path) -> None:
    """Silence about a truncation reads as "that is all there is", which is worse.

    The transcript keeps the clamped text rather than the whole answer, because the clamped
    text is what the model was actually shown.
    """

    reference = RepositoryRef("repo", tmp_path.resolve(), "branch", "content")
    investigator = AtlasInvestigator(
        _Oversized(),  # pyright: ignore[reportArgumentType]
        analysis_atlas(RepositoryAtlas("atlas", reference)),
        reference,
    )

    clamped = investigator.call("search_code", {"name": "Sink"})

    assert len(clamped) <= MAX_RESULT_CHARACTERS
    assert clamped.endswith(f"cut at {MAX_RESULT_CHARACTERS} characters.")
    assert investigator.transcript[0].result == clamped


def test_the_toolbox_offers_no_way_to_browse_the_whole_repository(
    tmp_path: Path,
) -> None:
    """A hinge is about a named thing. A repository-wide tool is where this becomes an agent."""

    investigator = _investigator(tmp_path)

    assert {spec.name for spec in investigator.tools} == {
        "search_code",
        "describe_code",
        "related_code",
        "read_code",
        "flagged_signals",
    }


def test_a_review_holding_no_structure_says_why_nothing_could_be_looked_up() -> None:
    """A reader has to tell "the code is silent" from "nothing could look"."""

    queries = DeterministicAtlasQueryService(SafeSourceReader())
    reference = RepositoryRef("repo", Path("/tmp/absent").resolve(), "branch", "content")

    offered = AtlasInvestigatorSource(queries).for_review(
        reference, RepositoryAtlas("atlas", reference)
    )

    assert offered.investigator is None
    assert "nothing could be looked up" in offered.withheld


def test_the_toolbox_answers_from_the_atlas_it_was_handed(tmp_path: Path) -> None:
    """A review never persists its atlas, so a toolbox that fetched one could answer
    about a different snapshot than the verdicts were reached against."""

    from archcompass.analysis.adapters.ast_analyzer import PythonAstRepositoryAnalyzer

    root = _repository(tmp_path)
    reference = RepositoryRef("repo", root, "branch", "content")
    analyzer = DataclassRepositoryAnalyzer(PythonAstRepositoryAnalyzer(), _NoScopes())
    first = analyzer.analyze(reference)
    (root / "app" / "later.py").write_text("LATER = 1\n", encoding="utf-8")
    second = analyzer.analyze(reference)
    queries = DeterministicAtlasQueryService(SafeSourceReader())

    offered = AtlasInvestigatorSource(queries).for_review(reference, first)
    assert offered.investigator is not None
    answer = offered.investigator.call("search_code", {"name": "later"})

    assert first.id != second.id
    assert "app.later" not in answer


# Every tool the toolbox offers, each asked something it can actually answer.
#
# The tests above this point were written against the *refusals* — a missing argument, an
# invented id, a relation that does not exist — because those are the paths that shaped the
# error messages. The consequence was that three of the five tools had no test that ever saw
# a real answer, and `related_code`, which `HINGE_CONTRACT` calls the tool that settles most
# hinges, had none for any of its five kinds. The search then shipped unable to find a
# module constant, which is what two of the three detectors are about, and nothing said so.
#
# A tool that returns the wrong thing is worse than one that raises: the model reads it,
# believes it, and puts a confident wrong answer in front of somebody. So each of these
# asserts on what came back rather than that something did.


def test_describing_a_node_answers_with_what_it_is(tmp_path: Path) -> None:
    investigator = _investigator(tmp_path)

    answer = investigator.call("describe_code", {"qualified_name": "app.sinks.FileSink"})

    assert "app.sinks.FileSink" in answer, answer


def test_related_code_answers_every_relation_it_offers(tmp_path: Path) -> None:
    """One assertion per kind, because a kind nothing exercises is a kind nothing checks.

    The three are not variations on each other — they read different edges in different
    directions, and a wiring mistake in one is invisible from the other two.
    """

    investigator = _investigator(tmp_path)

    def related(qualified_name: str, relation: str) -> str:
        return investigator.call(
            "related_code", {"qualified_name": qualified_name, "relation": relation}
        )

    # Which node answers which relation is not arbitrary and is worth writing down, because
    # nothing in the tool's description says it: an import is a fact about a *module*, so
    # dependencies are asked of the module, while a reference is a fact about a *symbol*.
    assert "app.ports" in related("app.sinks", "direct_dependencies")
    assert "app.service" in related("app.sinks", "direct_dependants")
    # What implements the port: one implementation or several, which is a fact the
    # repository has and a person need not be asked.
    assert "app.sinks.FileSink" in related("app.ports.Sink", "implementations")


def test_a_relation_the_toolbox_no_longer_offers_is_refused_by_name(tmp_path: Path) -> None:
    """`known_callers` and `related_tests` are still on the query service, not in the toolbox.

    A `tests` edge is only ever recorded beside a `calls` edge, so neither reaches a
    protocol — and a judgement is almost always about one. Asked 65 times across the stored
    investigations they came back empty 78% of the time, which reads exactly like "nothing
    uses this". The refusal names what is offered instead of answering emptily.
    """

    investigator = _investigator(tmp_path)

    for gone in ("known_callers", "related_tests"):
        answer = investigator.call(
            "related_code", {"qualified_name": "app.sinks.FileSink", "relation": gone}
        )
        assert f"no relationship called {gone!r}" in answer
        assert "direct_dependants" in answer


def test_reading_code_answers_with_the_source_at_that_node(tmp_path: Path) -> None:
    """The one lookup that touches disk, and the only one that can quote the repository."""

    investigator = _investigator(tmp_path)

    answer = investigator.call("read_code", {"qualified_name": "app.sinks.FileSink"})

    assert "class FileSink" in answer, answer
    assert "def write" in answer, answer


def test_flagged_signals_answers_with_what_the_analysis_noticed(tmp_path: Path) -> None:
    """Asserted as a shape rather than a code, because which signals a repository earns is
    the analyser's business and changes when a detector does. What must hold is that the
    tool answers something a model can read instead of raising or returning nothing."""

    investigator = _investigator(tmp_path)

    answer = investigator.call("flagged_signals", {})

    assert answer.strip(), "the signals lookup answered with nothing at all"
    assert [item.tool for item in investigator.transcript] == ["flagged_signals"]


def test_every_tool_the_toolbox_advertises_is_one_it_can_answer(tmp_path: Path) -> None:
    """The guard that would have caught a tool being advertised and never wired up.

    `tools()` is what the model is shown. Anything in it that `call` does not know
    is a tool the model will choose, be refused by, and have to recover from — and nothing
    else in this file would notice, because every other test names its tools by hand.
    """

    investigator = _investigator(tmp_path)
    advertised = {spec.name for spec in investigator.tools}

    assert advertised == {
        "search_code",
        "describe_code",
        "related_code",
        "read_code",
        "flagged_signals",
    }
    for name in sorted(advertised):
        assert "There is no tool called" not in investigator.call(name, {})
