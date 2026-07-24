from __future__ import annotations

import json
from typing import cast

import pytest
from pydantic import ValidationError

from archcompass.adapters.models.deterministic import DeterministicReasoningProvider
from archcompass.application.evidence import (
    repair_report_evidence_with_history,
    validate_report_evidence,
)
from archcompass.application.reporting import render_markdown
from archcompass.domain.atlas import AtlasNode, NodeType, SourceLocation
from archcompass.domain.case import ArchitectureCase, CaseStatement, StatementKind
from archcompass.domain.consultation import (
    AtlasEvidenceReference,
    Claim,
    ClaimClassification,
    ConcernCluster,
    ConsultationRun,
    ConsultationStatus,
    DesignForce,
    GlobalContext,
    RecommendationReport,
    cluster_partition_errors,
)
from archcompass.domain.policy import (
    PolicyConflict,
    PolicyEvidenceSummary,
    PolicyScope,
    PolicyStrength,
)


def _case() -> ArchitectureCase:
    return ArchitectureCase(
        title="Provider ownership",
        problem_statement="Provider capability knowledge leaks into orchestration.",
        desired_outcome="Give changing knowledge one owner.",
        expected_future_changes=["A second provider may be added."],
        confirmed_facts=[
            CaseStatement(
                id="fact-provider",
                text="One provider exists.",
                kind=StatementKind.FACT,
            )
        ],
    )


def _report() -> RecommendationReport:
    case = _case()
    context = GlobalContext(
        case_id=case.case_id,
        revision=1,
        title=case.title,
        problem=case.problem_statement,
        desired_outcome=case.desired_outcome,
        goals=[],
        constraints=[],
        future_changes=case.expected_future_changes,
        non_goals=[],
        confirmed_facts=["One provider exists."],
        assumptions=[],
    )
    provider = DeterministicReasoningProvider()
    forces = provider.discover_design_forces(context)
    clusters = provider.cluster_design_forces(context, forces)
    alternatives = provider.generate_alternatives(context, [])
    scenarios = provider.evaluate_scenarios(context, alternatives, [])
    return provider.synthesize_recommendation(
        case,
        context,
        forces,
        clusters,
        [],
        alternatives,
        scenarios,
        [],
    )


def test_clusters_must_be_an_exact_force_partition() -> None:
    forces = [
        DesignForce(
            force_id="force-a",
            title="A",
            description="A force",
            importance="high",
        ),
        DesignForce(
            force_id="force-b",
            title="B",
            description="Another force",
            importance="high",
        ),
    ]
    clusters = [
        ConcernCluster(
            cluster_id="cluster-a",
            title="Cluster",
            rationale="Group related forces",
            design_force_ids=["force-a", "force-invented"],
        )
    ]

    errors = cluster_partition_errors(forces, clusters)

    assert any("unknown" in error for error in errors)
    assert any("omit" in error for error in errors)


def test_case_statement_collections_enforce_their_kind() -> None:
    with pytest.raises(ValidationError, match="wrong kind"):
        ArchitectureCase(
            title="Invalid",
            problem_statement="A fact is misclassified.",
            desired_outcome="Reject it.",
            confirmed_facts=[
                CaseStatement(
                    text="This is not an assumption.",
                    kind=StatementKind.ASSUMPTION,
                )
            ],
        )


