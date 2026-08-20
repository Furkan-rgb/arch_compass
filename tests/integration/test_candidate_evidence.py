"""What a detected shape carries with it when it is handed to a judge.

A detector reports structure; this is the conversion that turns that structure into the
thing a model is actually shown. Everything asserted here was previously computed and then
discarded on the way through — the edge between participants, the nature that qualifies a
measurement, the comment that says what a constant means — so these tests are less about
new behaviour than about the conversion no longer being lossy.

The excerpt rules are here for the opposite reason. A ceiling that is too high does not
show more, it shows an arbitrary prefix of a long span and gives no sign that it did.
"""

from __future__ import annotations

from pathlib import Path
from textwrap import dedent

import pytest

from archcompass.analysis.adapters.ast_analyzer import PythonAstRepositoryAnalyzer
from archcompass.analysis.analyzer import (
    MAX_EXCERPT_LINES,
    DataclassCandidateDetector,
    DataclassRepositoryAnalyzer,
)
from archcompass.domain import Candidate, MetricNature, RepositoryRef
from archcompass.reasoning.adapters.langchain import candidate_text


class _NoNarrowing:
    """A scope repository for a repository nobody has narrowed."""

    def get(self, root: str) -> tuple[str, ...] | None:
        return None

    def set(self, root: str, excluded: tuple[str, ...]) -> None:  # pragma: no cover
        raise NotImplementedError


def _candidates(root: Path) -> tuple[Candidate, ...]:
    analyzer = DataclassRepositoryAnalyzer(PythonAstRepositoryAnalyzer(), _NoNarrowing())
    atlas = analyzer.analyze(
        RepositoryRef(id="repo", path=root, branch_id="branch", content_id="content")
    )
    return DataclassCandidateDetector().detect(atlas)


def _of_pattern(candidates: tuple[Candidate, ...], pattern: str) -> Candidate:
    found = [item for item in candidates if item.pattern == pattern]
    if not found:
        pytest.fail(f"no {pattern} candidate was detected")
    return found[0]


@pytest.fixture
def repository(tmp_path: Path) -> Path:
    package = tmp_path / "shop"
    package.mkdir()
    (package / "__init__.py").write_text("", encoding="utf-8")
    (package / "port.py").write_text(
        dedent(
            """
            from typing import Protocol


            class Ledger(Protocol):
                def record(self, amount: int) -> None: ...
            """
        ).lstrip(),
        encoding="utf-8",
    )
    # An implementation far longer than the excerpt ceiling, so the excerpt has to stop
    # somewhere and has to say that it stopped.
    body = "\n".join(f"        self._seen = {index}" for index in range(120))
    (package / "adapter.py").write_text(
        dedent(
            """
            from shop.port import Ledger


            class SqlLedger(Ledger):
                def record(self, amount: int) -> None:
            """
        ).lstrip()
        + body
        + "\n",
        encoding="utf-8",
    )
    # The same constant in two modules, each with the sentence that says what it means
    # written directly above it rather than beside it.
    for name in ("billing.py", "retries.py"):
        (package / name).write_text(
            dedent(
                """
                import os

                # The vendor's published guidance is five attempts before giving up.
                # Both callers of the payment API have to agree on this number.
                RETRY_LIMIT = 5
                """
            ).lstrip(),
            encoding="utf-8",
        )
    return tmp_path


def test_an_excerpt_stops_at_the_ceiling_and_says_that_it_did(repository: Path) -> None:
    candidate = _of_pattern(_candidates(repository), "sole_implementation")
    implementation = candidate.evidence[1]

    assert implementation.excerpt is not None
    assert len(implementation.excerpt.splitlines()) == MAX_EXCERPT_LINES
    assert implementation.note is not None
    # The note has to make the fragment legible as a fragment: a reader shown sixty lines
    # of a hundred-and-twenty-line span and no caption reads them as the whole thing.
    assert "opening fragment" in implementation.note
    assert implementation.location is not None
    assert (
        implementation.location.end_line - implementation.location.start_line + 1
        == MAX_EXCERPT_LINES
    )


def test_a_constant_carries_the_comment_that_explains_it(repository: Path) -> None:
    candidate = _of_pattern(_candidates(repository), "duplicated_knowledge")

    for evidence in candidate.evidence:
        assert evidence.excerpt is not None
        # The decisive fact about a duplicated constant is written above the assignment,
        # and a judge shown the assignment alone was deciding with it out of frame.
        assert "vendor's published guidance" in evidence.excerpt
        assert "RETRY_LIMIT = 5" in evidence.excerpt
        assert evidence.note is not None and "Widened upward" in evidence.note


def test_a_candidate_carries_the_edge_between_its_participants(repository: Path) -> None:
    candidate = _of_pattern(_candidates(repository), "sole_implementation")

    assert candidate.relationships, "the implements edge was computed and then discarded"
    edge = candidate.relationships[0]
    # `inherits` and not `implements`: this fixture subclasses the Protocol explicitly, and
    # which of the two established the link is exactly the distinction the edge is carried
    # for — a structural match and a declared subclass are not the same evidence.
    assert edge.kind == "inherits"
    # Qualified names rather than atlas ids: an id means nothing to the reader or the model
    # that the edge is being carried for.
    assert edge.source.endswith("SqlLedger")
    assert edge.target.endswith("Ledger")
    assert edge.resolved_by in {"parse", "types"}


def test_a_measurement_keeps_the_nature_that_qualifies_it(repository: Path) -> None:
    candidate = _of_pattern(_candidates(repository), "sole_implementation")

    dependants = candidate.measured("dependants_of_abstraction")
    assert dependants is not None
    # Zero here reads the same for an abstraction nothing uses and for one reached only
    # through wiring the parse cannot see. The tag is what keeps those two apart.
    assert dependants.nature is MetricNature.STRUCTURAL_PROXY
    assert dependants.limitations
    assert candidate.measured("implementations") is not None
    assert candidate.measured("implementations").nature is MetricNature.MEASUREMENT


def test_the_judge_reads_code_as_lines_rather_than_escapes(repository: Path) -> None:
    candidate = _of_pattern(_candidates(repository), "duplicated_knowledge")
    rendered = candidate_text(candidate)

    # The dataclass repr used to do this, and it escapes every newline: the code arrived as
    # one very long line punctuated by literal backslash-n.
    assert "\\n" not in rendered
    assert "RETRY_LIMIT = 5" in rendered
    assert "modules_stating_it" in rendered
    assert "[objective_measurement]" in rendered
