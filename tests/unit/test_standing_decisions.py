"""What a standing decision refuses to be, before any of it reaches a database."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from archcompass.domain.triage import DecisionComment, DecisionState, StandingDecision

CONTEXT = {
    "branch_id": "branch_abc",
    "boundary_fingerprint": "bdry_123",
    "author": "Deniz",
    "review_id": "rev_1",
    "boundary_reference": "BR-001",
    "material": True,
    "verdict_label": "Not earning its place",
}


def test_a_waiver_must_say_why() -> None:
    """The rule the whole state exists for: silencing a finding without stating a reason."""

    with pytest.raises(ValidationError, match="why it was waived"):
        StandingDecision(state=DecisionState.WAIVED, **CONTEXT)

    with pytest.raises(ValidationError, match="why it was waived"):
        StandingDecision(state=DecisionState.WAIVED, reason="   ", **CONTEXT)


def test_waiving_with_a_reason_is_accepted() -> None:
    decision = StandingDecision(
        state=DecisionState.WAIVED,
        reason="Intentional seam for the billing split.",
        **CONTEXT,
    )

    assert decision.decision_id.startswith("dec_")
    assert decision.state is DecisionState.WAIVED


@pytest.mark.parametrize("state", [DecisionState.ACCEPTED, DecisionState.PARKED])
def test_the_other_states_need_no_reason(state: DecisionState) -> None:
    assert StandingDecision(state=state, **CONTEXT).reason is None


def test_an_author_is_required_even_though_nobody_is_authenticated() -> None:
    with pytest.raises(ValidationError):
        StandingDecision(
            state=DecisionState.ACCEPTED,
            **{**CONTEXT, "author": ""},
        )


def test_a_decision_compares_itself_to_a_verdict_rather_than_to_a_run() -> None:
    """A second run reaching the same conclusion has not invalidated anyone's judgement."""

    decision = StandingDecision(state=DecisionState.ACCEPTED, **CONTEXT)

    assert decision.taken_on(material=True, verdict_label="Not earning its place")
    assert not decision.taken_on(material=False, verdict_label="Not earning its place")
    assert not decision.taken_on(material=True, verdict_label="Earning its place")


def test_a_decision_is_frozen_like_every_other_record() -> None:
    decision = StandingDecision(state=DecisionState.PARKED, **CONTEXT)

    with pytest.raises(ValidationError):
        decision.state = DecisionState.ACCEPTED  # type: ignore[misc]


def test_a_comment_carries_a_body_and_a_position() -> None:
    comment = DecisionComment(
        branch_id="branch_abc",
        boundary_fingerprint="bdry_123",
        author="Rae",
        body="This seam is deliberate.",
        created_at=datetime(2026, 8, 4, tzinfo=UTC),
    )

    assert comment.comment_id.startswith("dcom_")
    assert comment.ordinal == 1

    with pytest.raises(ValidationError):
        DecisionComment(
            branch_id="branch_abc",
            boundary_fingerprint="bdry_123",
            author="Rae",
            body="",
        )
