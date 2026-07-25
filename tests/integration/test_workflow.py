from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from archcompass.adapters.models.deterministic import DeterministicReasoningProvider
from archcompass.application.evidence import canonicalize_report_findings
from archcompass.bootstrap import BUNDLED_POLICY_SOURCE, build_runtime
from archcompass.domain.atlas import (
    AtlasQueryPlan,
    NodeDetailsQuery,
    RepositorySummaryQuery,
    SearchNodesQuery,
    SourceLocation,
)
from archcompass.domain.case import (
    ArchitectureCase,
    CaseStatement,
    RepositoryReference,
    StatementKind,
)
from archcompass.domain.consultation import (
    AtlasEvidenceReference,
    Claim,
    ClaimClassification,
    ClusterQueryPlan,
    ConcernAnalysis,
    ConcernCluster,
    ConsultationFailureStage,
    ConsultationStatus,
    DesignForce,
)
from archcompass.domain.diagnostics import FailureDiagnosticCode
from archcompass.domain.errors import (
    ClusterPartitionError,
    EvidenceReferenceError,
    ModelOutputValidationError,
    PolicyFormatError,
)
from archcompass.domain.policy import PolicyApplicabilityContext
from archcompass.workflows.consultation import ConsultationWorkflow


def _case(*, brownfield: bool = False) -> ArchitectureCase:
    return ArchitectureCase(
        title="Brownfield provider leakage" if brownfield else "Greenfield audiobook",
        problem_statement=(
            "Qwen-specific built-in voice logic is spread across modules."
            if brownfield
            else "Build an audiobook system with Qwen TTS and possible hosted providers."
        ),
        desired_outcome="Choose stable responsibilities without a universal plugin platform.",
        functional_requirements=["Book ingestion", "Narration", "Voice cloning"],
        quality_attributes=["Long-running resumable jobs"],
        technical_constraints=["One local GPU"],
        expected_future_changes=["Hosted providers may be added later"],
        confirmed_facts=[
            CaseStatement(
                text="Qwen is the initial provider",
                kind=StatementKind.FACT,
            )
        ],
    )


def test_analysis_claim_ids_are_canonicalized_before_synthesis() -> None:
    analyses = [
        ConcernAnalysis(
            cluster_id=f"cluster-{ordinal}",
            concern=f"Concern {ordinal}",
            findings=[
                Claim(
                    claim_id="none",
                    text=f"Distinct claim {ordinal}.",
                    classification=ClaimClassification.ADVISOR_INFERENCE,
                )
            ],
            implications=[f"Implication {ordinal}."],
        )
        for ordinal in range(1, 3)
    ]
    metadata: dict[str, object] = {"model_output_repairs": []}

    canonical = ConsultationWorkflow._canonicalize_analysis_claim_ids(
        analyses,
        metadata=metadata,
    )
    repeated = ConsultationWorkflow._canonicalize_analysis_claim_ids(
        analyses,
        metadata={"model_output_repairs": []},
    )

    claim_ids = [item.findings[0].claim_id for item in canonical]
    assert len(set(claim_ids)) == 2
    assert all(item.startswith("claim_") for item in claim_ids)
    assert claim_ids == [item.findings[0].claim_id for item in repeated]
    assert all(
        repair["kind"] == "reassigned_ambiguous_analysis_claim_id"
        for repair in metadata["model_output_repairs"]
    )


def test_greenfield_workflow_never_requires_atlas(runtime) -> None:
    assert runtime.policy_store.current_version() is None
    revision = runtime.case_service.create(_case())
    run = runtime.workflow.advise(revision.case_id)
    assert run.status == ConsultationStatus.SUCCEEDED
    assert run.atlas_version_id is None
    assert run.query_plans == []
    assert run.clusters
    assert len(run.concern_analyses) == len(run.clusters)
    assert [cluster.title for cluster in run.clusters] == [
        "Responsibility ownership",
        "Change locality and evolution",
        "Evidence uncertainty",
    ]
    assert "plan-cluster-atlas-queries:v4" not in run.prompt_identities
    assert run.stage_timings["discover_design_forces"] >= 0
    assert run.policy_index_version_id is not None
    assert run.execution_metadata["retrieved_policies"] == sum(
        len(packet.policies) for packet in run.focused_packets
    )
    assert run.execution_metadata["retrieved_policies"] == 18
    assert run.report is not None
    assert [item.finding_id for item in run.report.findings] == [
        f"FIND-{ordinal:03d}"
        for ordinal in range(1, len(run.report.findings) + 1)
    ]
    assert "provider" in run.report.recommended_architecture.text.casefold()
    assert runtime.case_service.show(revision.case_id).revision == 2


