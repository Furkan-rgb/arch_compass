from __future__ import annotations

import pytest
from pydantic import ValidationError

from archcompass.domain.atlas import (
    AtlasQueryPlan,
    ChangeAmplificationMetrics,
    CognitiveScopeMetrics,
)
from archcompass.domain.case import ArchitectureCase, CaseStatement, StatementKind
from archcompass.domain.consultation import RecommendationReport


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


def test_legacy_run_sourced_forces_upgrade_without_erasing_user_forces() -> None:
    architecture_case = ArchitectureCase.model_validate(
        {
            "schema_version": 2,
            "title": "Case",
            "problem_statement": "A problem",
            "desired_outcome": "An outcome",
            "design_forces": [
                {
                    "id": "force-user",
                    "text": "User intent",
                    "kind": "force",
                    "source": "user",
                },
                {
                    "id": "force-advisor",
                    "text": "Prior observation",
                    "kind": "force",
                    "source": "run_previous",
                },
            ],
        }
    )

    assert [item.id for item in architecture_case.design_forces] == ["force-user"]
    assert [item.id for item in architecture_case.advisor_design_forces] == ["force-advisor"]


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


def test_legacy_metric_names_load_but_new_json_uses_truthful_names() -> None:
    amplification = ChangeAmplificationMetrics.model_validate({"public_interfaces_crossed": 4})
    cognitive = CognitiveScopeMetrics.model_validate({"symbols_in_representative_path": 7})

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


def test_recommendation_report_requires_actionable_sections() -> None:
    schema = RecommendationReport.model_json_schema()
    required_lists = (
        "important_design_forces",
        "responsibility_allocation",
        "alternatives_considered",
        "scenario_analysis",
        "trade_offs",
        "implementation_sequence",
        "reversal_conditions",
        "revisit_triggers",
    )

    assert all(schema["properties"][name]["minItems"] == 1 for name in required_lists)
