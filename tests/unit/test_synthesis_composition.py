"""Composition guarantees that replace whole classes of provider repair.

Each test here pins a failure mode that used to require a repair mechanism and is now
either impossible to express or rejected outright.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from archcompass.application.synthesis import (
    build_claim_pool,
    compose_recommendation,
    validate_proposal,
)
from archcompass.domain.case import (
    ArchitectureCase,
    CaseAlternative,
    CaseStatement,
    Confidence,
    ConfidenceLevel,
    StatementKind,
)
from archcompass.domain.consultation import (
    AtlasEvidenceReference,
    Claim,
    ClaimClassification,
    ConcernAnalysis,
    ConcernCluster,
    DesignForce,
    ImportanceLevel,
    RecommendationDisposition,
    ScenarioEvaluation,
)
from archcompass.domain.proposals import (
    ProposedADR,
    ProposedAdvisorClaim,
    ProposedFinding,
    ProposedRecommendation,
    ProposedStatement,
)

_CLUSTER = ConcernCluster(
    cluster_id="cluster-ownership",
    title="Responsibility ownership",
    rationale="Decide who owns provider selection.",
    design_force_ids=["force-provider"],
)
_FORCE = DesignForce(
    force_id="force-provider",
    title="Provider variation",
    description="A second provider is plausible.",
    importance="medium",
    importance_rationale="Stated by the fixture.",
)
_ALTERNATIVES = [
    CaseAlternative(id="alt-keep", title="Keep local", summary="Change nothing."),
    CaseAlternative(id="alt-port", title="Introduce a port", summary="Add a boundary."),
]
_SCENARIOS = [
    ScenarioEvaluation(
        scenario="A second provider arrives.",
        assumptions=["It uses a different transport."],
        alternative_results={item.id: f"Outcome for {item.title}" for item in _ALTERNATIVES},
        conclusion="The port contains the change.",
    )
]
_CONFIDENCE = Confidence(level=ConfidenceLevel.MEDIUM, rationale="One surfaced node.")


def _case() -> ArchitectureCase:
    return ArchitectureCase(
        title="Provider ownership",
        problem_statement="Transport details leak into application code.",
        desired_outcome="Give provider selection one owner.",
        confirmed_facts=[
            CaseStatement(
                id="fact-config",
                text="Provider selection must stay configurable.",
                kind=StatementKind.FACT,
            )
        ],
    )


def _analysis() -> ConcernAnalysis:
    return ConcernAnalysis(
        cluster_id=_CLUSTER.cluster_id,
        concern=_CLUSTER.title,
        findings=[
            Claim(
                claim_id="claim-observation",
                text="The adapter exposes transport types to the application.",
                classification=ClaimClassification.REPOSITORY_OBSERVATION,
                atlas_references=[AtlasEvidenceReference(node_id="node-adapter")],
            )
        ],
        implications=["Application changes require transport knowledge."],
    )


def _pool():
    return build_claim_pool(
        case=_case(),
        clusters=[_CLUSTER],
        analyses=[_analysis()],
    )


def _statement(text: str, refs: list[str]) -> ProposedStatement:
    return ProposedStatement(
        text=text,
        classification=ClaimClassification.ADVISOR_INFERENCE,
        claim_refs=refs,
    )


def _proposal(
    *,
    claim_refs: list[str],
    cluster_ref: str = "C1",
    advisor_claims: list[ProposedAdvisorClaim] | None = None,
    disposition: str = "move_responsibility",
) -> ProposedRecommendation:
    statement = _statement("Move transport behind a port.", claim_refs)
    return ProposedRecommendation(
        disposition=disposition,
        problem_and_desired_outcome="Transport leaks; give it one owner.",
        confidence=_CONFIDENCE,
        advisor_claims=advisor_claims or [],
        findings=[
            ProposedFinding(
                cluster_ref=cluster_ref,
                title="Transport crosses the boundary",
                summary="The adapter's vocabulary reaches application code.",
                importance=ImportanceLevel.HIGH,
                importance_rationale="Every change must reason about transport.",
                confidence=_CONFIDENCE,
                consequence="Application changes require transport knowledge.",
                claim_refs=claim_refs,
                recommended_response="Introduce a provider port.",
                uncertainty=[],
            )
        ],
        decision_summary=statement,
        recommended_architecture=statement,
        responsibility_allocation=[statement],
        conceptual_interfaces=[],
        change_amplification_analysis=statement,
        trade_offs=[statement],
        implementation_sequence=[statement],
        reversal_conditions=[statement],
        revisit_triggers=[statement],
        adr=ProposedADR(
            title="Introduce a provider port",
            context="Transport leaks into application code.",
            decision=statement,
            consequences=[statement],
        ),
    )


def _compose(proposal: ProposedRecommendation):
    return compose_recommendation(
        proposal,
        pool=_pool(),
        forces=[_FORCE],
        alternatives=_ALTERNATIVES,
        scenarios=_SCENARIOS,
        analyses=[_analysis()],
        packets=[],
    ).report


def test_claims_are_placed_into_sections_by_their_own_classification() -> None:
    """Misclassification is not repaired, because the model never picks a section."""

    report = _compose(_proposal(claim_refs=["E1", "E2"]))

    assert [claim.claim_id for claim in report.repository_observations] == [
        "claim-observation"
    ]
    assert [claim.claim_id for claim in report.confirmed_context] == ["fact-config"]
    assert report.relevant_policies == []
    assert {claim.claim_id for claim in report.evidence_appendix} == {
        "claim-observation",
        "fact-config",
    }


def test_canonical_artifacts_are_injected_and_cannot_be_altered() -> None:
    """Forces, alternatives, and scenarios are absent from the wire contract."""

    report = _compose(_proposal(claim_refs=["E1"]))

    assert report.important_design_forces == [_FORCE]
    assert report.alternatives_considered == _ALTERNATIVES
    assert report.scenario_analysis == _SCENARIOS
    assert "important_design_forces" not in ProposedRecommendation.model_fields
    assert "alternatives_considered" not in ProposedRecommendation.model_fields
    assert "scenario_analysis" not in ProposedRecommendation.model_fields


def test_identical_authored_claims_collapse_to_one_identity() -> None:
    """Claim IDs are content-derived, so duplicates cannot describe different claims."""

    authored = [
        ProposedAdvisorClaim(
            ref="X1",
            text="The boundary follows from the combined evidence.",
            classification=ClaimClassification.ADVISOR_INFERENCE,
        ),
        ProposedAdvisorClaim(
            ref="X2",
            text="The boundary follows from the combined evidence.",
            classification=ClaimClassification.ADVISOR_INFERENCE,
        ),
    ]
    report = _compose(
        _proposal(claim_refs=["E1", "X1", "X2"], advisor_claims=authored)
    )

    authored_ids = {
        claim.claim_id
        for claim in report.evidence_appendix
        if claim.classification == ClaimClassification.ADVISOR_INFERENCE
    }
    assert len(authored_ids) == 1


def test_a_provider_cannot_author_repository_evidence() -> None:
    """Only advisor inference and derived constraints are the model's to state."""

    with pytest.raises(ValueError, match="supplied claim pool"):
        ProposedAdvisorClaim(
            ref="X1",
            text="The adapter imports the transport package.",
            classification=ClaimClassification.REPOSITORY_OBSERVATION,
        )


