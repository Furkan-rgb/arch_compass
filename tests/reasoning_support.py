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
from archcompass.domain.review import (
    BoundaryReview,
    BoundaryReviewReport,
    ReviewedBoundary,
    ReviewOverview,
    ReviewStatus,
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


def reviewed_boundary(
    reference: str,
    name: str,
    *,
    material: bool,
    pattern: FindingPattern = FindingPattern.SOLE_IMPLEMENTATION,
    measurements: list[FindingMeasurement] | None = None,
) -> ReviewedBoundary:
    """One judged boundary whose own text never contains its reference.

    Named separately from the reference on purpose: a fixture with `BR-001` inside the
    abstraction's name would make "no reference crosses the wire" pass for the wrong reason.
    """

    return ReviewedBoundary(
        reference=reference,
        candidate=FindingCandidate(
            pattern=pattern,
            summary=f"package.{name} is implemented only by package.{name}Adapter.",
            participants=[
                FindingParticipant(
                    node_id=name.lower(),
                    qualified_name=f"package.{name}",
                    role="Declares the abstraction.",
                )
            ],
            measurements=(
                [FindingMeasurement(name="implementations", value=1)]
                if measurements is None
                else measurements
            ),
            limitations="A static count cannot see runtime registration.",
        ),
        material=material,
        rationale=f"Argued from the case, about {name}.",
        recommended_response="Call the implementation directly." if material else "",
    )


def review(
    boundaries: list[ReviewedBoundary],
    *,
    overview: ReviewOverview | None = None,
) -> BoundaryReview:
    """A succeeded review holding those boundaries, ready to be questioned."""

    return BoundaryReview(
        case_id="case-test",
        case_revision=1,
        atlas_version_id="atlas-test",
        status=ReviewStatus.SUCCEEDED,
        reasoning_model="fake:fake-answerer",
        prompt_identity="answer-review-question:v3:abcdef123456",
        report=BoundaryReviewReport(
            case_title="Scheduler boundaries",
            problem_and_desired_outcome="Decide.\n\nA verdict per boundary.",
            reviewed=boundaries,
            overview=overview
            or ReviewOverview(
                situation="One operator, one server.",
                limits="One detector ran.",
            ),
        ),
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


#: The ordinary hinge: every field answered, and the verdict the same under both answers.
#: Filled rather than blank because the schema requires it — the three prose fields are the
#: working behind the declaration, and a reply may no longer skip to the conclusion.
SETTLED_HINGE = {
    "unknown": "Whether a second provider is actually contracted.",
    "if_confirmed": "The boundary absorbs the change and should stay.",
    "if_denied": "The constraint the case states keeps the boundary anyway.",
    "dependence": "stands_either_way",
}


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
            "hinge": SETTLED_HINGE,
            "verdict": "should_change" if material else "leave_as_is",
            "recommended_response": "Name the implementation directly." if material else "",
        }
    )
