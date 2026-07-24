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
    cluster_partition_diagnostics,
    cluster_partition_errors,
)
from archcompass.domain.diagnostics import FailureDiagnostic, FailureDiagnosticCode
from archcompass.domain.policy import (
    PolicyConflict,
    PolicyEvidenceSummary,
    PolicyScope,
    PolicyStrength,
)
from archcompass.workflows.consultation import (
    POLICY_QUERY_CHARACTER_BUDGET,
    ConsultationWorkflow,
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

    diagnostics = cluster_partition_diagnostics(forces, clusters)

    assert [item.code for item in diagnostics] == [
        FailureDiagnosticCode.UNKNOWN_FORCE_REFERENCES,
        FailureDiagnosticCode.MISSING_FORCE_REFERENCES,
    ]
    assert diagnostics[0].count == 1
    assert diagnostics[1].force_handles == ["F2"]
    serialized = json.dumps(
        [item.model_dump(mode="json") for item in diagnostics]
    )
    assert "force-a" not in serialized
    assert "force-b" not in serialized
    assert "force-invented" not in serialized


def test_failure_diagnostics_reject_internal_ids_and_model_prose() -> None:
    with pytest.raises(ValidationError, match="string_pattern_mismatch"):
        FailureDiagnostic(
            code=FailureDiagnosticCode.MISSING_FORCE_REFERENCES,
            force_handles=["force_internal-id /private/path"],
        )


def test_deterministic_reasoner_partitions_generic_forces_and_focuses_queries() -> None:
    forces = [
        DesignForce(
            force_id="force-ownership",
            title="Responsibility ownership",
            description="Give changing knowledge one owner.",
            importance="high",
        ),
        DesignForce(
            force_id="force-change",
            title="Evolution pressure",
            description="Contain credible variation and growth.",
            importance="high",
        ),
        DesignForce(
            force_id="force-lifecycle",
            title="Resource lifecycle",
            description="Make uncertain resource lifetime constraints explicit.",
            importance="medium",
        ),
        DesignForce(
            force_id="force-uncertainty",
            title="Evidence uncertainty",
            description="Keep unknown repository details explicit.",
            importance="medium",
        ),
    ]
    context = GlobalContext(
        case_id="case-routing",
        revision=1,
        title="Generic routing",
        problem="Several architectural forces need focused investigation.",
        desired_outcome="Investigate each concern independently.",
        goals=[],
        constraints=[],
        future_changes=[],
        non_goals=[],
        confirmed_facts=[],
        assumptions=[],
        atlas_summary="Repository evidence is available.",
    )
    provider = DeterministicReasoningProvider()

    clusters = provider.cluster_design_forces(context, forces)
    plans = provider.plan_atlas_queries(
        context,
        forces,
        clusters,
        iteration=1,
        prior_results={},
    )

    assert [cluster.title for cluster in clusters] == [
        "Responsibility ownership",
        "Lifecycle and operations",
        "Change locality and evolution",
        "Evidence uncertainty",
    ]
    assert sorted(
        force_id
        for cluster in clusters
        for force_id in cluster.design_force_ids
    ) == sorted(force.force_id for force in forces)
    assert [plan.plan.queries[0].model_dump()["metric"] for plan in plans] == [
        "dependency.fan_in",
        "local.branch_count",
        "dependency.fan_out",
        "cognitive_scope.dependency_neighbourhood_modules",
    ]
    assert provider.model_identity == "fake:deterministic-architecture-v3"
    assert provider.prompt_identity("cluster_design_forces") == "cluster-design-forces:v2"
    assert provider.prompt_identity("plan_atlas_queries") == (
        "plan-cluster-atlas-queries:v4"
    )


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

    assert loaded.schema_version == 3
    assert loaded.findings[0].finding_id == "FIND-001"
    assert loaded.decision_summary.text == current.decision_summary.text
    assert loaded.decision_summary.legacy is True
    assert set(loaded.scenario_analysis[0].alternative_results) == {
        item.id for item in loaded.alternatives_considered
    }


def test_schema_v3_report_rejects_unstructured_substantive_prose() -> None:
    payload = _report().model_dump(mode="json")
    payload["decision_summary"] = "An unclassified decision"

    with pytest.raises(ValidationError, match="SupportedStatement"):
        RecommendationReport.model_validate(payload)


def test_schema_v2_report_upgrades_to_uncertain_compatibility_finding() -> None:
    payload = _report().model_dump(mode="json")
    payload["schema_version"] = 2
    payload.pop("findings")

    loaded = RecommendationReport.model_validate(payload)

    assert loaded.schema_version == 3
    assert [item.finding_id for item in loaded.findings] == ["FIND-001"]
    assert "compatibility" in loaded.findings[0].uncertainty[0].casefold()


def test_schema_v3_report_requires_authored_findings() -> None:
    payload = _report().model_dump(mode="json")
    payload.pop("findings")

    with pytest.raises(ValidationError, match="findings"):
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


def test_source_location_rejects_a_reversed_span() -> None:
    with pytest.raises(ValidationError, match="end line must not precede"):
        SourceLocation(path="provider.py", start_line=20, end_line=10)


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

    assert "## 6. Findings" in markdown
    assert "FIND-001" in markdown
    assert "Importance rationale" in markdown
    assert "Recommended response" in markdown
    assert "Uncertainty" in markdown
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


def test_greenfield_policy_query_contains_case_intent_and_is_bounded() -> None:
    case = ArchitectureCase(
        title="Report questions",
        problem_statement="Add a hosted reasoning provider for report follow-up questions.",
        desired_outcome="Preserve evidence selection and answer semantics when providers switch.",
        functional_requirements=["Users can ask questions about persisted findings."],
        expected_future_changes=["More model providers will be introduced."],
    )
    force = DesignForce(
        force_id="force-provider",
        title="Provider-neutral evidence",
        description="Keep authoritative report evidence stable across providers.",
        importance="high",
    )
    cluster = ConcernCluster(
        cluster_id="cluster-provider",
        title="Responsibility ownership",
        rationale="Identify the owner of model context selection.",
        design_force_ids=[force.force_id],
    )

    query = ConsultationWorkflow._policy_retrieval_query(
        case=case,
        cluster=cluster,
        force_lookup={force.force_id: force},
        atlas=None,
        selected_node_ids=[],
    )

    assert "hosted reasoning provider" in query
    assert "Preserve evidence selection" in query
    assert "Users can ask questions about persisted findings" in query
    assert len(query) <= POLICY_QUERY_CHARACTER_BUDGET


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

    assert loaded.schema_version == 3
    assert loaded.clusters == []
    assert loaded.concern_analyses == []
    assert loaded.stage_timings == {}
    assert loaded.validation_errors == []

    payload["schema_version"] = 1
    explicit_v1 = ConsultationRun.model_validate_json(json.dumps(payload))
    assert explicit_v1.schema_version == 3
    assert explicit_v1.clusters == []
