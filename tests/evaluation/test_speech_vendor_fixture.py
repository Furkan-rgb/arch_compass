"""The brownfield example repository, checked without a model.

What this repository presents is not what `boundary-review` presents. There, what a reader
settles is whether a boundary absorbs any variation at all. Here every seam stands in front
of variation a second vendor would bring, and what separates them is placement: three are
at the edge the change arrives at, and three are vendor-shaped holes cut into modules with
no other reason to know a vendor exists. None of that is decidable by counting, which is
the property these tests defend.

The repetition is the other half: the same voice list is written into four modules and one
copy has drifted (master plan §8A.3). A brownfield example that did not actually contain
the leak would demonstrate nothing.
"""

from __future__ import annotations

import ast
from collections import defaultdict
from pathlib import Path

import pytest

from archcompass.adapters.analysis.ast_analyzer import PythonAstRepositoryAnalyzer
from archcompass.boundary.atlas import FindingPattern
from archcompass.boundary.finding_detectors import detect_finding_candidates

FIXTURE = Path("eval/cases/speech-vendor").resolve()

pytestmark = pytest.mark.evaluation


def test_no_boundary_can_be_told_from_another_by_its_shape_alone() -> None:
    """Within a pattern the candidates must be indistinguishable, so only the case decides.

    Narrower than "the whole fixture is one shape", deliberately: the repetition it always
    carried is detected too, so it exercises both directions of the catalogue. What matters
    is that two *sole-implementation* boundaries cannot be separated by counting, because
    then a run could split them three and three without reading anything a reader said.
    """

    atlas = PythonAstRepositoryAnalyzer().analyze(FIXTURE / "repository")
    candidates = detect_finding_candidates(atlas)
    boundaries = [
        candidate
        for candidate in candidates
        if candidate.pattern is FindingPattern.SOLE_IMPLEMENTATION
    ]

    assert len(boundaries) == 6
    for candidate in boundaries:
        measured = {item.name: item.value for item in candidate.measurements}
        assert measured["implementations"] == 1
    # And both directions really are present, or the example has quietly stopped showing
    # the discrimination it was written for.
    assert {candidate.pattern for candidate in candidates} == {
        FindingPattern.SOLE_IMPLEMENTATION,
        FindingPattern.DUPLICATED_KNOWLEDGE,
        FindingPattern.SCATTERED_CONCEPT,
    }


def test_the_repetition_the_detector_reports_is_really_there() -> None:
    """The same knowledge in several modules, with one copy already wrong."""

    definitions: dict[str, dict[str, list[str]]] = defaultdict(dict)
    for path in sorted((FIXTURE / "repository").rglob("*.py")):
        module = path.relative_to(FIXTURE / "repository").as_posix()
        for statement in ast.parse(path.read_text(encoding="utf-8")).body:
            if not isinstance(statement, ast.Assign):
                continue
            for target in statement.targets:
                if isinstance(target, ast.Name) and target.id.isupper():
                    definitions[target.id][module] = ast.unparse(statement.value)

    voices = definitions["BUILT_IN_VOICES"]
    assert len(voices) >= 3, "the voice list must be written out in several modules"
    assert len(set(voices.values())) > 1, "at least one copy must have drifted out of step"


def test_the_fixture_repository_still_parses() -> None:
    """A fixture that stopped being valid Python would produce an empty atlas quietly."""

    atlas = PythonAstRepositoryAnalyzer().analyze(FIXTURE / "repository")

    assert len(atlas.nodes) > 60
    assert len(atlas.edges) > 120
