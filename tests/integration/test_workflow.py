from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from archcompass.adapters.models.deterministic import DeterministicReasoningProvider
from archcompass.bootstrap import BUNDLED_POLICY_SOURCE, build_runtime
from archcompass.domain.atlas import (
    AtlasQueryPlan,
    RepositorySummaryQuery,
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
    ConcernCluster,
    ConsultationFailureStage,
    ConsultationStatus,
)
from archcompass.domain.errors import (
    EvidenceReferenceError,
    ModelOutputValidationError,
    PolicyFormatError,
)


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


def test_greenfield_workflow_never_requires_atlas(runtime) -> None:
    assert runtime.policy_store.current_version() is None
    revision = runtime.case_service.create(_case())
    run = runtime.workflow.advise(revision.case_id)
    assert run.status == ConsultationStatus.SUCCEEDED
    assert run.atlas_version_id is None
    assert run.query_plans == []
    assert run.clusters
    assert len(run.concern_analyses) == len(run.clusters)
    assert "plan-cluster-atlas-queries:v2" not in run.prompt_identities
    assert run.stage_timings["discover_design_forces"] >= 0
    assert run.policy_index_version_id is not None
    assert run.execution_metadata["retrieved_policies"] == 6
    assert run.report is not None
    assert "provider" in run.report.recommended_architecture.casefold()
    assert runtime.case_service.show(revision.case_id).revision == 2


def test_brownfield_workflow_uses_focused_packets_not_raw_atlas(runtime) -> None:
    atlas = runtime.analyzer.analyze(
        Path("eval/cases/provider-leakage/repository").resolve()
    )
    runtime.atlas_repository.save(atlas)
    revision = runtime.case_service.create(_case(brownfield=True))
    run = runtime.workflow.advise(revision.case_id, atlas=atlas)
    assert run.status == ConsultationStatus.SUCCEEDED
    assert run.focused_packets
    assert all(packet.query_results for packet in run.focused_packets)
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

    run = runtime.workflow.advise(revision.case_id, atlas=atlas)

    assert run.policy_index_version_id is not None
    policies = runtime.policy_store.list_policies(run.policy_index_version_id)
    assert len(policies) == 16
    assert any(policy.id == "repository-dependency-policy" for policy in policies)


def test_consultation_uses_registered_workspace_policy_sources(
    runtime,
    tmp_path: Path,
) -> None:
    source = tmp_path / "workspace-policies"
    source.mkdir()
    bundled = (BUNDLED_POLICY_SOURCE / "contain-dependencies.md").read_text(
        encoding="utf-8"
    )
    (source / "workspace-containment.md").write_text(
        bundled.replace(
            "id: contain-dependencies",
            "id: workspace-containment",
            1,
        ).replace("scope: general", "scope: organisation", 1),
        encoding="utf-8",
    )
    runtime.policy_service.add_source(source)
    revision = runtime.case_service.create(_case())

    run = runtime.workflow.advise(revision.case_id)

    assert run.policy_index_version_id is not None
    policies = runtime.policy_store.list_policies(run.policy_index_version_id)
    assert any(policy.id == "workspace-containment" for policy in policies)


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

    with pytest.raises(ModelOutputValidationError, match="omit force"):
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
    assert failed.prompt_identities == [
        "discover-design-forces:v2",
        "cluster-design-forces:v1",
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
                return statement.model_copy(
                    update={"supporting_claim_ids": [invented.claim_id]}
                )

            return report.model_copy(
                update={
                    "repository_observations": [invented],
                    "evidence_appendix": [*report.evidence_appendix, invented],
                    "decision_summary": unsupported(report.decision_summary),
                    "recommended_architecture": unsupported(
                        report.recommended_architecture
                    ),
                    "responsibility_allocation": [
                        unsupported(item)
                        for item in report.responsibility_allocation
                    ],
                    "conceptual_interfaces": [
                        unsupported(item) for item in report.conceptual_interfaces
                    ],
                    "change_amplification_analysis": unsupported(
                        report.change_amplification_analysis
                    ),
                    "trade_offs": [
                        unsupported(item) for item in report.trade_offs
                    ],
                    "implementation_sequence": [
                        unsupported(item)
                        for item in report.implementation_sequence
                    ],
                    "reversal_conditions": [
                        unsupported(item)
                        for item in report.reversal_conditions
                    ],
                    "revisit_triggers": [
                        unsupported(item) for item in report.revisit_triggers
                    ],
                    "adr": report.adr.model_copy(
                        update={
                            "decision": unsupported(report.adr.decision),
                            "consequences": [
                                unsupported(item)
                                for item in report.adr.consequences
                            ],
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
    assert failed.report.repository_observations[0].claim_id == (
        "claim-invented-repository"
    )
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
    atlas = runtime.analyzer.analyze(
        Path("eval/cases/provider-leakage/repository").resolve()
    )
    runtime.atlas_repository.save(atlas)
    revision = runtime.case_service.create(_case(brownfield=True))

    run = runtime.workflow.advise(
        revision.case_id,
        atlas_version_id=atlas.version.version_id,
    )

    first_iteration = [item for item in run.query_plans if item.plan.iteration == 1]
    assert sum(len(item.plan.queries) for item in first_iteration) == 8
    assert any(item["kind"] == "query_budget" for item in run.execution_metadata["truncations"])
    updated = runtime.case_service.show(revision.case_id).snapshot
    assert updated.repository is not None
    assert updated.repository.atlas_version_id == atlas.version.version_id
    assert updated.repository.root_path == atlas.version.root_path


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
