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
    report = provider.synthesize_recommendation(
        case, context, [], alternatives, scenarios, []
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
    errors = validate_report_evidence(
        report, allowed_nodes={}, allowed_policy_ids=set()
    )
    assert any("unknown atlas node" in error for error in errors)

    repaired = repair_report_evidence(
        report,
        allowed_nodes={},
        allowed_policy_ids=set(),
    )

    assert repaired.repository_observations == []
    assert repaired.evidence_appendix == []
    assert validate_report_evidence(
        repaired,
        allowed_nodes={},
        allowed_policy_ids=set(),
    ) == []
