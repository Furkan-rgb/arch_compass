"""Inputs and replies for the two reasoning stages, shared by the adapter tests.

Both transports are exercised through `judge_finding_candidate`: it is the stage with the
most demanding contract — a positional array whose length the schema fixes — so a
transport that carries it correctly carries the other one too.
"""

from __future__ import annotations

import json

from archcompass.domain.atlas import (
    FindingCandidate,
    FindingMeasurement,
    FindingParticipant,
    FindingPattern,
)
from archcompass.domain.case import ArchitectureCase
from archcompass.domain.policy import (
    PolicyDocument,
    PolicyScope,
    PolicySource,
    PolicyStrength,
)


def case() -> ArchitectureCase:
    return ArchitectureCase(
        title="Provider ownership",
        problem_statement="Provider-specific capabilities leak into orchestration.",
        desired_outcome="Keep orchestration provider-neutral.",
        expected_future_changes=["A second provider"],
    )


def candidate() -> FindingCandidate:
    return FindingCandidate(
        pattern=FindingPattern.SOLE_IMPLEMENTATION,
        summary="package.Port is implemented only by package.Adapter.",
        participants=[
            FindingParticipant(
                node_id="port",
                qualified_name="package.Port",
                role="Declares the abstraction.",
            ),
            FindingParticipant(
                node_id="adapter",
                qualified_name="package.Adapter",
                role="The only implementation of it in this repository.",
            ),
        ],
        measurements=[
            FindingMeasurement(name="implementations", value=1, unit="implementations")
        ],
        limitations="Counted from one static snapshot.",
    )


def policy(policy_id: str, title: str) -> PolicyDocument:
    return PolicyDocument(
        id=policy_id,
        title=title,
        scope=PolicyScope.GENERAL,
        strength=PolicyStrength.PREFERRED,
        tags=["structure"],
        source=PolicySource(author="test"),
        body=f"{title} body.",
        source_path=f"policies/{policy_id}.md",
        content_hash=f"hash-{policy_id}",
    )


def policies(count: int = 2) -> list[PolicyDocument]:
    return [policy(f"policy-{index}", f"Policy {index}") for index in range(1, count + 1)]


def verdict_json(
    *,
    bearings: int = 2,
    material: bool = False,
    rationale: str = "The boundary is the process edge this case names.",
) -> str:
    """A well-formed reply, with one bearing per presented policy."""

    return json.dumps(
        {
            "rationale": rationale,
            "policy_bearings": [{"bears_on": False, "how": ""} for _ in range(bearings)],
            "material": material,
            "recommended_response": "Name the implementation directly." if material else "",
        }
    )
