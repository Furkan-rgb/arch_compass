"""The blocking rule and the pull-request comment, examined without a run behind them.

Both are decisions about presentation of a judgement rather than the judgement itself, and
both are where a mistake is silent: a blocking rule that is one condition too loose fails a
pull request nobody could have prevented, and a comment renderer that paraphrases publishes a
second version of the review under the review's name. Neither would be caught by an
integration test that only asserts an exit code.

The vocabulary here is the revision partition. `new`, `changed` and `known` are gone with the
baseline that gave them their meaning, and what a boundary is now measured by is where this
revision put it and whether anybody has decided about it.
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
from archcompass.application.standings import needs_attention, standing_for
from archcompass.domain.atlas import (
    FindingCandidate,
    FindingParticipant,
    FindingPattern,
)
from archcompass.domain.delta import AddressedBoundary, BoundaryState, JudgedBecause
from archcompass.domain.review import ReviewedBoundary, ReviewStatus
from archcompass.domain.triage import DecisionState, StandingDecision

RATIONALE = (
    "Nothing in this snapshot depends on the abstraction, so the boundary currently sits "
    "in front of a single concrete implementation with no caller reading the contract."
)


def _decision(state: DecisionState, fingerprint: str = "bfp_1") -> StandingDecision:
    return StandingDecision(
        branch_id="branch_1",
        boundary_fingerprint=fingerprint,
        state=state,
        author="Deniz",
        reason="Intentional seam for the billing split.",
        review_id="rev_1",
        boundary_reference="BR-001",
        material=True,
        verdict_label="not earning its place",
    )


def _reviewed(**overrides: object) -> ReviewedBoundary:
    fields: dict[str, object] = {
        "reference": "BR-001",
        "candidate": FindingCandidate(
            pattern=FindingPattern.SOLE_IMPLEMENTATION,
            summary="package.Port is implemented only by package.Adapter.",
            participants=[
                FindingParticipant(
                    node_id="port",
                    qualified_name="package.Port",
                    role="Declares the abstraction.",
                )
            ],
            limitations="A static count cannot see runtime registration.",
        ),
        "fingerprint": "bfp_1",
        "material": True,
        "rationale": RATIONALE,
    }
    fields.update(overrides)
    return ReviewedBoundary.model_validate(fields)


def test_a_material_undecided_judged_boundary_blocks() -> None:
    assert is_blocking(
        delta_state=BoundaryState.JUDGED, needs_attention=True, holding=False
    )


def test_a_boundary_this_revision_carried_never_blocks() -> None:
    """Nothing moved under it since the previous revision said its piece."""

    assert not is_blocking(
        delta_state=BoundaryState.CARRIED, needs_attention=True, holding=False
    )


def test_a_boundary_that_carried_its_standing_across_a_rename_never_blocks() -> None:
    """A rename is not a change this pull request introduced, and it is not a way to hide
    one either: the standing follows the succession, so the boundary is only quiet if it
    was quiet before somebody moved it."""

    assert not is_blocking(
        delta_state=BoundaryState.SUCCEEDED, needs_attention=True, holding=False
    )


def test_a_run_that_could_not_partition_itself_treats_everything_as_judged() -> None:
    """No branch lineage means no previous revision, which is the state a first run is in."""

    assert is_blocking(delta_state=None, needs_attention=True, holding=False)


def test_a_boundary_nobody_needs_to_look_at_never_blocks() -> None:
    """Cleared, or decided. `needs_attention` is where those two are told apart."""

    assert not is_blocking(
        delta_state=BoundaryState.JUDGED, needs_attention=False, holding=False
    )


def test_a_held_verdict_never_blocks() -> None:
    """It rests on a question nobody in a pipeline was in a position to answer."""

    assert not is_blocking(
        delta_state=BoundaryState.JUDGED, needs_attention=True, holding=True
    )


def test_a_cleared_verdict_never_needs_attention() -> None:
    """Evidence that the advisor looked is not a finding."""

    assert not needs_attention(_reviewed(material=False), {})


def test_an_undecided_material_boundary_needs_attention() -> None:
    assert needs_attention(_reviewed(), {})


@pytest.mark.parametrize(
    "state", [DecisionState.ACCEPTED, DecisionState.WAIVED, DecisionState.PARKED]
)
def test_any_recorded_decision_silences_a_finding(state: DecisionState) -> None:
    """Parking included. It is a decision a person took under their own name — "we have seen
    this and it is not now" — and treating it as no answer would leave a team with no way to
    say that except by accepting something they do not accept."""

    assert not needs_attention(_reviewed(), {"bfp_1": _decision(state)})


def test_a_decision_carries_across_a_succession_to_the_boundary_that_replaced_it() -> None:
    """The rename case, read rather than merely recorded: the standing is filed under the
    predecessor's fingerprint, and this is what makes it apply to the successor."""

    standings = {"bfp_old": _decision(DecisionState.ACCEPTED, "bfp_old")}
    renamed = _reviewed(fingerprint="bfp_new", succeeds="bfp_old")

    assert standing_for(renamed, standings) is not None
    assert not needs_attention(renamed, standings)


