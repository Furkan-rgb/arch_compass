"""A candidate whose verdict cannot be reached from the repository, kept as a fixture.

`held` is a first-class outcome of this product: a judgement that stops and asks is worth
more than a confident wrong one. Giving the judge tools puts that outcome at risk in a
specific way — a missing human fact plus a repository it can read could become an
unjustified confident verdict — so there has to be a case in the suite where asking is the
only honest answer, and where what makes it so is visible rather than asserted.

This is that case. `SettlementFeed` is documented as a published contract with one
implementation and no test double. Whether an external consumer has actually written against
it is the deciding fact, it is nowhere in the repository, and no lookup can settle it.

The verdict itself is not asserted here. A model's answer is not a unit test's business, and
a test that pinned one would fail on a model change rather than on a defect. What is pinned
is the shape: the candidate exists, it carries the two facts that make `held` right, and it
carries nothing that would settle the question.
"""

from __future__ import annotations

from pathlib import Path

from archcompass.analysis.adapters.ast_analyzer import PythonAstRepositoryAnalyzer
from archcompass.analysis.atlas import FindingPattern
from archcompass.analysis.detectors import detect_finding_candidates

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "held_only" / "repository"


def test_the_fixture_offers_exactly_one_candidate_nothing_in_it_can_settle() -> None:
    found = detect_finding_candidates(PythonAstRepositoryAnalyzer().analyze(FIXTURE))

    assert len(found) == 1, [item.summary for item in found]
    candidate = found[0]
    assert candidate.pattern is FindingPattern.SOLE_IMPLEMENTATION
    assert candidate.participants[0].qualified_name == "app.ports.SettlementFeed"

    measured = {item.name: item.value for item in candidate.measurements}
    # One implementation, and nothing standing in for it in a test — so the corpus's
    # testing-boundary exception plainly does not apply, and the only exception left is the
    # published contract, which is the fact nobody here can check.
    assert measured["implementations"] == 1
    assert measured["test_doubles_offering_its_methods"] == 0
    # And it is used, so "nothing depends on it" is not available as an easy answer either.
    assert measured["dependants_of_abstraction"] >= 1
