"""The standing example repository, checked without a model.

`make demo` scores a live run against `expected.yaml`. That score only means something if
the fixture still presents what the key describes, so these run offline and fail when the
two drift apart.

The fixture's whole point is that the detector cannot separate the six boundaries — every
one is an abstraction with a single implementation — while the case can. Assertions here
defend that symmetry, because a fixture where the shapes differ would let a run score well
on the shapes rather than on the reasoning.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from archcompass.adapters.analysis.ast_analyzer import PythonAstRepositoryAnalyzer
from archcompass.domain.atlas import FindingPattern
from archcompass.domain.case import ArchitectureCase
from archcompass.domain.finding_detectors import detect_finding_candidates

FIXTURE = Path("eval/cases/boundary-review").resolve()

pytestmark = pytest.mark.evaluation


def _key() -> dict[str, bool]:
    document = yaml.safe_load((FIXTURE / "expected.yaml").read_text(encoding="utf-8"))
    return {item["abstraction"]: item["material"] for item in document["boundaries"]}


def _detected() -> list[str]:
    atlas = PythonAstRepositoryAnalyzer().analyze(FIXTURE / "repository")
    return [
        candidate.participants[0].qualified_name
        for candidate in detect_finding_candidates(atlas)
    ]


def test_the_detector_finds_exactly_the_boundaries_the_key_scores() -> None:
    """An unscored candidate would silently shrink the denominator of every run."""

    assert sorted(_detected()) == sorted(_key())


def test_every_detected_boundary_is_the_same_shape() -> None:
    """The fixture must not let a run score by telling the shapes apart, only the case."""

    atlas = PythonAstRepositoryAnalyzer().analyze(FIXTURE / "repository")
    candidates = detect_finding_candidates(atlas)

    assert {candidate.pattern for candidate in candidates} == {
        FindingPattern.SOLE_IMPLEMENTATION
    }
    for candidate in candidates:
        measured = {item.name: item.value for item in candidate.measurements}
        assert measured["implementations"] == 1


def test_the_key_is_a_real_discrimination_and_not_a_lean() -> None:
    """All-material or all-immaterial would be passed by a stage that never reads the case."""

    verdicts = list(_key().values())

    assert verdicts.count(True) >= 2
    assert verdicts.count(False) >= 2


def test_the_case_states_the_grounds_the_key_relies_on() -> None:
    """Each expected verdict must be reachable from case text, not from outside knowledge."""

    case = ArchitectureCase.model_validate(
        yaml.safe_load((FIXTURE / "case.yaml").read_text(encoding="utf-8"))
    )
    text = " ".join(
        [
            case.problem_statement,
            *case.technical_constraints,
            *case.expected_future_changes,
            *case.non_goals,
            *(statement.text for statement in case.confirmed_facts),
        ]
    ).casefold()

    # Grounds for the three justified boundaries.
    assert "sms" in text
    assert "postgres" in text
    assert "substitutes its own clock" in text
    # Grounds for the three that are not.
    assert "downstream reporting system" in text
    assert "uuid4" in text
    assert "configuration format other than" in text


def test_the_fixture_repository_still_parses() -> None:
    """A fixture that stopped being valid Python would produce an empty atlas quietly."""

    atlas = PythonAstRepositoryAnalyzer().analyze(FIXTURE / "repository")

    assert len(atlas.nodes) > 40
    assert len(atlas.edges) > 80