def test_the_boundarys_own_decision_wins_over_the_one_it_succeeded() -> None:
    own = _decision(DecisionState.PARKED, "bfp_new")
    standings = {
        "bfp_new": own,
        "bfp_old": _decision(DecisionState.ACCEPTED, "bfp_old"),
    }

    assert standing_for(_reviewed(fingerprint="bfp_new", succeeds="bfp_old"), standings) is own


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
        "delta_state": BoundaryState.JUDGED,
        "judged_because": JudgedBecause.NEW,
        "material": True,
        "verdict_label": "not earning its place",
        "rationale": RATIONALE,
        "needs_attention": True,
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
        "previous_review_id": "rev_0",
        "first_revision": False,
        "counts": CiCounts(
            carried=40,
            judged=1,
            succeeded=0,
            addressed=0,
            attention=1,
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


def test_carried_boundaries_are_counted_and_not_listed() -> None:
    """The delta working. The count stays visible so the silence is a claim."""

    carried = _boundary(
        reference="BR-002",
        delta_state=BoundaryState.CARRIED,
        judged_because=None,
        needs_attention=False,
        blocking=False,
        rationale="A rationale nobody needs to read again.",
    )
    comment = render_ci_comment(_run(_boundary(), carried))

    assert "BR-002" not in comment
    assert "40 carried" in comment


def test_a_closure_is_named_rather_than_counted() -> None:
    """The one piece of good news the tool has, and it used to deliver it by going quiet."""

    closed = AddressedBoundary(
        fingerprint="bfp_gone",
        pattern=FindingPattern.SOLE_IMPLEMENTATION,
        title="package.Port is implemented only by package.Adapter.",
        material=True,
        verdict_label="not earning its place",
        last_seen_in_review="rev_0",
        last_reference="BR-004",
    )
    run = _run(_boundary(), addressed=[closed])

    comment = render_ci_comment(run)
    summary = render_ci_summary(run)

    assert "### Addressed" in comment
    assert "package.Port is implemented only by package.Adapter." in comment
    assert "BR-004" in comment
    assert "Addressed: package.Port is implemented only by package.Adapter." in summary


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
        needs_attention=False,
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


def test_a_revision_that_moved_nothing_says_so_rather_than_showing_an_empty_section() -> None:
    carried = _boundary(
        delta_state=BoundaryState.CARRIED,
        judged_because=None,
        needs_attention=False,
        blocking=False,
    )
    run = _run(carried, blocking=[], exit_code=0)

    assert "Nothing on this branch moved since the previous revision." in render_ci_comment(run)
    assert "Nothing on this branch moved since the previous revision." in render_ci_summary(run)


def test_the_summary_leads_with_the_partition_and_quotes_the_rationale_whole() -> None:
    """The log reader gets the untruncated verdict: there is no width to save here, and the
    excerpt exists for the comment's sake rather than for the reviewer's."""

    summary = render_ci_summary(_run(_boundary()))

    assert summary.splitlines()[2].startswith(
        "40 carried, 1 judged, 0 succeeded, 0 addressed — 1 needing attention"
    )
    assert "Compared with revision rev_0." in summary
    assert RATIONALE in summary
    assert "1 material boundary to account for: BR-001." in summary


def test_a_judged_boundary_names_the_input_that_moved_it() -> None:
    """The whole reason `changed` was retired: a reader must never hear "your code moved"
    when what moved was the model."""

    moved = _boundary(judged_because=JudgedBecause.MODEL)

    assert "because model" in render_ci_summary(_run(moved))
    assert "because model" in render_ci_comment(_run(moved))


def test_a_first_revision_says_it_had_nothing_to_compare_with() -> None:
    """Two judged boundaries look identical whether this is revision one or a revision that
    broke everything, unless the document says which."""

    summary = render_ci_summary(
        _run(_boundary(), first_revision=True, previous_review_id=None)
    )

    assert "First revision on feature/split" in summary
