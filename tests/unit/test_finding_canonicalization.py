from __future__ import annotations

from dataclasses import dataclass

import pytest
from tests.synthesis_support import synthesize_report

from archcompass.adapters.models.deterministic import DeterministicReasoningProvider
from archcompass.application.evidence import (
    canonicalize_report_findings,
    repair_report_evidence_with_history,
    validate_report_evidence,
)
from archcompass.domain.atlas import (
    AtlasMetricValue,
    AtlasNode,
    AtlasNodeEvidence,
    AtlasNodeSummary,
    NodeType,
    ObscuritySignal,
    SourceLocation,
)
from archcompass.domain.case import ArchitectureCase, Confidence, ConfidenceLevel
from archcompass.domain.consultation import (
    ArchitecturalFinding,
    AtlasEvidenceReference,
    Claim,
    ClaimClassification,
    ConcernAnalysis,
    ConcernCluster,
    FindingImportance,
    FocusedAnalysisPacket,
    GlobalContext,
    RecommendationReport,
)
from archcompass.domain.policy import (
    PolicyChunk,
    PolicyDocument,
    PolicyEvidenceSummary,
    PolicyScope,
    PolicySource,
    PolicyStrength,
    RetrievedPolicy,
)


@dataclass(frozen=True)
class _ClusterFixture:
    packet: FocusedAnalysisPacket
    analysis: ConcernAnalysis
    claim: Claim
    finding: ArchitecturalFinding
    atlas_node: AtlasNode


