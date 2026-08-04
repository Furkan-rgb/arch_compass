"""The blocking rule and the pull-request comment, examined without a run behind them.

Both are decisions about presentation of a judgement rather than the judgement itself, and
both are where a mistake is silent: a blocking rule that is one condition too loose fails a
pull request nobody could have prevented, and a comment renderer that paraphrases publishes a
second version of the review under the review's name. Neither would be caught by an
integration test that only asserts an exit code.
"""

from __future__ import annotations

import pytest

from archcompass.application.ci import (
    CiBoundary,
    CiCounts,
    CiDecision,
    CiQuestion,
    CiRun,
    FailOn,
    exit_code_for,
    is_blocking,
)
from archcompass.application.ci_rendering import (
    COMMENT_MARKER,
    render_ci_comment,
    render_ci_summary,
)
from archcompass.domain.baseline import BoundaryDisposition
from archcompass.domain.review import ReviewStatus
from archcompass.domain.triage import DecisionState, StandingDecision

RATIONALE = (
    "Nothing in this snapshot depends on the abstraction, so the boundary currently sits "
    "in front of a single concrete implementation with no caller reading the contract."
)


def _decision(state: DecisionState) -> StandingDecision:
    return StandingDecision(
        branch_id="branch_1",
        boundary_fingerprint="bfp_1",
        state=state,
        author="Deniz",
        reason="Intentional seam for the billing split.",
        review_id="rev_1",
        boundary_reference="BR-001",
        material=True,
        verdict_label="not earning its place",
    )


def test_a_new_material_undecided_settled_boundary_blocks() -> None:
    assert is_blocking(
        disposition=BoundaryDisposition.NEW,
        material=True,
        holding=False,
        decision=None,
    )


@pytest.mark.parametrize(
    "disposition",
    [BoundaryDisposition.CHANGED, BoundaryDisposition.KNOWN],
)
def test_a_boundary_the_base_branch_has_seen_never_blocks(
    disposition: BoundaryDisposition,
) -> None:
    """Including `changed`. The structure was there before this branch existed, so whatever
    moved the verdict, this change did not introduce the boundary."""

    assert not is_blocking(
        disposition=disposition, material=True, holding=False, decision=None
    )


def test_a_cleared_verdict_never_blocks() -> None:
    """Evidence that the advisor looked is not a finding."""

    assert not is_blocking(
        disposition=BoundaryDisposition.NEW,
        material=False,
        holding=False,
        decision=None,
    )


def test_a_held_verdict_never_blocks() -> None:
    """It rests on a question nobody in a pipeline was in a position to answer."""

    assert not is_blocking(
        disposition=BoundaryDisposition.NEW,
        material=True,
        holding=True,
        decision=None,
    )


@pytest.mark.parametrize(
    ("state", "blocks"),
    [
        (DecisionState.ACCEPTED, False),
        (DecisionState.WAIVED, False),
        # Parked is explicitly undecided: somebody looked and did not answer, which is not an
        # answer. Treating it as one would make "I will think about it" silence the finding.
        (DecisionState.PARKED, True),
    ],
)
def test_only_an_accepted_or_waived_decision_silences_a_finding(
    state: DecisionState, blocks: bool
) -> None:
    assert (
        is_blocking(
            disposition=BoundaryDisposition.NEW,
            material=True,
            holding=False,
            decision=_decision(state),
        )
        is blocks
    )


@pytest.mark.parametrize(
    ("blocking", "fail_on", "code"),
    [
        ([], FailOn.NEW_MATERIAL, 0),
        (["BR-001"], FailOn.NEW_MATERIAL, 1),
        ([], FailOn.NOTHING, 0),
        (["BR-001"], FailOn.NOTHING, 0),
    ],
)
def test_the_exit_code_follows_the_blocking_set_and_what_the_run_was_told_to_fail_for(
    blocking: list[str], fail_on: FailOn, code: int
) -> None:
    assert exit_code_for(blocking, fail_on) == code


def _boundary(**overrides: object) -> CiBoundary:
    fields: dict[str, object] = {
        "reference": "BR-001",
        "fingerprint": "bfp_1",
        "disposition": BoundaryDisposition.NEW,
        "material": True,
        "verdict_label": "not earning its place",
        "rationale": RATIONALE,
        "blocking": True,
    }
    fields.update(overrides)
    return CiBoundary.model_validate(fields)


def _run(*boundaries: CiBoundary, **overrides: object) -> CiRun:
    fields: dict[str, object] = {
        "case_id": "case_1",
        "case_title": "Warehouse sync boundaries",
        "review_id": "rev_1",
        "status": ReviewStatus.SUCCEEDED,
        "repo_id": "repoid_1",
        "branch_id": "branch_2",
        "branch_name": "feature/split",
        "base_branch_name": "main",
        "base_branch_id": "branch_1",
        "atlas_version_id": "atlas_1",
        "reasoning_model": "fake:deterministic-substitute",
        "baseline_size": 40,
        "counts": CiCounts(
            new=1,
            changed=0,
            known=40,
            holding=0,
            verdicts_reused=40,
            verdicts_total=41,
        ),
        "boundaries": list(boundaries),
        "blocking": [item.reference for item in boundaries if item.blocking],
        "fail_on": FailOn.NEW_MATERIAL,
        "exit_code": 1,
    }
    fields.update(overrides)
    return CiRun.model_validate(fields)