def test_multiple_clusters_keep_policy_retrieval_and_analysis_isolated(
    runtime,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class TwoClusterReasoner(DeterministicReasoningProvider):
        def cluster_design_forces(self, context, forces):
            del context
            return [
                ConcernCluster(
                    cluster_id="cluster-ownership",
                    title="Responsibility ownership",
                    rationale="Investigate ownership policies.",
                    design_force_ids=[forces[0].force_id],
                ),
                ConcernCluster(
                    cluster_id="cluster-change",
                    title="Change and variation",
                    rationale="Investigate change-locality policies.",
                    design_force_ids=[force.force_id for force in forces[1:]],
                ),
            ]

    class PartitioningRetriever:
        def __init__(self):
            self.queries: list[str] = []
            self.candidates = None

        def retrieve(
            self,
            query,
            *,
            top_k,
            version_id=None,
            max_sections_per_policy=None,
            applicability=None,
        ):
            self.queries.append(query)
            if self.candidates is None:
                self.candidates = runtime.policy_store.retrieve(
                    "bounded policy isolation fixture",
                    top_k=top_k * 2,
                    version_id=version_id,
                    max_sections_per_policy=max_sections_per_policy,
                    applicability=applicability,
                )
            partition = (len(self.queries) - 1) % 2
            return self.candidates[partition::2][:top_k]

    retriever = PartitioningRetriever()
    monkeypatch.setattr(runtime.workflow, "_reasoning", TwoClusterReasoner())
    monkeypatch.setattr(runtime.workflow, "_policies", retriever)
    revision = runtime.case_service.create(_case())

    run = runtime.workflow.advise(revision.case_id)

    assert len(run.clusters) == 2
    assert len(run.focused_packets) == len(run.concern_analyses) == 2
    assert len(retriever.queries) == 2
    assert retriever.queries[0] != retriever.queries[1]
    policy_sets = [{item.policy.id for item in packet.policies} for packet in run.focused_packets]
    assert policy_sets[0]
    assert policy_sets[1]
    assert policy_sets[0].isdisjoint(policy_sets[1])
    for packet, analysis in zip(
        run.focused_packets,
        run.concern_analyses,
        strict=True,
    ):
        cited = {policy_id for finding in analysis.findings for policy_id in finding.policy_ids}
        assert cited <= {item.policy.id for item in packet.policies}


def test_brownfield_workflow_uses_focused_packets_not_raw_atlas(
    runtime,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured_contexts = []

    class CapturingReasoner(DeterministicReasoningProvider):
        def discover_design_forces(self, context):
            captured_contexts.append(context)
            return super().discover_design_forces(context)

    monkeypatch.setattr(runtime.workflow, "_reasoning", CapturingReasoner())
    atlas = runtime.analyzer.analyze(Path("eval/cases/provider-leakage/repository").resolve())
    runtime.atlas_repository.save(atlas)
    revision = runtime.case_service.create(_case(brownfield=True))
    run = runtime.workflow.advise(
        revision.case_id, atlas_version_id=atlas.version.version_id
    )
    assert run.status == ConsultationStatus.SUCCEEDED
    assert run.focused_packets
    assert all(packet.node_summaries for packet in run.focused_packets)
    assert captured_contexts[0].atlas_overview is not None
    assert captured_contexts[0].atlas_overview.hotspots
    assert all(
        evidence.reasons
        and evidence.metrics
        and all(metric.definition for metric in evidence.metrics)
        for packet in run.focused_packets
        for evidence in packet.node_evidence
    )
    assert any(
        relationship.source.qualified_name and relationship.target.qualified_name
        for packet in run.focused_packets
        for relationship in packet.relationship_evidence
    )
    serialized = run.model_dump_json()
    assert '"nodes":' not in serialized
    assert run.report is not None
    assert run.report.repository_observations
    expected_policy_ids = {
        policy_id
        for claim in [
            *run.report.relevant_policies,
            *run.report.evidence_appendix,
        ]
        for policy_id in claim.policy_ids
    }
    expected_policy_ids.update(item.id for item in run.report.policy_evidence)
    expected_policy_ids.update(
        policy_id
        for conflict in [
            *run.report.policy_conflicts,
            *[
                conflict
                for analysis in run.concern_analyses
                for conflict in analysis.policy_conflicts
            ],
        ]
        for policy_id in conflict.policy_ids
    )
    updated = runtime.case_service.show(revision.case_id).snapshot
    assert set(updated.referenced_policy_ids) == expected_policy_ids


def test_finding_evidence_is_projected_exactly_from_its_focused_packet(
    runtime,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    invented_value = 987_654

    class InventedFindingEvidenceReasoner(DeterministicReasoningProvider):
        def synthesize_recommendation(
            self,
            case,
            context,
            forces,
            clusters,
            analyses,
            alternatives,
            scenarios,
            packets,
        ):
            report = super().synthesize_recommendation(
                case,
                context,
                forces,
                clusters,
                analyses,
                alternatives,
                scenarios,
                packets,
            )
            target_index = next(
                index
                for index, finding in enumerate(report.findings)
                if finding.metric_observations
            )
            target = report.findings[target_index]
            invented_metric = target.metric_observations[0].model_copy(
                update={"value": invented_value}
            )
            findings = list(report.findings)
            findings[target_index] = target.model_copy(
                update={
                    "metric_observations": [
                        invented_metric,
                        *target.metric_observations[1:],
                    ]
                }
            )
            return report.model_copy(update={"findings": findings})

    monkeypatch.setattr(
        runtime.workflow,
        "_reasoning",
        InventedFindingEvidenceReasoner(),
    )
    atlas = runtime.analyzer.analyze(
        Path("eval/cases/provider-leakage/repository").resolve()
    )
    runtime.atlas_repository.save(atlas)
    revision = runtime.case_service.create(_case(brownfield=True))

    run = runtime.workflow.advise(
        revision.case_id, atlas_version_id=atlas.version.version_id
    )

    assert run.report is not None
    assert all(
        metric.value != invented_value
        for finding in run.report.findings
        for metric in finding.metric_observations
    )
    canonical = canonicalize_report_findings(
        run.report,
        packets=run.focused_packets,
        analyses=run.concern_analyses,
    )
    assert canonical.report == run.report
    assert canonical.actions == []
    repairs = [
        repair
        for repair in run.execution_metadata["model_output_repairs"]
        if repair["kind"] == "restored_canonical_finding_evidence"
    ]
    assert any(
        any(
            metric["value"] == invented_value
            for metric in repair["model_output"]["metric_observations"]
        )
        for repair in repairs
    )


def test_cross_cluster_finding_claim_is_removed_by_the_single_repair(
    runtime,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class CrossClusterFindingReasoner(DeterministicReasoningProvider):
        def synthesize_recommendation(
            self,
            case,
            context,
            forces,
            clusters,
            analyses,
            alternatives,
            scenarios,
            packets,
        ):
            report = super().synthesize_recommendation(
                case,
                context,
                forces,
                clusters,
                analyses,
                alternatives,
                scenarios,
                packets,
            )
            first, second, *remaining = report.findings
            mixed = first.model_copy(
                update={"claim_ids": [*first.claim_ids, second.claim_ids[0]]}
            )
            return report.model_copy(update={"findings": [mixed, second, *remaining]})

    monkeypatch.setattr(
        runtime.workflow,
        "_reasoning",
        CrossClusterFindingReasoner(),
    )
    revision = runtime.case_service.create(_case())

    run = runtime.workflow.advise(revision.case_id)

    assert run.report is not None
    assert any("outside concern cluster" in error for error in run.initial_validation_errors)
    assert any(
        "cross-cluster claims" in action for action in run.repair_actions
    )
    assert {
        finding.concern_cluster_id for finding in run.report.findings
    } == {cluster.cluster_id for cluster in run.clusters}


def test_brownfield_preflight_includes_repository_policies(
    runtime,
    tmp_path: Path,
) -> None:
    repository = tmp_path / "repository"
    shutil.copytree(Path("eval/cases/provider-leakage/repository"), repository)
    local_policies = repository / ".archcompass" / "policies"
    local_policies.mkdir(parents=True)
    bundled = (BUNDLED_POLICY_SOURCE / "contain-dependencies.md").read_text(encoding="utf-8")
    (local_policies / "repository-dependency-policy.md").write_text(
        bundled.replace(
            "id: contain-dependencies",
            "id: repository-dependency-policy",
            1,
        ).replace("scope: general", "scope: repository", 1),
        encoding="utf-8",
    )
    atlas = runtime.analyzer.analyze(repository)
    runtime.atlas_repository.save(atlas)
    revision = runtime.case_service.create(_case(brownfield=True))

    run = runtime.workflow.advise(
        revision.case_id, atlas_version_id=atlas.version.version_id
    )

    assert run.policy_index_version_id is not None
    policies = runtime.policy_store.list_policies(run.policy_index_version_id)
    assert len(policies) == len(tuple(BUNDLED_POLICY_SOURCE.glob("*.md"))) + 1
    assert any(policy.id == "repository-dependency-policy" for policy in policies)


def test_consultation_uses_registered_workspace_policy_sources(
    runtime,
    tmp_path: Path,
) -> None:
    source = tmp_path / "workspace-policies"
    source.mkdir()
    bundled = (BUNDLED_POLICY_SOURCE / "contain-dependencies.md").read_text(encoding="utf-8")
    (source / "workspace-containment.md").write_text(
        bundled.replace(
            "id: contain-dependencies",
            "id: workspace-containment",
            1,
        ).replace(
            "scope: general",
            "scope: organisation\napplies_to: example-organisation",
            1,
        ),
        encoding="utf-8",
    )
    runtime.policy_service.add_source(source)
    revision = runtime.case_service.create(
        _case().model_copy(
            update={
                "policy_applicability": PolicyApplicabilityContext(
                    organisation="example-organisation"
                )
            }
        )
    )

    run = runtime.workflow.advise(revision.case_id)

    assert run.policy_index_version_id is not None
    policies = runtime.policy_store.list_policies(run.policy_index_version_id)
    assert any(policy.id == "workspace-containment" for policy in policies)
    assert all(
        retrieved.policy.scope.value == "general"
        or retrieved.policy.applies_to == "example-organisation"
        for packet in run.focused_packets
        for retrieved in packet.policies
    )


def test_policy_preflight_fails_before_reasoning(
    tmp_path: Path,
    fake_config_text: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workspace = tmp_path / "workspace"
    config_path = workspace / "config" / "models.yaml"
    config_path.parent.mkdir(parents=True)
    config_path.write_text(fake_config_text, encoding="utf-8")
    runtime = build_runtime(
        workspace,
        policy_sources=[tmp_path / "missing-policies"],
    )
    revision = runtime.case_service.create(_case())

    def unexpected_reasoning(*args: object, **kwargs: object) -> None:
        pytest.fail("reasoning must not start before policy preflight succeeds")

    monkeypatch.setattr(
        runtime.workflow._reasoning,
        "discover_design_forces",
        unexpected_reasoning,
    )

    with pytest.raises(PolicyFormatError, match="found no policy documents"):
        runtime.workflow.advise(revision.case_id)

    with runtime.database.connect() as connection:
        row = connection.execute(
            "SELECT run_id FROM consultation_runs WHERE case_id = ?",
            (revision.case_id,),
        ).fetchone()
    assert row is not None
    failed = runtime.run_repository.get(str(row["run_id"]))
    assert failed.status == ConsultationStatus.FAILED
    assert failed.failure_stage == ConsultationFailureStage.POLICY
    assert failed.sanitized_errors
    assert failed.prompt_identities == []


def test_invalid_cluster_partition_is_persisted_as_a_failed_run(
    runtime,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class InvalidClusterReasoner(DeterministicReasoningProvider):
        def cluster_design_forces(self, context, forces):
            del context
            return [
                ConcernCluster(
                    cluster_id="cluster-invalid",
                    title="Incomplete concern",
                    rationale="Deliberately omits discovered forces.",
                    design_force_ids=[forces[0].force_id],
                )
            ]

    monkeypatch.setattr(runtime.workflow, "_reasoning", InvalidClusterReasoner())
    revision = runtime.case_service.create(_case())

    with pytest.raises(ClusterPartitionError, match="Missing force handles"):
        runtime.workflow.advise(revision.case_id)

    with runtime.database.connect() as connection:
        row = connection.execute(
            "SELECT run_id FROM consultation_runs WHERE case_id = ?",
            (revision.case_id,),
        ).fetchone()
    assert row is not None
    failed = runtime.run_repository.get(str(row["run_id"]))
    assert failed.status == ConsultationStatus.FAILED
    assert failed.failure_stage == ConsultationFailureStage.CLUSTERING
    assert [cluster.cluster_id for cluster in failed.clusters] == ["cluster-invalid"]
    assert [item.code for item in failed.failure_diagnostics] == [
        FailureDiagnosticCode.MISSING_FORCE_REFERENCES
    ]
    assert failed.failure_diagnostics[0].force_handles
    assert "force_" not in failed.sanitized_errors[0]
    assert failed.prompt_identities == [
        "discover-design-forces:v3",
        "cluster-design-forces:v2",
    ]


def test_failed_evidence_repair_remains_loadable_with_full_history(
    runtime,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class UnsupportedReportReasoner(DeterministicReasoningProvider):
        def synthesize_recommendation(self, *args, **kwargs):
            report = super().synthesize_recommendation(*args, **kwargs)
            invented = Claim(
                claim_id="claim-invented-repository",
                text="An unsurfaced repository node proves the recommendation.",
                classification=ClaimClassification.REPOSITORY_OBSERVATION,
                atlas_references=[
                    AtlasEvidenceReference(
                        node_id="node-invented",
                        location=SourceLocation(
                            path="invented.py",
                            start_line=1,
                            end_line=1,
                        ),
                    )
                ],
            )

            def unsupported(statement):
                return statement.model_copy(update={"supporting_claim_ids": [invented.claim_id]})

            return report.model_copy(
                update={
                    "repository_observations": [invented],
                    "evidence_appendix": [*report.evidence_appendix, invented],
                    "decision_summary": unsupported(report.decision_summary),
                    "recommended_architecture": unsupported(report.recommended_architecture),
                    "responsibility_allocation": [
                        unsupported(item) for item in report.responsibility_allocation
                    ],
                    "conceptual_interfaces": [
                        unsupported(item) for item in report.conceptual_interfaces
                    ],
                    "change_amplification_analysis": unsupported(
                        report.change_amplification_analysis
                    ),
                    "trade_offs": [unsupported(item) for item in report.trade_offs],
                    "implementation_sequence": [
                        unsupported(item) for item in report.implementation_sequence
                    ],
                    "reversal_conditions": [
                        unsupported(item) for item in report.reversal_conditions
                    ],
                    "revisit_triggers": [unsupported(item) for item in report.revisit_triggers],
                    "adr": report.adr.model_copy(
                        update={
                            "decision": unsupported(report.adr.decision),
                            "consequences": [unsupported(item) for item in report.adr.consequences],
                        }
                    ),
                }
            )

    monkeypatch.setattr(runtime.workflow, "_reasoning", UnsupportedReportReasoner())
    revision = runtime.case_service.create(_case())

    with pytest.raises(EvidenceReferenceError, match="evidence validation failed"):
        runtime.workflow.advise(revision.case_id)

    with runtime.database.connect() as connection:
        row = connection.execute(
            "SELECT run_id FROM consultation_runs WHERE case_id = ?",
            (revision.case_id,),
        ).fetchone()
    assert row is not None
    failed = runtime.run_repository.get(str(row["run_id"]))
    assert failed.failure_stage == ConsultationFailureStage.VALIDATION
    assert failed.initial_validation_errors
    assert failed.repair_actions
    assert failed.final_validation_errors
    assert failed.report is not None
    assert failed.report.repository_observations[0].claim_id == ("claim-invented-repository")
    assert runtime.case_service.show(revision.case_id).revision == 1


def test_cluster_query_budget_is_global_and_case_records_persisted_atlas(
    runtime,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class Fresh:
        def ensure_fresh(self, atlas: object) -> None:
            del atlas

    class TwoClusterReasoner(DeterministicReasoningProvider):
        def cluster_design_forces(self, context, forces):
            del context
            midpoint = max(1, len(forces) // 2)
            groups = (forces[:midpoint], forces[midpoint:])
            return [
                ConcernCluster(
                    cluster_id=f"cluster-{index}",
                    title=f"Concern {index}",
                    rationale="Exercise the global planning budget.",
                    design_force_ids=[force.force_id for force in group],
                )
                for index, group in enumerate(groups, start=1)
                if group
            ]

        def plan_atlas_queries(
            self,
            context,
            forces,
            clusters,
            *,
            iteration,
            prior_results,
        ):
            del context, forces, prior_results
            return [
                ClusterQueryPlan(
                    cluster_id=cluster.cluster_id,
                    plan=AtlasQueryPlan(
                        iteration=iteration,
                        rationale="Deliberately exceed the shared budget.",
                        queries=(
                            [
                                RepositorySummaryQuery(
                                    kind="repository_summary",
                                    limit=30,
                                )
                                for _ in range(6)
                            ]
                            if iteration == 1
                            else []
                        ),
                    ),
                )
                for cluster in clusters
            ]

    monkeypatch.setattr(runtime.workflow, "_freshness", Fresh())
    monkeypatch.setattr(runtime.workflow, "_reasoning", TwoClusterReasoner())
    atlas = runtime.analyzer.analyze(Path("eval/cases/provider-leakage/repository").resolve())
    runtime.atlas_repository.save(atlas)
    revision = runtime.case_service.create(_case(brownfield=True))

    run = runtime.workflow.advise(
        revision.case_id,
        atlas_version_id=atlas.version.version_id,
    )

    first_iteration = [item for item in run.query_plans if item.plan.iteration == 1]
    assert sum(len(item.plan.queries) for item in first_iteration) == 8
    assert all(len(item.plan.queries) == 4 for item in first_iteration)
    assert any(item["kind"] == "query_budget" for item in run.execution_metadata["truncations"])
    updated = runtime.case_service.show(revision.case_id).snapshot
    assert updated.repository is not None
    assert updated.repository.atlas_version_id == atlas.version.version_id
    assert updated.repository.root_path == atlas.version.root_path


def test_successful_consultation_preserves_user_forces_and_replaces_advisor_forces(
    runtime,
) -> None:
    user_force = CaseStatement(
        id="force-user-owned",
        text="Resource lifecycle: Cleanup ownership must remain explicit.",
        kind=StatementKind.FORCE,
        source="user",
    )
    stale_advisor_force = CaseStatement(
        id="force-stale-advisor",
        text="Old advisor observation",
        kind=StatementKind.FORCE,
        source="run_previous",
    )
    revision = runtime.case_service.create(
        _case().model_copy(
            update={
                "design_forces": [user_force],
                "advisor_design_forces": [stale_advisor_force],
            }
        )
    )

    run = runtime.workflow.advise(revision.case_id)
    updated = runtime.case_service.show(revision.case_id).snapshot

    assert updated.design_forces == [user_force]
    assert updated.advisor_design_forces
    assert all(item.source == run.run_id for item in updated.advisor_design_forces)
    assert all(item.id != stale_advisor_force.id for item in updated.advisor_design_forces)
    assert run.design_forces[0].force_id == user_force.id
    assert any(user_force.id in cluster.design_force_ids for cluster in run.clusters)
    assert run.report is not None
    assert any(force.force_id == user_force.id for force in run.report.important_design_forces)


def test_advisor_force_id_collisions_are_reminted_without_losing_forces(
    runtime,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user_force = CaseStatement(
        id="force-shared",
        text="Resource lifecycle: Cleanup ownership must remain explicit.",
        kind=StatementKind.FORCE,
        source="user",
    )

    class CollidingReasoner(DeterministicReasoningProvider):
        def discover_design_forces(self, context):
            del context
            return [
                DesignForce(
                    force_id=user_force.id,
                    title="Provider ownership",
                    description="Provider knowledge needs one owner.",
                    importance="high",
                ),
                DesignForce(
                    force_id=user_force.id,
                    title="Change locality",
                    description="Provider changes should remain local.",
                    importance="high",
                ),
            ]

    monkeypatch.setattr(runtime.workflow, "_reasoning", CollidingReasoner())
    revision = runtime.case_service.create(
        _case().model_copy(update={"design_forces": [user_force]})
    )

    run = runtime.workflow.advise(revision.case_id)

    assert len(run.design_forces) == 3
    assert run.design_forces[0].force_id == user_force.id
    assert len({force.force_id for force in run.design_forces}) == 3
    assert all(force.force_id != user_force.id for force in run.design_forces[1:])
    updated = runtime.case_service.show(revision.case_id).snapshot
    assert [item.id for item in updated.advisor_design_forces] == [
        force.force_id for force in run.design_forces[1:]
    ]


def test_unsurfaced_model_query_ids_are_dropped_and_audited(
    runtime,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class Fresh:
        def ensure_fresh(self, atlas: object) -> None:
            del atlas

    class InventedQueryIdReasoner(DeterministicReasoningProvider):
        def plan_atlas_queries(
            self,
            context,
            forces,
            clusters,
            *,
            iteration,
            prior_results,
        ):
            del context, forces, prior_results
            return [
                ClusterQueryPlan(
                    cluster_id=cluster.cluster_id,
                    plan=AtlasQueryPlan(
                        iteration=iteration,
                        rationale="Discover first, then inspect only surfaced IDs.",
                        queries=(
                            [
                                SearchNodesQuery(
                                    kind="search_nodes",
                                    terms=["provider"],
                                    limit=20,
                                ),
                                NodeDetailsQuery(
                                    kind="node_details",
                                    node_id="invented_provider_node",
                                ),
                            ]
                            if iteration == 1
                            else []
                        ),
                    ),
                )
                for cluster in clusters
            ]

    monkeypatch.setattr(runtime.workflow, "_freshness", Fresh())
    monkeypatch.setattr(runtime.workflow, "_reasoning", InventedQueryIdReasoner())
    atlas = runtime.analyzer.analyze(Path("eval/cases/provider-leakage/repository").resolve())
    runtime.atlas_repository.save(atlas)
    revision = runtime.case_service.create(_case(brownfield=True))

    run = runtime.workflow.advise(
        revision.case_id,
        atlas_version_id=atlas.version.version_id,
    )

    assert run.status == ConsultationStatus.SUCCEEDED
    assert all(
        query.kind != "node_details" for plan in run.query_plans for query in plan.plan.queries
    )
    assert run.execution_metadata["query_plan_repairs"] == [
        {
            "kind": "dropped_unsurfaced_node_query",
            "cluster_id": cluster.cluster_id,
            "iteration": 1,
            "unknown_node_ids": ["invented_provider_node"],
            "query": {
                "kind": "node_details",
                "node_id": "invented_provider_node",
            },
        }
        for cluster in run.clusters
    ]


def test_omitted_cluster_query_plan_is_completed_and_audited(
    runtime,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class Fresh:
        def ensure_fresh(self, atlas: object) -> None:
            del atlas

    class OmittedClusterPlanReasoner(DeterministicReasoningProvider):
        def cluster_design_forces(self, context, forces):
            del context
            return [
                ConcernCluster(
                    cluster_id=f"cluster-{index}",
                    title=f"Concern {index}",
                    rationale="Keep both concern clusters explicit.",
                    design_force_ids=[force.force_id],
                )
                for index, force in enumerate(forces, start=1)
            ]

        def plan_atlas_queries(
            self,
            context,
            forces,
            clusters,
            *,
            iteration,
            prior_results,
        ):
            del context, forces, prior_results
            return [
                ClusterQueryPlan(
                    cluster_id=clusters[0].cluster_id,
                    plan=AtlasQueryPlan(
                        iteration=iteration,
                        rationale="The model returned only the first cluster.",
                        queries=[],
                    ),
                )
            ]

    monkeypatch.setattr(runtime.workflow, "_freshness", Fresh())
    monkeypatch.setattr(runtime.workflow, "_reasoning", OmittedClusterPlanReasoner())
    atlas = runtime.analyzer.analyze(Path("eval/cases/provider-leakage/repository").resolve())
    runtime.atlas_repository.save(atlas)
    revision = runtime.case_service.create(_case(brownfield=True))

    run = runtime.workflow.advise(
        revision.case_id,
        atlas_version_id=atlas.version.version_id,
    )

    assert run.status == ConsultationStatus.SUCCEEDED
    assert {plan.cluster_id for plan in run.query_plans} == {
        cluster.cluster_id for cluster in run.clusters
    }
    added = [
        repair
        for repair in run.execution_metadata["query_plan_repairs"]
        if repair["kind"] == "added_empty_cluster_plan"
    ]
    assert len(added) == len(run.clusters) - 1


def test_concern_analysis_cluster_identity_is_corrected_and_audited(
    runtime,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class WrongAnalysisClusterReasoner(DeterministicReasoningProvider):
        def analyze_concern_cluster(self, context, packet):
            analysis = super().analyze_concern_cluster(context, packet)
            return analysis.model_copy(
                update={
                    "cluster_id": "invented-cluster",
                    "concern": "invented-cluster",
                }
            )

    monkeypatch.setattr(
        runtime.workflow,
        "_reasoning",
        WrongAnalysisClusterReasoner(),
    )
    revision = runtime.case_service.create(_case())

    run = runtime.workflow.advise(revision.case_id)

    assert run.status == ConsultationStatus.SUCCEEDED
    assert [(analysis.cluster_id, analysis.concern) for analysis in run.concern_analyses] == [
        (cluster.cluster_id, cluster.title) for cluster in run.clusters
    ]
    assert run.execution_metadata["model_output_repairs"] == [
        repair
        for cluster in run.clusters
        for repair in (
            {
                "kind": "corrected_concern_analysis_cluster",
                "from_cluster_id": "invented-cluster",
                "to_cluster_id": cluster.cluster_id,
            },
            {
                "kind": "corrected_concern_analysis_title",
                "cluster_id": cluster.cluster_id,
                "from_concern": "invented-cluster",
                "to_concern": cluster.title,
            },
        )
    ]


def test_unsupported_repository_finding_is_dropped_and_audited(
    runtime,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class UnsupportedRepositoryFindingReasoner(DeterministicReasoningProvider):
        def analyze_concern_cluster(self, context, packet):
            analysis = super().analyze_concern_cluster(context, packet)
            unsupported = Claim(
                claim_id="claim-unsupported-repository",
                text="This repository claim has no surfaced source support.",
                classification=ClaimClassification.REPOSITORY_OBSERVATION,
            )
            return analysis.model_copy(update={"findings": [*analysis.findings, unsupported]})

    monkeypatch.setattr(
        runtime.workflow,
        "_reasoning",
        UnsupportedRepositoryFindingReasoner(),
    )
    revision = runtime.case_service.create(_case())

    run = runtime.workflow.advise(revision.case_id)

    assert run.status == ConsultationStatus.SUCCEEDED
    assert all(
        finding.claim_id != "claim-unsupported-repository"
        for analysis in run.concern_analyses
        for finding in analysis.findings
    )
    assert any(
        repair["kind"] == "dropped_unsupported_repository_finding"
        for repair in run.execution_metadata["model_output_repairs"]
    )


def test_fully_invalid_concern_analysis_fails_without_regeneration(
    runtime,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class InvalidConcernReasoner(DeterministicReasoningProvider):
        attempts = 0

        def analyze_concern_cluster(self, context, packet):
            self.attempts += 1
            return (
                super()
                .analyze_concern_cluster(context, packet)
                .model_copy(
                    update={
                        "findings": [
                            Claim(
                                claim_id="claim-unsupported-only",
                                text="This repository claim has no surfaced source support.",
                                classification=ClaimClassification.REPOSITORY_OBSERVATION,
                            )
                        ]
                    }
                )
            )

    reasoner = InvalidConcernReasoner()
    monkeypatch.setattr(runtime.workflow, "_reasoning", reasoner)
    revision = runtime.case_service.create(_case())

    with pytest.raises(
        ModelOutputValidationError,
        match="Repository findings require",
    ):
        runtime.workflow.advise(revision.case_id)

    assert reasoner.attempts == 1
    with runtime.database.connect() as connection:
        row = connection.execute(
            "SELECT run_id FROM consultation_runs WHERE case_id = ?",
            (revision.case_id,),
        ).fetchone()
    assert row is not None
    failed = runtime.run_repository.get(str(row["run_id"]))
    assert failed.status == ConsultationStatus.FAILED
    assert failed.failure_stage == ConsultationFailureStage.CONCERN_ANALYSIS
    assert failed.prompt_identities.count("analyze-concern:v2") == 1
    assert failed.execution_metadata["model_output_repairs"] == [
        {
            "kind": "rejected_empty_concern_evidence_repair",
            "cluster_id": failed.focused_packets[0].cluster.cluster_id,
            "proposed_repairs": [
                {
                    "kind": "dropped_unsupported_repository_finding",
                    "cluster_id": failed.focused_packets[0].cluster.cluster_id,
                    "claim": {
                        "claim_id": "claim-unsupported-only",
                        "text": "This repository claim has no surfaced source support.",
                        "classification": "repository_observation",
                        "atlas_references": [],
                        "policy_ids": [],
                    },
                }
            ],
        }
    ]
    assert runtime.case_service.show(revision.case_id).revision == 1


def test_synthesis_reuses_canonical_upstream_artifacts_and_audits_repairs(
    runtime,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class RecreatedSynthesisArtifactsReasoner(DeterministicReasoningProvider):
        def synthesize_recommendation(
            self,
            case,
            context,
            forces,
            clusters,
            analyses,
            alternatives,
            scenarios,
            packets,
        ):
            report = super().synthesize_recommendation(
                case,
                context,
                forces,
                clusters,
                analyses,
                alternatives,
                scenarios,
                packets,
            )
            recreated_forces = [
                force.model_copy(update={"force_id": f"recreated-{index}"})
                for index, force in enumerate(forces, start=1)
            ]
            recreated_policy_evidence = [
                report.policy_evidence[0].model_copy(
                    update={
                        "title": report.policy_evidence[0].id,
                        "matched_sections": ["Invented section"],
                    }
                ),
                *report.policy_evidence[1:],
            ]
            return report.model_copy(
                update={
                    "important_design_forces": recreated_forces,
                    "policy_evidence": recreated_policy_evidence,
                }
            )

    monkeypatch.setattr(
        runtime.workflow,
        "_reasoning",
        RecreatedSynthesisArtifactsReasoner(),
    )
    revision = runtime.case_service.create(_case())

    run = runtime.workflow.advise(revision.case_id)

    assert run.status == ConsultationStatus.SUCCEEDED
    assert run.report is not None
    assert run.report.important_design_forces == run.design_forces
    repairs = [
        repair
        for repair in run.execution_metadata["model_output_repairs"]
        if repair["kind"] == "restored_canonical_synthesis_artifact"
    ]
    assert [repair["field"] for repair in repairs] == ["important_design_forces"]
    assert [force["force_id"] for force in repairs[0]["model_output"]] == [
        f"recreated-{index}" for index in range(1, len(run.design_forces) + 1)
    ]
    assert repairs[0]["canonical_input"] == [
        force.model_dump(mode="json") for force in run.design_forces
    ]
    policy_repairs = [
        repair
        for repair in run.execution_metadata["model_output_repairs"]
        if repair["kind"] == "restored_canonical_policy_evidence"
        and repair["model_output"]["matched_sections"] == ["Invented section"]
    ]
    assert len(policy_repairs) == 1
    assert policy_repairs[0]["model_output"]["matched_sections"] == ["Invented section"]
    assert policy_repairs[0]["canonical_input"] == (
        run.report.policy_evidence[0].model_dump(mode="json")
    )


def test_invalid_synthesis_fails_after_deterministic_repair_without_regeneration(
    runtime,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class InvalidSynthesisReasoner(DeterministicReasoningProvider):
        attempts = 0

        def synthesize_recommendation(
            self,
            case,
            context,
            forces,
            clusters,
            analyses,
            alternatives,
            scenarios,
            packets,
        ):
            self.attempts += 1
            report = super().synthesize_recommendation(
                case,
                context,
                forces,
                clusters,
                analyses,
                alternatives,
                scenarios,
                packets,
            )
            return report.model_copy(
                update={
                    "decision_summary": report.decision_summary.model_copy(
                        update={"supporting_claim_ids": ["claim-invented"]}
                    )
                }
            )

    reasoner = InvalidSynthesisReasoner()
    monkeypatch.setattr(runtime.workflow, "_reasoning", reasoner)
    revision = runtime.case_service.create(_case())

    with pytest.raises(EvidenceReferenceError, match="no supporting claim IDs"):
        runtime.workflow.advise(revision.case_id)

    assert reasoner.attempts == 1
    with runtime.database.connect() as connection:
        row = connection.execute(
            "SELECT run_id FROM consultation_runs WHERE case_id = ?",
            (revision.case_id,),
        ).fetchone()
    assert row is not None
    failed = runtime.run_repository.get(str(row["run_id"]))
    assert failed.status == ConsultationStatus.FAILED
    assert failed.failure_stage == ConsultationFailureStage.VALIDATION
    assert failed.initial_validation_errors
    assert failed.final_validation_errors
    assert failed.prompt_identities.count("synthesize-recommendation:v2") == 1
    assert runtime.case_service.show(revision.case_id).revision == 1


def test_explicit_repository_precedes_case_atlas_and_uses_its_latest_version(
    runtime,
    tmp_path: Path,
) -> None:
    first_repository = tmp_path / "first-repository"
    explicit_repository = tmp_path / "explicit-repository"
    fixture = Path("eval/cases/provider-leakage/repository")
    shutil.copytree(fixture, first_repository)
    shutil.copytree(fixture, explicit_repository)
    case_atlas = runtime.analyzer.analyze(first_repository)
    runtime.atlas_repository.save(case_atlas)
    explicit_older = runtime.analyzer.analyze(explicit_repository)
    runtime.atlas_repository.save(explicit_older)
    explicit_latest = runtime.analyzer.analyze(explicit_repository)
    runtime.atlas_repository.save(explicit_latest)
    case = _case(brownfield=True).model_copy(
        update={
            "repository": RepositoryReference(
                root_path=case_atlas.version.root_path,
                atlas_version_id=case_atlas.version.version_id,
            )
        }
    )
    recorded_revision = runtime.case_service.create(case)
    explicit_revision = runtime.case_service.create(
        case.model_copy(update={"case_id": "case-explicit"})
    )

    recorded_run = runtime.workflow.advise(recorded_revision.case_id)
    explicit_run = runtime.workflow.advise(
        explicit_revision.case_id,
        repository_root=explicit_repository,
    )

    assert recorded_run.atlas_version_id == case_atlas.version.version_id
    assert explicit_run.atlas_version_id == explicit_latest.version.version_id
    assert explicit_run.atlas_version_id != explicit_older.version.version_id
    updated = runtime.case_service.show(explicit_revision.case_id).snapshot
    assert updated.repository == RepositoryReference(
        root_path=explicit_latest.version.root_path,
        atlas_version_id=explicit_latest.version.version_id,
    )
