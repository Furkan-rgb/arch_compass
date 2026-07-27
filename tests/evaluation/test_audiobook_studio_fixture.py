"""The example modelled on the project ArchCompass was started because of.

`make eval-local` scores a live run against `expected.yaml`. That score only means
something if the fixture still presents what the key describes, so these run offline and
fail when the two drift apart.

This is the only fixture that exercises all three detectors, and it is deliberately the
hardest. Under each of the two repetition detectors one instance is a real finding and one
is not, so a run cannot score by learning that duplication is bad, or that a vendor named
outside its package is bad. Only the case separates them.

Two properties are defended here that the key cannot express:

- The case must never state the finding. Working out which shapes are wrong is the
  advisor's job; a case that says it first grades the model on reading rather than on
  judgement.
- The adapters must keep the shapes that used to be invisible — structural conformance,
  a concrete return where the port declares the abstract type, a widened signature, and a
  marker Protocol with no methods. Every one of those once caused this repository's
  boundaries to be missed silently, and a review that finds nothing reads as approval.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest
import yaml

from archcompass.adapters.analysis.ast_analyzer import PythonAstRepositoryAnalyzer
from archcompass.domain.atlas import FindingPattern
from archcompass.domain.case import ArchitectureCase
from archcompass.domain.finding_detectors import detect_finding_candidates

FIXTURE = Path("eval/cases/audiobook-studio").resolve()

pytestmark = pytest.mark.evaluation


def _key() -> dict[str, bool]:
    document = yaml.safe_load((FIXTURE / "expected.yaml").read_text(encoding="utf-8"))
    return {item["abstraction"]: item["material"] for item in document["boundaries"]}


def _case() -> ArchitectureCase:
    return ArchitectureCase.model_validate(
        yaml.safe_load((FIXTURE / "case.yaml").read_text(encoding="utf-8"))
    )


def _candidates():
    return detect_finding_candidates(
        PythonAstRepositoryAnalyzer().analyze(FIXTURE / "repository")
    )


def _source(relative: str) -> str:
    return (FIXTURE / "repository" / relative).read_text(encoding="utf-8")


def test_the_case_is_a_case_this_workspace_would_accept() -> None:
    assert _case().title


def test_the_detector_finds_exactly_the_boundaries_the_key_scores() -> None:
    """An unscored candidate would silently shrink the denominator of every run."""

    detected = sorted(item.participants[0].qualified_name for item in _candidates())

    assert detected == sorted(_key())


def test_all_three_detectors_are_exercised() -> None:
    """The fixture exists to cover both directions of the catalogue at once."""

    assert {item.pattern for item in _candidates()} == {
        FindingPattern.SOLE_IMPLEMENTATION,
        FindingPattern.DUPLICATED_KNOWLEDGE,
        FindingPattern.SCATTERED_CONCEPT,
    }


def test_each_repetition_detector_carries_both_verdicts() -> None:
    """Otherwise a run could score by condemning a shape rather than reading the case."""

    key = _key()
    by_pattern: dict[FindingPattern, list[bool]] = {}
    for candidate in _candidates():
        name = candidate.participants[0].qualified_name
        by_pattern.setdefault(candidate.pattern, []).append(key[name])

    for pattern in (
        FindingPattern.DUPLICATED_KNOWLEDGE,
        FindingPattern.SCATTERED_CONCEPT,
        FindingPattern.SOLE_IMPLEMENTATION,
    ):
        verdicts = by_pattern[pattern]
        assert True in verdicts and False in verdicts, (pattern, verdicts)


def test_the_adapters_keep_the_shapes_that_used_to_be_invisible() -> None:
    """Each of these once made a real repository's boundaries vanish from the sweep."""

    port = _source("synthesis/base.py")
    adapter = _source("synthesis/qwen.py")

    # A marker Protocol with no operations at all.
    assert "class Voice(Protocol):" in port
    # Operations carrying no argument to compare, which once made a port unmatchable.
    assert "def check_available(self) -> None:" in port
    assert "def close(self) -> None:" in port
    # Structural conformance: the adapter does not inherit the port.
    assert "class QwenSynthesis:" in adapter
    # A concrete return where the port declares the abstract type, and a widened signature.
    assert "-> QwenVoice | QwenBuiltinVoice:" in adapter
    assert "ref_text: str | None = None" in adapter


def test_no_adapter_inherits_the_protocol_it_satisfies() -> None:
    """Inheritance would make the fixture pass through the easy path and prove nothing."""

    for relative in ("synthesis/qwen.py", "preparation/ollama.py"):
        tree = ast.parse(_source(relative))
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                assert not node.bases, f"{relative}:{node.name} must conform structurally"


def test_the_case_never_states_the_finding() -> None:
    """The example must be judged, not read."""

    case = _case()
    text = " ".join(
        [
            case.problem_statement,
            case.desired_outcome,
            *case.technical_constraints,
            *case.organisational_constraints,
            *case.quality_attributes,
            *case.non_goals,
            *case.expected_future_changes,
            *[item.text for item in case.confirmed_facts],
            *[item.text for item in case.assumptions],
        ]
    ).casefold()

    for word in (
        "duplicat",
        "boundary",
        "abstraction",
        "indirection",
        "protocol",
        "registry",
        "leak",
        "remove",
        "refactor",
        "sample_rate",
        "qwen",
        "ollama",
    ):
        assert word not in text, f"the case gives the finding away with {word!r}"