def test_the_comment_opens_with_the_marker_an_action_finds_it_by() -> None:
    """The whole sticky-comment mechanism: one comment edited on every push, found by a
    substring that never varies with the run."""

    comment = render_ci_comment(_run(_boundary()))

    assert comment.splitlines()[0] == COMMENT_MARKER
    assert comment.count(COMMENT_MARKER) == 1


def test_the_comment_quotes_the_verdict_and_never_rewrites_it() -> None:
    comment = render_ci_comment(_run(_boundary()))

    assert "not earning its place" in comment
    assert RATIONALE in comment, "a short rationale is quoted whole"


def test_a_long_rationale_is_cut_at_a_sentence_and_says_that_it_was() -> None:
    """A rationale cut mid-clause can invert the finding it is quoting."""

    long = " ".join(
        f"Sentence number {index} says something about the boundary." for index in range(12)
    )
    comment = render_ci_comment(_run(_boundary(rationale=long)))

    quoted = next(line for line in comment.splitlines() if "Sentence number 0" in line)
    assert quoted.strip().endswith("…")
    assert quoted.strip().rstrip("… ").endswith(".")
    assert "Sentence number 11" not in comment


def test_known_boundaries_are_counted_and_not_listed() -> None:
    """The baseline working. The count stays visible so the silence is a claim."""

    known = _boundary(
        reference="BR-002",
        disposition=BoundaryDisposition.KNOWN,
        blocking=False,
        rationale="A rationale nobody needs to read again.",
    )
    comment = render_ci_comment(_run(_boundary(), known))

    assert "BR-002" not in comment
    assert "40 known" in comment


def test_a_held_boundary_is_listed_with_the_question_that_would_settle_it() -> None:
    held = _boundary(
        reference="BR-003",
        holding=True,
        blocking=False,
        questions=[
            CiQuestion(
                reference="Q-1",
                question="Is a second warehouse vendor coming this year?",
                unknown="Whether a second vendor is planned.",
                answer_belongs_in="expected_future_changes",
            )
        ],
    )
    comment = render_ci_comment(_run(_boundary(), held))

    assert "Held on an open question" in comment
    assert "Is a second warehouse vendor coming this year?" in comment
    assert "never blocking" in comment


def test_a_waiver_is_named_in_the_comment_rather_than_silently_removing_the_finding() -> None:
    decided = _boundary(
        blocking=False,
        decision=CiDecision(
            decision_id="dec_1",
            state=DecisionState.WAIVED,
            author="Deniz",
            reason="Intentional seam for the billing split.",
            branch_id="branch_1",
            taken_on_this_verdict=True,
        ),
    )
    comment = render_ci_comment(_run(decided, blocking=[], exit_code=0))

    assert "waived by Deniz" in comment
    assert "Intentional seam for the billing split." in comment


def test_a_decision_taken_against_an_earlier_verdict_says_so() -> None:
    stale = _boundary(
        blocking=True,
        decision=CiDecision(
            decision_id="dec_1",
            state=DecisionState.PARKED,
            author="Deniz",
            reason=None,
            branch_id="branch_1",
            taken_on_this_verdict=False,
        ),
    )
    comment = render_ci_comment(_run(stale))

    assert "taken against an earlier verdict" in comment


def test_the_footer_attributes_carried_forward_verdicts() -> None:
    """Required by the plan: a cached verdict is not evidence that anything was looked at
    twice, and the comment has to say which it is."""

    comment = render_ci_comment(_run(_boundary()))

    assert "40 of 41 verdicts reused from earlier runs" in comment


def test_no_link_is_invented_without_a_workspace_to_link_to() -> None:
    without = render_ci_comment(_run(_boundary()))
    with_url = render_ci_comment(_run(_boundary()), workspace_url="https://compass.example/")

    assert "](" not in without
    assert "[BR-001](https://compass.example/reviews/rev_1#BR-001)" in with_url


def test_a_run_with_nothing_new_says_so_rather_than_showing_an_empty_section() -> None:
    known = _boundary(disposition=BoundaryDisposition.KNOWN, blocking=False)
    run = _run(known, blocking=[], exit_code=0)

    assert "Nothing new or changed on this branch." in render_ci_comment(run)
    assert "Nothing new or changed on this branch." in render_ci_summary(run)


def test_the_summary_leads_with_the_partition_and_quotes_the_rationale_whole() -> None:
    """The log reader gets the untruncated verdict: there is no width to save here, and the
    excerpt exists for the comment's sake rather than for the reviewer's."""

    summary = render_ci_summary(_run(_boundary()))

    assert summary.splitlines()[2].startswith("1 new, 0 changed, 40 known")
    assert RATIONALE in summary
    assert "1 new material boundary to account for: BR-001." in summary
