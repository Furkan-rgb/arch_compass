"""The example repository modelled on the project ArchCompass was started because of.

The only one that exercises all three detectors, and deliberately the hardest. Under each
of the two repetition detectors one instance is a real finding and one is not, so nothing
here can be settled by learning that duplication is bad, or that a vendor named outside its
package is bad — only by what a reader says about their circumstances.

The property defended below that no listing can express: the adapters keep the shapes that
used to be invisible — structural conformance, a concrete return where the port declares
the abstract type, a widened signature, and a marker Protocol with no methods. Every one of
those once caused this repository's boundaries to be missed silently, and a review that
finds nothing reads as approval.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from archcompass.adapters.analysis.ast_analyzer import PythonAstRepositoryAnalyzer
from archcompass.boundary.atlas import FindingPattern
from archcompass.boundary.finding_detectors import detect_finding_candidates

FIXTURE = Path("eval/cases/audiobook-studio").resolve()

pytestmark = pytest.mark.evaluation


def _candidates():
    return detect_finding_candidates(
        PythonAstRepositoryAnalyzer().analyze(FIXTURE / "repository")
    )


def _source(relative: str) -> str:
    return (FIXTURE / "repository" / relative).read_text(encoding="utf-8")


def test_all_three_detectors_are_exercised() -> None:
    """The example exists to cover both directions of the catalogue at once."""

    assert {item.pattern for item in _candidates()} == {
        FindingPattern.SOLE_IMPLEMENTATION,
        FindingPattern.DUPLICATED_KNOWLEDGE,
        FindingPattern.SCATTERED_CONCEPT,
    }


def test_each_repetition_detector_carries_more_than_one_instance() -> None:
    """One instance per detector could be read off its shape; two cannot.

    The pairs are the point of this example: within a pattern the candidates look alike,
    and what separates them is only what the review is told about the project.
    """

    by_pattern: dict[FindingPattern, list[str]] = {}
    for candidate in _candidates():
        name = candidate.participants[0].qualified_name
        by_pattern.setdefault(candidate.pattern, []).append(name)

    for pattern in (
        FindingPattern.DUPLICATED_KNOWLEDGE,
        FindingPattern.SCATTERED_CONCEPT,
        FindingPattern.SOLE_IMPLEMENTATION,
    ):
        assert len(by_pattern[pattern]) >= 2, (pattern, by_pattern[pattern])


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
