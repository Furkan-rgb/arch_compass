"""The standing example repository, checked without a model.

`make demo` runs the review path against this repository, and the workspace offers it as
the first thing a visitor can click. Both rest on it still presenting what it was written
to present, so these run offline and fail when it stops.

The fixture's whole point is that the detector cannot separate the six boundaries — every
one is an abstraction with a single implementation. Only circumstances can, and this
example ships none: the questions the run comes back with are what write them down.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from archcompass.adapters.analysis.ast_analyzer import PythonAstRepositoryAnalyzer
from archcompass.domain.atlas import FindingPattern
from archcompass.domain.finding_detectors import detect_finding_candidates

FIXTURE = Path("eval/cases/boundary-review").resolve()

pytestmark = pytest.mark.evaluation


def test_every_detected_boundary_is_the_same_shape() -> None:
    """Nothing here may be decidable by counting, or the case is never read at all."""

    atlas = PythonAstRepositoryAnalyzer().analyze(FIXTURE / "repository")
    candidates = detect_finding_candidates(atlas)

    assert len(candidates) == 6
    assert {candidate.pattern for candidate in candidates} == {
        FindingPattern.SOLE_IMPLEMENTATION
    }
    for candidate in candidates:
        measured = {item.name: item.value for item in candidate.measurements}
        assert measured["implementations"] == 1


def test_the_fixture_repository_still_parses() -> None:
    """A fixture that stopped being valid Python would produce an empty atlas quietly."""

    atlas = PythonAstRepositoryAnalyzer().analyze(FIXTURE / "repository")

    assert len(atlas.nodes) > 40
    assert len(atlas.edges) > 80
