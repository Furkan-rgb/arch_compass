"""The brownfield example repository, checked without a model.

`make eval-local` scores a live run against `expected.yaml`. That score only means
something if the fixture still presents what the key describes, so these run offline and
fail when the two drift apart.

What this fixture measures is not what `boundary-review` measures. There, half the
boundaries sit in front of variation the case rules out. Here *every* boundary sits in
front of variation the case says is genuinely coming, so a run that reads "a second vendor
is contracted" and stops there clears all six. The discrimination is placement: three seams
are at the edge the change arrives at, and three are vendor-shaped holes cut into modules
with no other reason to know a vendor exists.

Two properties are defended here that the key cannot express:

- The case must never state the finding. The whole point of the example is that ArchCompass
  works out where the boundaries are wrong; a case that says it first grades the model on
  reading rather than on judgement.
- The repetition must really be in the repository. The same voice list is written into four
  modules and one copy has drifted. The fixture carried that for a long time before any
  detector could see it — *repetition without ownership*, master plan §8A.3 — and now that
  one can, it is scored rather than merely present.
"""

from __future__ import annotations

import ast
from collections import defaultdict
from pathlib import Path

import pytest
import yaml

from archcompass.adapters.analysis.ast_analyzer import PythonAstRepositoryAnalyzer
from archcompass.domain.atlas import FindingPattern
from archcompass.domain.case import ArchitectureCase
from archcompass.domain.finding_detectors import detect_finding_candidates

FIXTURE = Path("eval/cases/speech-vendor").resolve()

pytestmark = pytest.mark.evaluation


def _key() -> dict[str, bool]:
    document = yaml.safe_load((FIXTURE / "expected.yaml").read_text(encoding="utf-8"))
    return {item["abstraction"]: item["material"] for item in document["boundaries"]}


def _case() -> ArchitectureCase:
    return ArchitectureCase.model_validate(
        yaml.safe_load((FIXTURE / "case.yaml").read_text(encoding="utf-8"))
    )


def _case_text() -> str:
    case = _case()
    return " ".join(
        [
            case.title,
            case.problem_statement,
            case.desired_outcome,
            *case.actors_and_workflows,
            *case.functional_requirements,
            *case.quality_attributes,
            *case.technical_constraints,
            *case.organisational_constraints,
            *case.expected_future_changes,
            *case.non_goals,
            *(statement.text for statement in case.confirmed_facts),
        ]
    ).casefold()


def _detected() -> list[str]:
    atlas = PythonAstRepositoryAnalyzer().analyze(FIXTURE / "repository")
    return [
        candidate.participants[0].qualified_name
        for candidate in detect_finding_candidates(atlas)
    ]


def test_the_detector_finds_exactly_the_boundaries_the_key_scores() -> None:
    """An unscored candidate would silently shrink the denominator of every run."""

    assert sorted(_detected()) == sorted(_key())


def test_no_boundary_can_be_scored_by_its_shape_alone() -> None:
    """Within a pattern the candidates must be indistinguishable, so only the case decides.

    This used to assert the whole fixture was one shape. It is not any more, deliberately:
    the repetition it always carried is detected and scored now, so the fixture exercises
    both directions of the catalogue. The guarantee it was protecting is narrower than the
    old assertion and is what actually matters — a run must not be able to tell two
    *sole-implementation* boundaries apart by counting, because then it could score three
    material and three not without ever reading the case.
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
    # And both directions really are present, or the fixture has quietly stopped testing
    # the discrimination its key is written for.
    assert {candidate.pattern for candidate in candidates} == {
        FindingPattern.SOLE_IMPLEMENTATION,
        FindingPattern.DUPLICATED_KNOWLEDGE,
        FindingPattern.SCATTERED_CONCEPT,
    }


def test_the_key_is_a_real_discrimination_and_not_a_lean() -> None:
    """All-material or all-immaterial would be passed by a stage that never reads the case."""

    verdicts = list(_key().values())

    assert verdicts.count(True) >= 2
    assert verdicts.count(False) >= 2


def test_the_case_states_the_grounds_the_key_relies_on() -> None:
    """Each expected verdict must be reachable from case text, not from outside knowledge."""

    text = _case_text()

    # Grounds for the three boundaries drawn where the change arrives.
    assert "under contract" in text
    assert "web player" in text
    assert "database driver" in text
    # Grounds for the three that answer a question belonging to the vendor.
    assert "only answerable by asking that vendor at runtime" in text
    assert "not known until its account is provisioned" in text
    assert "no other reason to change" in text


def test_the_case_never_states_the_finding() -> None:
    """The advisor has to find the leak; the case must not hand it over.

    This is the property the example exists for. Every word below either names the defect,
    names the fix, or names the code the defect is in — and any of them turns the run into
    a reading exercise whose score says nothing about architectural judgement.
    """

    text = _case_text()

    for word in (
        # The defect, and the shape of the fix.
        "duplicat",
        "scatter",
        "leak",
        "copy",
        "copies",
        "owner",
        "discovery",
        "single source",
        # The vendor, and the seams the verdicts are about. Naming any of them points at
        # the answer, and the case has no reason to: a team describes what it wants, not
        # the classes it suspects.
        "qwen",
        "provider",
        "voicelistsource",
        "voicevalidator",
        "voiceresolver",
        "catalogue",
        "preflight",
    ):
        assert word not in text, f"the case gives the finding away with {word!r}"


def test_the_repetition_the_next_detector_will_want_is_really_there() -> None:
    """The same knowledge in several modules, with one copy already wrong.

    Nothing scores this today. It is the other half of the catalogue (§8A.3), and a
    brownfield fixture that did not actually contain the leak would be ready for nothing.
    """

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