def test_schema_v1_report_strings_upgrade_losslessly() -> None:
    current = _report()
    payload = current.model_dump(mode="json")
    payload.pop("schema_version")
    payload.pop("disposition")
    for field in (
        "decision_summary",
        "recommended_architecture",
        "change_amplification_analysis",
    ):
        payload[field] = cast(dict[str, object], payload[field])["text"]
    for field in (
        "responsibility_allocation",
        "conceptual_interfaces",
        "trade_offs",
        "implementation_sequence",
        "reversal_conditions",
        "revisit_triggers",
    ):
        payload[field] = [
            cast(dict[str, object], item)["text"] for item in cast(list[object], payload[field])
        ]
    adr = cast(dict[str, object], payload["adr"])
    adr["decision"] = cast(dict[str, object], adr["decision"])["text"]
    adr["consequences"] = [
        cast(dict[str, object], item)["text"] for item in cast(list[object], adr["consequences"])
    ]
    for scenario in cast(list[dict[str, object]], payload["scenario_analysis"]):
        results = cast(dict[str, str], scenario["alternative_results"])
        scenario["alternative_results"] = list(results.values())
    payload.pop("policy_evidence")
    payload.pop("policy_conflicts")

    loaded = RecommendationReport.model_validate_json(json.dumps(payload))

    assert loaded.schema_version == 2
    assert loaded.decision_summary.text == current.decision_summary.text
    assert loaded.decision_summary.legacy is True
    assert set(loaded.scenario_analysis[0].alternative_results) == {
        item.id for item in loaded.alternatives_considered
    }


def test_schema_v2_report_rejects_unstructured_substantive_prose() -> None:
    payload = _report().model_dump(mode="json")
    payload["decision_summary"] = "An unclassified decision"

    with pytest.raises(ValidationError, match="SupportedStatement"):
        RecommendationReport.model_validate(payload)


def test_supported_statement_schema_requires_non_empty_support_ids() -> None:
    schema = RecommendationReport.model_json_schema()
    supported_statement = schema["$defs"]["SupportedStatement"]

    assert "supporting_claim_ids" in supported_statement["required"]
    assert supported_statement["properties"]["supporting_claim_ids"]["minItems"] == 1


def test_scenarios_require_exact_alternative_id_coverage() -> None:
    payload = _report().model_dump(mode="json")
    scenario = cast(list[dict[str, object]], payload["scenario_analysis"])[0]
    results = cast(dict[str, str], scenario["alternative_results"])
    results.pop(next(iter(results)))

    with pytest.raises(ValidationError, match="coverage mismatch"):
        RecommendationReport.model_validate(payload)


def test_report_requires_canonical_evidence_for_every_cited_policy() -> None:
    report = _report()
    policy_claim = Claim(
        claim_id="claim-policy",
        text="A retrieved policy applies.",
        classification=ClaimClassification.POLICY_GUIDANCE,
        policy_ids=["policy-a"],
    )
    payload = report.model_copy(
        update={
            "relevant_policies": [policy_claim],
            "evidence_appendix": [*report.evidence_appendix, policy_claim],
        }
    ).model_dump(mode="json")

    with pytest.raises(ValidationError, match="canonical policy evidence"):
        RecommendationReport.model_validate(payload)


def test_invalid_repository_location_removes_the_whole_observation() -> None:
    report = _report()
    node = AtlasNode(
        atlas_id="node-provider",
        path="provider.py",
        symbol_name="Provider",
        qualified_name="provider.Provider",
        node_type=NodeType.CLASS,
        start_line=10,
        end_line=20,
        parser_version="test",
    )
    observation = Claim(
        claim_id="claim-invalid-location",
        text="Provider knowledge lives here.",
        classification=ClaimClassification.REPOSITORY_OBSERVATION,
        atlas_references=[
            AtlasEvidenceReference(
                node_id=node.atlas_id,
                location=SourceLocation(
                    path="other.py",
                    start_line=10,
                    end_line=20,
                ),
            )
        ],
    )
    report = report.model_copy(
        update={
            "repository_observations": [observation],
            "evidence_appendix": [*report.evidence_appendix, observation],
        }
    )
    errors = validate_report_evidence(
        report,
        allowed_nodes={node.atlas_id: node},
        allowed_policy_ids=set(),
    )

    repaired = repair_report_evidence_with_history(
        report,
        allowed_nodes={node.atlas_id: node},
        allowed_policy_ids=set(),
    )

    assert any("source path" in error for error in errors)
    assert repaired.report.repository_observations == []
    assert any("Removed repository observation" in item for item in repaired.actions)
    assert all(
        reference.location is not None
        for claim in repaired.report.evidence_appendix
        for reference in claim.atlas_references
    )


