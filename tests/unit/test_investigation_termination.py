"""Every investigation that runs records why it stopped. `None` means only "not recorded".

The distinction this file guards is the one a judge needs and a reader needs: "the repository
is silent" and "we stopped asking" are opposite facts about a hinge, and before terminations
were recorded they were stored identically — a run that exhausted its six model calls left
the same empty note as one that had finished looking.

`None` survives only for records written before the field existed. It must never come to mean
a natural end, and no path that actually runs may produce it.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from archcompass.domain import (
    CandidateId,
    InvestigationLookup,
    RecordedInvestigation,
    Termination,
)

SOURCE_ROOT = Path(__file__).resolve().parents[2] / "src" / "archcompass"


def _conclude_calls() -> list[tuple[Path, ast.Call]]:
    """Every `conclude(...)` in the source, found by AST rather than by grep.

    The record's termination can only be set through this one method, so a sweep of its call
    sites is a sweep of every way a live investigation ends.
    """

    found: list[tuple[Path, ast.Call]] = []
    for path in sorted(SOURCE_ROOT.rglob("*.py")):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr == "conclude"
            ):
                found.append((path, node))
    return found


def test_every_way_an_investigation_ends_names_a_termination() -> None:
    """A future refactor cannot start writing records with no reason for stopping.

    Asserted over the source rather than by running each path, because the paths that matter
    are the ones that are hard to reach on purpose — a provider that stops answering, a size
    ceiling, an exhausted turn budget. A test that only covered the reachable ones would pass
    while the interesting exits went back to being indistinguishable.
    """

    calls = _conclude_calls()
    assert calls, "no `conclude` call was found; this guard now sweeps nothing"

    terminations = {member.name for member in Termination}
    for path, call in calls:
        where = f"{path.relative_to(SOURCE_ROOT)}:{call.lineno}"
        assert len(call.args) >= 2, f"{where} concludes without saying why it stopped"
        reason = call.args[1]
        # Either a `Termination.X` literal, or a name the enclosing function computed — both
        # are typed, and the type is what forbids `None`. What is refused is a literal `None`
        # or an empty string, which is what the field held before it was a state.
        if isinstance(reason, ast.Constant):
            raise AssertionError(f"{where} concludes with the constant {reason.value!r}")
        if isinstance(reason, ast.Attribute):
            assert reason.attr in terminations, f"{where} names no known termination"


def test_a_run_that_looked_at_nothing_still_says_why_it_stopped() -> None:
    """Zero useful lookups is not zero information. The reason is the information."""

    record = RecordedInvestigation(
        candidate_id=CandidateId("candidate_1"),
        lookups=(InvestigationLookup("describe_code", (("qualified_name", "x"),), "no"),),
        termination=Termination.MODEL_CALL_LIMIT,
    )

    assert record.termination is Termination.MODEL_CALL_LIMIT


def test_a_withheld_investigation_cannot_also_have_terminated() -> None:
    """Two opposite accounts of one investigation: it never began, and here is how it ended."""

    with pytest.raises(ValueError, match="never ran"):
        RecordedInvestigation(
            candidate_id=CandidateId("candidate_1"),
            withheld="this review holds no analysed structure",
            termination=Termination.NATURAL_END,
        )


def test_an_unrecorded_termination_is_not_a_natural_end() -> None:
    """The legacy shape, and the one reading of it that must never be taken.

    A stored review from before this field decodes with `termination=None` and its lookups
    intact. Reading that as `NATURAL_END` would tell a judge the search had run to its own
    end, on the strength of a field that simply was not written yet.
    """

    legacy = RecordedInvestigation(
        candidate_id=CandidateId("candidate_1"),
        lookups=(InvestigationLookup("related_code", (("qualified_name", "x"),), "row"),),
    )

    assert legacy.termination is None
    assert legacy.termination is not Termination.NATURAL_END

    from archcompass.reasoning.adapters.langchain import observations_text

    rendered = observations_text(legacy)
    assert "not recorded" in rendered
    assert "of its own accord" not in rendered


def test_a_truncated_investigation_tells_the_judge_it_may_be_incomplete() -> None:
    """Silence after four of six intended lookups is unexplored, not absent."""

    from archcompass.reasoning.adapters.langchain import observations_text

    rendered = observations_text(
        RecordedInvestigation(
            candidate_id=CandidateId("candidate_1"),
            lookups=(InvestigationLookup("read_code", (("qualified_name", "x"),), "src"),),
            termination=Termination.MODEL_CALL_LIMIT,
        )
    )

    assert "cut short" in rendered
    assert "model_call_limit" in rendered
    assert "unexplored rather than as absence" in rendered


def test_the_judge_is_told_whose_choice_the_observations_were() -> None:
    """Detector evidence and model-chosen lookups are two kinds of thing in one prompt.

    They are both allowed to bear on a verdict and neither may be mistaken for the other, so
    the block that carries the lookups says out loud that a model asked for them.
    """

    from archcompass.reasoning.adapters.langchain import observations_text

    rendered = observations_text(
        RecordedInvestigation(
            candidate_id=CandidateId("candidate_1"),
            lookups=(InvestigationLookup("read_code", (("qualified_name", "x"),), "src"),),
            termination=Termination.NATURAL_END,
        )
    )

    assert "chosen by a model rather than by the detector" in rendered
    assert "not evidence" in rendered


def test_the_investigating_models_own_prose_never_reaches_the_judge() -> None:
    """The lossy layer this refactor exists to remove.

    The judge reads what the repository answered, not what a model made of it. A closing
    paragraph is kept for a human reader and has no authority over a verdict, so it must not
    appear in the prompt the verdict is reached from.
    """

    from archcompass.reasoning.adapters.langchain import observations_text

    rendered = observations_text(
        RecordedInvestigation(
            candidate_id=CandidateId("candidate_1"),
            lookups=(InvestigationLookup("read_code", (("qualified_name", "x"),), "src"),),
            closing="I conclude this boundary is deliberate and the finding is not material.",
            termination=Termination.NATURAL_END,
        )
    )

    assert "deliberate" not in rendered
    assert "not material" not in rendered
