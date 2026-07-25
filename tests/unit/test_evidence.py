from tests.synthesis_support import synthesize_report

from archcompass.adapters.models.deterministic import DeterministicReasoningProvider
from archcompass.application.evidence import (
    repair_report_evidence_with_history,
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
    report = synthesize_report(
        provider,
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

    repaired = repair_report_evidence_with_history(
        report,
        allowed_nodes={},
        allowed_policy_ids=set(),
    ).report

    assert repaired.repository_observations == []
    assert repaired.evidence_appendix == []
    final_errors = validate_report_evidence(
        repaired,
        allowed_nodes={},
        allowed_policy_ids=set(),
    )
    assert final_errors == [
        "Supported statement has no supporting claim IDs",
        "A recommendation report must contain architectural findings",
    ]


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
    report = synthesize_report(
        provider,
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
    repaired = repair_report_evidence_with_history(
        report,
        allowed_nodes={},
        allowed_policy_ids=set(),
    ).report

    assert any("policy that was not retrieved" in error for error in errors)
    assert repaired.relevant_policies == []
    assert all(
        "policy-invented" not in claim.policy_ids
        for claim in repaired.evidence_appendix
    )


def test_duplicate_claim_id_is_reassigned_only_when_support_is_unambiguous() -> None:
    provider = DeterministicReasoningProvider()
    case = ArchitectureCase(
        title="Duplicate claim identity",
        problem_statement="Validate duplicate claim repair.",
        desired_outcome="Preserve unambiguous evidence support.",
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
    report = synthesize_report(
        provider,
        case, context, forces, clusters, [], alternatives, scenarios, []
    )
    assumption = Claim(
        claim_id="claim-reused",
        text="A future provider may be added.",
        classification=ClaimClassification.SCENARIO_ASSUMPTION,
    )
    policy = Claim(
        claim_id="claim-reused",
        text="Keep one conceptual change local.",
        classification=ClaimClassification.POLICY_GUIDANCE,
        policy_ids=["policy-locality"],
    )
    decision = report.decision_summary.model_copy(
        update={
            "classification": ClaimClassification.POLICY_GUIDANCE,
            "supporting_claim_ids": ["claim-reused"],
        }
    )
    report = report.model_copy(
        update={
            "decision_summary": decision,
            "assumptions_and_unresolved_questions": [assumption],
            "relevant_policies": [policy],
            "evidence_appendix": [
                *report.evidence_appendix,
                assumption,
                policy,
            ],
        }
    )

    outcome = repair_report_evidence_with_history(
        report,
        allowed_nodes={},
        allowed_policy_ids={"policy-locality"},
    )

    repaired_assumption = outcome.report.assumptions_and_unresolved_questions[0]
    repaired_policy = outcome.report.relevant_policies[0]
    assert repaired_assumption.claim_id.startswith("claim_")
    assert repaired_assumption.claim_id != "claim-reused"
    assert repaired_policy.claim_id == "claim-reused"
    assert outcome.report.decision_summary.supporting_claim_ids == ["claim-reused"]
    assert any(
        "Reassigned duplicate claim ID claim-reused" in action
        for action in outcome.actions
    )
    assert validate_report_evidence(
        outcome.report,
        allowed_nodes={},
        allowed_policy_ids={"policy-locality"},
    ) == []


def test_ambiguous_duplicate_claim_id_remains_invalid() -> None:
    provider = DeterministicReasoningProvider()
    case = ArchitectureCase(
        title="Ambiguous claim identity",
        problem_statement="Reject ambiguous duplicate claim repair.",
        desired_outcome="Do not guess which evidence was intended.",
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
    report = synthesize_report(
        provider,
        case, context, forces, clusters, [], alternatives, scenarios, []
    )
    first = Claim(
        claim_id="claim-ambiguous",
        text="First policy interpretation.",
        classification=ClaimClassification.POLICY_GUIDANCE,
        policy_ids=["policy-locality"],
    )
    second = first.model_copy(update={"text": "Second policy interpretation."})
    report = report.model_copy(
        update={
            "decision_summary": report.decision_summary.model_copy(
                update={
                    "classification": ClaimClassification.POLICY_GUIDANCE,
                    "supporting_claim_ids": ["claim-ambiguous"],
                }
            ),
            "relevant_policies": [first, second],
            "evidence_appendix": [
                *report.evidence_appendix,
                first,
                second,
            ],
        }
    )

    outcome = repair_report_evidence_with_history(
        report,
        allowed_nodes={},
        allowed_policy_ids={"policy-locality"},
    )

    assert not any("Reassigned duplicate claim ID" in action for action in outcome.actions)
    assert any(
        "Claim ID claim-ambiguous is reused for different claims" in error
        for error in validate_report_evidence(
            outcome.report,
            allowed_nodes={},
            allowed_policy_ids={"policy-locality"},
        )
    )