def test_markdown_preserves_scenario_and_support_metadata() -> None:
    report = _report()
    repository_claim = Claim(
        claim_id="claim-repository",
        text="Provider knowledge is duplicated.",
        classification=ClaimClassification.REPOSITORY_OBSERVATION,
        atlas_references=[
            AtlasEvidenceReference(
                node_id="node-provider",
                location=SourceLocation(
                    path="provider.py",
                    start_line=3,
                    end_line=8,
                ),
            )
        ],
    )
    policy_claims = [
        Claim(
            claim_id=f"claim-{policy_id}",
            text=f"{policy_id} applies.",
            classification=ClaimClassification.POLICY_GUIDANCE,
            policy_ids=[policy_id],
        )
        for policy_id in ("policy-a", "policy-b")
    ]
    policy_evidence = [
        PolicyEvidenceSummary(
            id=policy_id,
            title=f"Policy {policy_id[-1].upper()}",
            scope=PolicyScope.ORGANISATION,
            strength=PolicyStrength.PREFERRED,
            matched_sections=["Guidance", "Exceptions"],
        )
        for policy_id in ("policy-a", "policy-b")
    ]
    conflict = PolicyConflict(
        policy_ids=["policy-a", "policy-b"],
        explanation="The policies recommend different ownership boundaries.",
        reconciliation="Apply the narrower boundary in this repository.",
    )
    report = report.model_copy(
        update={
            "repository_observations": [repository_claim],
            "relevant_policies": policy_claims,
            "policy_evidence": policy_evidence,
            "policy_conflicts": [conflict],
            "evidence_appendix": [
                *report.evidence_appendix,
                repository_claim,
                *policy_claims,
            ],
        }
    )
    markdown = render_markdown(report)
    scenario = report.scenario_analysis[0]

    assert scenario.assumptions[0] in markdown
    assert all(alternative_id in markdown for alternative_id in scenario.alternative_results)
    assert report.decision_summary.supporting_claim_ids[0] in markdown
    assert str(report.decision_summary.classification) in markdown
    assert "provider.py:3-8" in markdown
    assert str(ClaimClassification.REPOSITORY_OBSERVATION) in markdown
    assert "Policy A" in markdown
    assert "scope=`organisation`" in markdown
    assert "strength=`preferred`" in markdown
    assert "Guidance, Exceptions" in markdown
    assert conflict.explanation in markdown
    assert conflict.reconciliation in markdown


def test_failed_run_requires_auditable_failure_details() -> None:
    with pytest.raises(ValidationError, match="failure stage"):
        ConsultationRun(
            schema_version=2,
            status=ConsultationStatus.FAILED,
            case_id="case-test",
            input_case_revision=1,
            reasoning_model="fake:test",
            embedding_model="fake:test",
            config_hash="cfg-test",
        )


def test_schema_v1_run_json_loads_with_new_audit_defaults() -> None:
    report = _report()
    current = ConsultationRun(
        schema_version=2,
        status=ConsultationStatus.SUCCEEDED,
        case_id="case-test",
        input_case_revision=1,
        result_case_revision=2,
        reasoning_model="fake:test",
        embedding_model="fake:test",
        config_hash="cfg-test",
        report=report,
        markdown_report=render_markdown(report),
    )
    payload = current.model_dump(mode="json")
    payload.pop("schema_version")
    payload.pop("clusters")
    payload.pop("concern_analyses")
    payload.pop("stage_timings")
    payload.pop("failure_stage")
    payload.pop("sanitized_errors")
    payload["validation_errors"] = payload.pop("final_validation_errors")
    payload["repair_attempted"] = False
    payload.pop("initial_validation_errors")
    payload.pop("repair_actions")

    loaded = ConsultationRun.model_validate_json(json.dumps(payload))

    assert loaded.schema_version == 2
    assert loaded.clusters == []
    assert loaded.concern_analyses == []
    assert loaded.stage_timings == {}
    assert loaded.validation_errors == []

    payload["schema_version"] = 1
    explicit_v1 = ConsultationRun.model_validate_json(json.dumps(payload))
    assert explicit_v1.schema_version == 2
    assert explicit_v1.clusters == []