def test_unknown_claim_handles_are_reported_not_silently_dropped() -> None:
    errors = validate_proposal(_proposal(claim_refs=["E1", "E99"]), pool=_pool())

    assert any("unknown claim handles" in error and "E99" in error for error in errors)


def test_a_finding_must_cite_evidence_from_its_own_cluster() -> None:
    """Citing only case context leaves a finding without packet evidence."""

    errors = validate_proposal(_proposal(claim_refs=["E2"]), pool=_pool())

    assert any("own concern cluster" in error for error in errors)


def test_every_concern_cluster_must_receive_a_finding() -> None:
    pool = build_claim_pool(
        case=_case(),
        clusters=[
            _CLUSTER,
            ConcernCluster(
                cluster_id="cluster-lifecycle",
                title="Resource lifecycle",
                rationale="Decide who closes the client.",
                design_force_ids=["force-lifecycle"],
            ),
        ],
        analyses=[_analysis()],
    )

    errors = validate_proposal(_proposal(claim_refs=["E1"]), pool=pool)

    assert any("No finding was produced" in error and "C2" in error for error in errors)


def test_an_unknown_disposition_cannot_be_expressed() -> None:
    """The disposition set is closed, so an invalid one fails at the wire boundary.

    A real model returned "Recommendation" here when the field was free text; the JSON
    schema now enumerates the set, so the grammar cannot produce it and the DTO cannot
    hold it.
    """

    with pytest.raises(ValidationError, match="disposition"):
        _proposal(claim_refs=["E1"], disposition="do_something_clever")


def test_the_wire_schema_enumerates_every_disposition() -> None:
    """The constraint must reach the JSON schema, which is what constrains the model."""

    schema = ProposedRecommendation.model_json_schema()
    reference = schema["properties"]["disposition"]["$ref"].rsplit("/", 1)[-1]

    assert set(schema["$defs"][reference]["enum"]) == {
        item.value for item in RecommendationDisposition
    }
