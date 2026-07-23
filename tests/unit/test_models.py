from __future__ import annotations

import pytest
from pydantic import ValidationError

from archcompass.domain.atlas import AtlasQueryPlan
from archcompass.domain.case import ArchitectureCase
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
