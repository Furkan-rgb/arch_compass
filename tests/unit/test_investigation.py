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
from archcompass.domain import RepositoryAtlas, RepositoryRef
from archcompass.ports.atlas import RepositoryAnalyzer as AnalyzerRecordSource


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
        "from app.ports import Sink\n\n\nclass FileSink:\n"
        "    def write(self, value: str) -> None:\n        print(value)\n",
        encoding="utf-8",
    )
    return root


def _investigator(tmp_path: Path) -> AtlasInvestigator:
    from archcompass.analysis.adapters.ast_analyzer import PythonAstRepositoryAnalyzer

    source: AnalyzerRecordSource = PythonAstRepositoryAnalyzer()
    root = _repository(tmp_path)
    reference = RepositoryRef("repo", root, "branch", "content")
    atlas = DataclassRepositoryAnalyzer(source, _NoScopes()).analyze(reference)
    queries = DeterministicAtlasQueryService(SafeSourceReader())
    return AtlasInvestigator(queries, analysis_atlas(atlas), reference)


def test_finding_code_by_name_is_how_a_node_id_enters_the_conversation(
    tmp_path: Path,
) -> None:
    """Every other tool needs an id, and a candidate only ever carries qualified names.

    If this stopped matching, nothing else in the toolbox would be reachable — the model
    would be holding names the atlas does not answer to.
    """

    investigator = _investigator(tmp_path)

    answer = investigator.call("find_code", {"name": "Sink"})

    assert "app.ports.Sink" in answer
    assert any(line.strip().startswith("node_") for line in answer.splitlines())


def test_a_lookup_is_recorded_whether_or_not_it_answered_anything(tmp_path: Path) -> None:
    """A pass that asked and was refused kept its hinge from nothing.

    Without the refused calls the record would show an investigation that never happened
    as one that looked and found nothing to say, and those are opposite facts.
    """

    investigator = _investigator(tmp_path)

    investigator.call("find_code", {"name": "NothingIsCalledThis"})

    assert [item.tool for item in investigator.transcript] == ["find_code"]
    assert investigator.transcript[0].result


def test_an_unknown_tool_comes_back_as_a_sentence_naming_the_ones_that_exist(
    tmp_path: Path,
) -> None:
    investigator = _investigator(tmp_path)

    answer = investigator.call("grep", {"query": "Sink"})

    assert "There is no tool called 'grep'" in answer
    assert "find_code" in answer
    assert len(investigator.transcript) == 1


def test_an_argument_of_the_wrong_type_is_declined_rather_than_raised(
    tmp_path: Path,
) -> None:
    investigator = _investigator(tmp_path)

    answer = investigator.call("describe_code", {"node_id": None})

    assert "needs a non-empty string 'node_id'" in answer


def test_an_unknown_relationship_names_the_ones_this_repository_answers_to(
    tmp_path: Path,
) -> None:
    investigator = _investigator(tmp_path)

    answer = investigator.call("related_code", {"node_id": "x", "kind": "inherits"})

    assert "There is no relationship called 'inherits'" in answer
    assert "implementations" in answer


def test_a_node_id_that_does_not_exist_is_answered_rather_than_raised(
    tmp_path: Path,
) -> None:
    """A model guessing at an identifier must not be able to fail a review."""

    investigator = _investigator(tmp_path)

    answer = investigator.call("describe_code", {"node_id": "node_invented"})

    assert answer
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

    clamped = investigator.call("find_code", {"name": "Sink"})

    assert len(clamped) <= MAX_RESULT_CHARACTERS
    assert clamped.endswith(f"cut at {MAX_RESULT_CHARACTERS} characters.")
    assert investigator.transcript[0].result == clamped


def test_the_toolbox_offers_no_way_to_browse_the_whole_repository(
    tmp_path: Path,
) -> None:
    """A hinge is about a named thing. A repository-wide tool is where this becomes an agent."""

    investigator = _investigator(tmp_path)

    assert {spec.name for spec in investigator.tools} == {
        "find_code",
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
    answer = offered.investigator.call("find_code", {"name": "later"})

    assert first.id != second.id
    assert "app.later" not in answer
