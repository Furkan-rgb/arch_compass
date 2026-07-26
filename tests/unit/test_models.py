from __future__ import annotations

import pytest
from pydantic import ValidationError

from archcompass.domain.atlas import (
    AtlasQueryPlan,
    ChangeAmplificationMetrics,
    CognitiveScopeMetrics,
    FindingCandidate,
    FindingParticipant,
    FindingPattern,
)
from archcompass.domain.case import ArchitectureCase, CaseStatement, StatementKind
from archcompass.domain.review import BoundaryReview, ReviewedBoundary, ReviewStatus


def _candidate() -> FindingCandidate:
    return FindingCandidate(
        pattern=FindingPattern.SOLE_IMPLEMENTATION,
        summary="package.Port is implemented only by package.Adapter.",
        participants=[
            FindingParticipant(
                node_id="port", qualified_name="package.Port", role="Declares it."
            )
        ],
        limitations="Counted from one static snapshot.",
    )


def test_public_models_forbid_unknown_fields() -> None:
    with pytest.raises(ValidationError):
        ArchitectureCase.model_validate(
            {
                "title": "Case",
                "problem_statement": "A problem",
                "desired_outcome": "An outcome",
                "unexpected": True,
            }
        )


def test_a_case_holds_no_advisor_output() -> None:
    """The case is user intent, and only that (ADR 0007).

    An advisor that writes its conclusions back into the case makes it both the question and
    the answer, and a reader then cannot tell which half they are looking at. Advisor output
    lives in the review, pinned to the revision that produced it — so these fields are
    refused rather than ignored.
    """

    for field, value in (
        ("current_recommendation", {"summary": "Remove it", "rationale": "Because"}),
        ("confidence", {"level": "high", "rationale": "Because"}),
        ("advisor_design_forces", [{"text": "Prior observation", "kind": "force"}]),
    ):
        with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
            ArchitectureCase.model_validate(
                {
                    "title": "Case",
                    "problem_statement": "A problem",
                    "desired_outcome": "An outcome",
                    field: value,
                }
            )


def test_architecture_case_rejects_duplicate_user_force_ids() -> None:
    duplicate_id = "force-user"

    with pytest.raises(
        ValidationError,
        match="design_forces contains duplicate user-authored IDs",
    ):
        ArchitectureCase(
            title="Case",
            problem_statement="A problem",
            desired_outcome="An outcome",
            design_forces=[
                CaseStatement(
                    id=duplicate_id,
                    text="Ownership",
                    kind=StatementKind.FORCE,
                ),
                CaseStatement(
                    id=duplicate_id,
                    text="Lifecycle",
                    kind=StatementKind.FORCE,
                ),
            ],
        )


def test_metric_models_accept_only_their_truthful_names() -> None:
    """The overstated pre-release metric names are gone, not aliased."""

    with pytest.raises(ValidationError):
        ChangeAmplificationMetrics.model_validate({"public_interfaces_crossed": 4})
    with pytest.raises(ValidationError):
        CognitiveScopeMetrics.model_validate({"symbols_in_representative_path": 7})

    amplification = ChangeAmplificationMetrics.model_validate(
        {"public_call_targets_in_affected_modules": 4}
    )
    cognitive = CognitiveScopeMetrics.model_validate(
        {"bounded_resolved_call_chain_nodes": 7}
    )

    assert amplification.public_call_targets_in_affected_modules == 4
    assert cognitive.bounded_resolved_call_chain_nodes == 7
    assert amplification.model_dump(mode="json") == {
        "likely_affected_modules": 0,
        "public_call_targets_in_affected_modules": 4,
        "coordinated_implementations": 0,
        "configuration_locations": 0,
        "reverse_neighbourhood_tests": 0,
    }
    assert cognitive.model_dump(mode="json")["bounded_resolved_call_chain_nodes"] == 7


def test_query_plan_uses_discriminated_query_contracts() -> None:
    plan = AtlasQueryPlan.model_validate(
        {
            "iteration": 1,
            "rationale": "Inspect",
            "queries": [{"kind": "node_details", "node_id": "node_1"}],
        }
    )
    assert plan.queries[0].kind == "node_details"
    with pytest.raises(ValidationError):
        AtlasQueryPlan.model_validate(
            {
                "iteration": 1,
                "rationale": "Inspect",
                "queries": [{"kind": "unknown"}],
            }
        )


def test_a_cleared_boundary_cannot_carry_a_recommended_response() -> None:
    """An advisor that always has a next action has not answered the question."""

    with pytest.raises(ValidationError, match="must not carry a response"):
        ReviewedBoundary(
            reference="BR-001",
            candidate=_candidate(),
            material=False,
            rationale="The boundary is the process edge this case names.",
            recommended_response="Remove it.",
        )


def test_a_succeeded_review_must_carry_its_report() -> None:
    """A success with nothing to show is a failure that reported the wrong status."""

    with pytest.raises(ValidationError, match="must carry its report"):
        BoundaryReview(
            status=ReviewStatus.SUCCEEDED,
            case_id="case-1",
            case_revision=1,
            atlas_version_id="atlas-1",
            reasoning_model="fake:test",
            prompt_identity="judge-finding-candidate:v3:abc",
        )