def _base_report() -> RecommendationReport:
    case = ArchitectureCase(
        title="Canonical finding evidence",
        problem_statement="Keep provider prose separate from application-owned evidence.",
        desired_outcome="Retain only exact focused-packet artifacts.",
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
    provider = DeterministicReasoningProvider()
    forces = provider.discover_design_forces(context)
    clusters = provider.cluster_design_forces(context, forces)
    alternatives = provider.generate_alternatives(context, [])
    scenarios = provider.evaluate_scenarios(context, alternatives, [])
    return synthesize_report(
        provider,
        case,
        context,
        forces,
        clusters,
        [],
        alternatives,
        scenarios,
        [],
    )


def _cluster_fixture(label: str, *, line: int) -> _ClusterFixture:
    cluster_id = f"cluster-{label}"
    node_id = f"node-{label}"
    policy_id = f"policy-{label}"
    path = f"src/{label}.py"
    location = SourceLocation(path=path, start_line=line, end_line=line + 5)
    node_summary = AtlasNodeSummary(
        node_id=node_id,
        qualified_name=f"package.{label}.work",
        node_type=NodeType.FUNCTION,
        path=path,
        location=location,
        is_public=True,
    )
    metric = AtlasMetricValue(
        node_id=node_id,
        metric="fan_out",
        value=line // 10,
        rank=1,
        definition="Count of outgoing static dependencies.",
        limitations="Static calls only.",
    )
    signal = ObscuritySignal(
        code="missing_docstring",
        message=f"{node_id} has no docstring.",
        node_id=node_id,
        location=location,
        definition="The analyzed symbol has no docstring.",
        limitations="Documentation may exist outside the symbol.",
    )
    policy = RetrievedPolicy(
        policy=PolicyDocument(
            id=policy_id,
            title=f"Policy {label.upper()}",
            scope=PolicyScope.GENERAL,
            strength=PolicyStrength.GUIDANCE,
            tags=["test"],
            source=PolicySource(author="ArchCompass tests"),
            body="Keep evidence local to the concern.",
            source_path=f"policies/{policy_id}.md",
            content_hash=f"hash-{policy_id}",
        ),
        chunks=[
            PolicyChunk(
                chunk_id=f"chunk-{label}",
                policy_id=policy_id,
                section="Guidance",
                ordinal=0,
                text="Keep evidence local to the concern.",
                content_hash=f"chunk-hash-{label}",
            )
        ],
        distance=0.1,
    )
    cluster = ConcernCluster(
        cluster_id=cluster_id,
        title=f"Concern {label.upper()}",
        rationale=f"Inspect concern {label.upper()}.",
        design_force_ids=[f"force-{label}"],
    )
    packet = FocusedAnalysisPacket(
        cluster=cluster,
        node_evidence=[
            AtlasNodeEvidence(
                node=node_summary,
                metrics=[metric],
                signals=[signal],
            )
        ],
        policies=[policy],
        uncertainty=["Runtime behavior was not observed."],
    )
    claim = Claim(
        claim_id=f"claim-{label}",
        text=f"{node_id} concentrates concern {label.upper()}.",
        classification=ClaimClassification.REPOSITORY_OBSERVATION,
        atlas_references=[
            AtlasEvidenceReference(
                node_id=node_id,
                location=location,
            )
        ],
        policy_ids=[policy_id],
    )
    analysis = ConcernAnalysis(
        cluster_id=cluster_id,
        concern=cluster.title,
        findings=[claim],
        implications=[f"Concern {label.upper()} can amplify changes."],
    )
    finding = ArchitecturalFinding(
        finding_id="FIND-099",
        title=cluster.title,
        summary=claim.text,
        concern_cluster_id=cluster_id,
        importance=FindingImportance.HIGH,
        importance_rationale="The focused evidence makes this concern material.",
        confidence=Confidence(
            level=ConfidenceLevel.HIGH,
            rationale="The finding is supported by located repository evidence.",
        ),
        consequence=analysis.implications[0],
        claim_ids=[claim.claim_id],
        atlas_node_ids=[node_id],
        policy_ids=[policy_id],
        affected_locations=[node_summary],
        metric_observations=[metric],
        obscurity_signals=[signal],
        recommended_response=f"Keep concern {label.upper()} local.",
        uncertainty=list(packet.uncertainty),
    )
    atlas_node = AtlasNode(
        atlas_id=node_id,
        path=path,
        symbol_name="work",
        qualified_name=node_summary.qualified_name,
        node_type=NodeType.FUNCTION,
        start_line=line,
        end_line=line + 5,
        is_public=True,
        parser_version="test-parser",
    )
    return _ClusterFixture(
        packet=packet,
        analysis=analysis,
        claim=claim,
        finding=finding,
        atlas_node=atlas_node,
    )


def _report_with_findings(
    fixtures: list[_ClusterFixture],
    findings: list[ArchitecturalFinding],
) -> RecommendationReport:
    report = _base_report()
    claims = [fixture.claim for fixture in fixtures]
    return report.model_copy(
        update={
            "findings": findings,
            "repository_observations": claims,
            "policy_evidence": [
                PolicyEvidenceSummary.from_retrieved(fixture.packet.policies[0])
                for fixture in fixtures
            ],
            "evidence_appendix": [*report.evidence_appendix, *claims],
        }
    )


def _tampered_finding(
    fixture: _ClusterFixture,
    evidence_field: str,
) -> ArchitecturalFinding:
    if evidence_field == "affected_locations":
        update: object = [
            fixture.finding.affected_locations[0].model_copy(
                update={
                    "path": "invented/location.py",
                    "location": SourceLocation(
                        path="invented/location.py",
                        start_line=900,
                        end_line=901,
                    ),
                }
            )
        ]
    elif evidence_field == "metric_observations":
        update = [
            fixture.finding.metric_observations[0].model_copy(
                update={
                    "value": 999_999,
                    "definition": "Invented metric definition.",
                }
            )
        ]
    elif evidence_field == "obscurity_signals":
        update = [
            fixture.finding.obscurity_signals[0].model_copy(
                update={
                    "code": "invented_signal",
                    "message": "Invented signal message.",
                }
            )
        ]
    else:
        assert evidence_field == "policy_ids"
        update = ["policy-invented"]
    return fixture.finding.model_copy(update={evidence_field: update})


@pytest.mark.parametrize(
    ("evidence_field", "validation_error"),
    [
        ("affected_locations", "locations do not match its focused packet"),
        ("metric_observations", "metrics do not match its focused packet"),
        ("obscurity_signals", "signals do not match its focused packet"),
        ("policy_ids", "policies do not match its focused packet"),
    ],
)
def test_finding_artifacts_are_restored_exactly_from_the_focused_packet(
    evidence_field: str,
    validation_error: str,
) -> None:
    fixture = _cluster_fixture("a", line=10)
    tampered = _tampered_finding(fixture, evidence_field)
    report = _report_with_findings([fixture], [tampered])

    outcome = canonicalize_report_findings(
        report,
        packets=[fixture.packet],
        analyses=[fixture.analysis],
    )
    pre_canonical_errors = validate_report_evidence(
        report,
        allowed_nodes={fixture.atlas_node.atlas_id: fixture.atlas_node},
        allowed_policy_ids={fixture.packet.policies[0].policy.id},
        finding_evidence_by_cluster=outcome.evidence_by_cluster,
    )

    assert any(validation_error in error for error in pre_canonical_errors)
    assert outcome.report.findings == [
        fixture.finding.model_copy(update={"finding_id": "FIND-001"})
    ]
    assert len(outcome.actions) == 1
    assert outcome.actions[0]["kind"] == "restored_canonical_finding_evidence"
    assert (
        outcome.actions[0]["model_output"][evidence_field]
        != outcome.actions[0]["canonical_input"][evidence_field]
    )
    assert validate_report_evidence(
        outcome.report,
        allowed_nodes={fixture.atlas_node.atlas_id: fixture.atlas_node},
        allowed_policy_ids={fixture.packet.policies[0].policy.id},
        finding_evidence_by_cluster=outcome.evidence_by_cluster,
    ) == []


def test_missing_finding_cluster_is_assigned_when_only_one_packet_exists() -> None:
    fixture = _cluster_fixture("a", line=10)
    finding = fixture.finding.model_copy(
        update={
            "finding_id": "FIND-001",
            "concern_cluster_id": None,
        }
    )
    report = _report_with_findings([fixture], [finding])

    outcome = canonicalize_report_findings(
        report,
        packets=[fixture.packet],
        analyses=[fixture.analysis],
    )

    assert outcome.report.findings == [
        fixture.finding.model_copy(update={"finding_id": "FIND-001"})
    ]
    assert outcome.actions == [
        {
            "kind": "assigned_single_concern_cluster_to_finding",
            "finding_id": "FIND-001",
            "concern_cluster_id": fixture.packet.cluster.cluster_id,
        }
    ]


def test_missing_finding_cluster_remains_invalid_when_assignment_is_ambiguous() -> None:
    first = _cluster_fixture("a", line=10)
    second = _cluster_fixture("b", line=20)
    finding = first.finding.model_copy(
        update={
            "finding_id": "FIND-001",
            "concern_cluster_id": None,
        }
    )
    report = _report_with_findings([first, second], [finding])

    outcome = canonicalize_report_findings(
        report,
        packets=[first.packet, second.packet],
        analyses=[first.analysis, second.analysis],
    )

    assert outcome.report.findings[0].concern_cluster_id is None
    assert all(
        action["kind"] != "assigned_single_concern_cluster_to_finding"
        for action in outcome.actions
    )


def test_cross_cluster_claim_is_removed_before_final_ordered_ids_are_assigned() -> None:
    first = _cluster_fixture("a", line=10)
    second = _cluster_fixture("b", line=20)
    mixed = second.finding.model_copy(
        update={
            "finding_id": "FIND-087",
            "claim_ids": [second.claim.claim_id, first.claim.claim_id],
        }
    )
    out_of_order = first.finding.model_copy(update={"finding_id": "FIND-042"})
    report = _report_with_findings([first, second], [mixed, out_of_order])
    packets = [first.packet, second.packet]
    analyses = [first.analysis, second.analysis]
    allowed_nodes = {
        first.atlas_node.atlas_id: first.atlas_node,
        second.atlas_node.atlas_id: second.atlas_node,
    }
    allowed_policy_ids = {
        first.packet.policies[0].policy.id,
        second.packet.policies[0].policy.id,
    }

    initial = canonicalize_report_findings(
        report,
        packets=packets,
        analyses=analyses,
    )
    initial_errors = validate_report_evidence(
        initial.report,
        allowed_nodes=allowed_nodes,
        allowed_policy_ids=allowed_policy_ids,
        finding_evidence_by_cluster=initial.evidence_by_cluster,
    )
    repaired = repair_report_evidence_with_history(
        initial.report,
        allowed_nodes=allowed_nodes,
        allowed_policy_ids=allowed_policy_ids,
        finding_evidence_by_cluster=initial.evidence_by_cluster,
    )
    final = canonicalize_report_findings(
        repaired.report,
        packets=packets,
        analyses=analyses,
    )

    assert any("outside concern cluster" in error for error in initial_errors)
    assert any("cross-cluster claims" in action for action in repaired.actions)
    assert [finding.finding_id for finding in final.report.findings] == [
        "FIND-001",
        "FIND-002",
    ]
    assert [
        (
            finding.concern_cluster_id,
            finding.claim_ids,
            finding.atlas_node_ids,
            finding.policy_ids,
        )
        for finding in final.report.findings
    ] == [
        ("cluster-b", ["claim-b"], ["node-b"], ["policy-b"]),
        ("cluster-a", ["claim-a"], ["node-a"], ["policy-a"]),
    ]
    assert validate_report_evidence(
        final.report,
        allowed_nodes=allowed_nodes,
        allowed_policy_ids=allowed_policy_ids,
        finding_evidence_by_cluster=final.evidence_by_cluster,
    ) == []
