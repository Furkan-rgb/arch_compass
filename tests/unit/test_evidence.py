from archcompass.adapters.models.deterministic import DeterministicReasoningProvider
from archcompass.application.evidence import (
    repair_report_evidence,
    validate_report_evidence,
)
from archcompass.domain.case import ArchitectureCase
from archcompass.domain.consultation import (
    AtlasEvidenceReference,
    Claim,
    ClaimClassification,
    GlobalContext,
)


def test_invented_evidence_is_rejected() -> None:
    provider = DeterministicReasoningProvider()
    case = ArchitectureCase(
        title="Test",
        problem_statement="Test a claim",
        desired_outcome="Validate evidence",
    )
    context = GlobalContext(
        case_id=case.case_id,
        revision=1,
        title=case.title,
        problem=case.problem_statement,
        desired_outcome=case.desired_outcome,
        goals=[],
        constraints=[],
        future_changes=[],
        non_goals=[],
        confirmed_facts=[],
        assumptions=[],
    )
    alternatives = provider.generate_alternatives(context, [])
    scenarios = provider.evaluate_scenarios(context, alternatives, [])
    forces = provider.discover_design_forces(context)
    clusters = provider.cluster_design_forces(context, forces)
    report = provider.synthesize_recommendation(
        case, context, forces, clusters, [], alternatives, scenarios, []
    )
    bad = Claim(
        text="Invented observation",
        classification=ClaimClassification.REPOSITORY_OBSERVATION,
        atlas_references=[AtlasEvidenceReference(node_id="node_invented")],
    )
    report = report.model_copy(
        update={
            "repository_observations": [bad],
            "evidence_appendix": [bad],
        }
    )
    errors = validate_report_evidence(report, allowed_nodes={}, allowed_policy_ids=set())
    assert any("unknown atlas node" in error for error in errors)

    repaired = repair_report_evidence(
        report,
        allowed_nodes={},
        allowed_policy_ids=set(),
    )

    assert repaired.repository_observations == []
    assert repaired.evidence_appendix == []
    final_errors = validate_report_evidence(
        repaired,
        allowed_nodes={},
        allowed_policy_ids=set(),
    )
    assert final_errors == ["Supported statement has no supporting claim IDs"]


def test_invented_policy_ids_are_removed() -> None:
    provider = DeterministicReasoningProvider()
    case = ArchitectureCase(
        title="Policy evidence",
        problem_statement="Validate policy citations.",
        desired_outcome="Keep only retrieved guidance.",
    )
    context = GlobalContext(
        case_id=case.case_id,
        revision=1,
        title=case.title,
        problem=case.problem_statement,
        desired_outcome=case.desired_outcome,
        goals=[],
        constraints=[],
        future_changes=[],
        non_goals=[],
        confirmed_facts=[],
        assumptions=[],
    )
    alternatives = provider.generate_alternatives(context, [])
    scenarios = provider.evaluate_scenarios(context, alternatives, [])
    forces = provider.discover_design_forces(context)
    clusters = provider.cluster_design_forces(context, forces)
    report = provider.synthesize_recommendation(
        case, context, forces, clusters, [], alternatives, scenarios, []
    )
    invented = Claim(
        text="An invented policy applies.",
        classification=ClaimClassification.POLICY_GUIDANCE,
        policy_ids=["policy-invented"],
    )
    report = report.model_copy(
        update={
            "relevant_policies": [invented],
            "evidence_appendix": [*report.evidence_appendix, invented],
        }
    )

    errors = validate_report_evidence(
        report,
        allowed_nodes={},
        allowed_policy_ids=set(),
    )
    repaired = repair_report_evidence(
        report,
        allowed_nodes={},
        allowed_policy_ids=set(),
    )

    assert any("policy that was not retrieved" in error for error in errors)
    assert repaired.relevant_policies == []
    assert all(
        "policy-invented" not in claim.policy_ids
        for claim in repaired.evidence_appendix
    )
