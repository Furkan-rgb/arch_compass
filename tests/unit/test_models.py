from __future__ import annotations

import pytest
from pydantic import ValidationError

from archcompass.domain.atlas import AtlasQueryPlan
from archcompass.domain.case import ArchitectureCase


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

