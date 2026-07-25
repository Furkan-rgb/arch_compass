"""Unified, auditable greenfield and brownfield consultation workflow."""

from __future__ import annotations

import re
from collections import Counter
from collections.abc import Callable
from contextlib import suppress
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from time import perf_counter
from typing import TypeVar, cast

from pydantic import JsonValue

from archcompass.application.evidence import (
    canonicalize_report_findings,
    repair_report_evidence_with_history,
    validate_report_evidence,
)
from archcompass.application.reporting import render_markdown
from archcompass.configuration import AppConfig
from archcompass.domain.atlas import (
    Atlas,
    AtlasEdge,
    AtlasNode,
    AtlasNodeEvidence,
    AtlasNodeSummary,
    AtlasOverview,
    AtlasQuery,
    AtlasQueryPlan,
    AtlasQueryResult,
    AtlasRelationshipEvidence,
    AtlasSelectionReason,
    AtlasSelectionReasonKind,
    NodeType,
    ObscuritySignal,
    SourceExcerpt,
    SourceLocation,
)
from archcompass.domain.atlas_metrics import (
    canonical_metric_name,
    salient_profile_observations,
)
from archcompass.domain.base import canonical_json, new_id, utc_now
from archcompass.domain.case import (
    ArchitectureCase,
    CaseAlternative,
    CaseStatement,
    Confidence,
    RecommendationState,
    RepositoryReference,
    StatementKind,
)
from archcompass.domain.consultation import (
    ClaimClassification,
    ClusterQueryPlan,
    ConcernAnalysis,
    ConcernCluster,
    ConsultationFailureStage,
    ConsultationRun,
    ConsultationStatus,
    DesignForce,
    FocusedAnalysisPacket,
    FocusedNodeSummary,
    GlobalContext,
    RecommendationReport,
    ScenarioEvaluation,
    cluster_partition_diagnostics,
)
from archcompass.domain.errors import (
    AtlasNotFoundError,
    ClusterPartitionError,
    EvidenceReferenceError,
    ModelOutputValidationError,
)
from archcompass.domain.evidence_rules import location_within
from archcompass.domain.execution import ProgressEventType
from archcompass.domain.policy import (
    PolicyApplicabilityContext,
    PolicyEvidenceSummary,
    PolicyIndexVersion,
    RetrievedPolicy,
    canonical_policy_evidence,
)
from archcompass.ports.atlas import AtlasFreshnessChecker, AtlasQueryService
from archcompass.ports.policies import PolicyIndex, PolicyRetriever
from archcompass.ports.progress import ConsultationProgressSink
from archcompass.ports.reasoning import FocusedReasoningProvider, ReasoningTask
from archcompass.ports.repositories import (
    AtlasRepository,
    CaseRepository,
    ConsultationCommitRepository,
    ConsultationRunRepository,
)

Result = TypeVar("Result")
POLICY_QUERY_CHARACTER_BUDGET = 8_000


def _surfaced_span(
    node_summaries: dict[str, FocusedNodeSummary],
    node_id: str,
) -> SourceLocation | None:
    """The span a packet surfaced for a node, or None when it surfaced no node."""

    summary = node_summaries.get(node_id)
    return summary.location if summary is not None else None


class ConsultationWorkflow:
    def __init__(
        self,
        *,
        config: AppConfig,
        cases: CaseRepository,
        runs: ConsultationRunRepository,
        commits: ConsultationCommitRepository,
        atlases: AtlasRepository,
        queries: AtlasQueryService,
        policy_index: PolicyIndex,
        policies: PolicyRetriever,
        reasoning: FocusedReasoningProvider,
        policy_sources: tuple[Path, ...],
        freshness: AtlasFreshnessChecker | None = None,
        policy_source_resolver: Callable[[Path | None], list[Path]] | None = None,
        repository_validator: Callable[[Path], object] | None = None,
    ) -> None:
        self._config = config
        self._cases = cases
        self._runs = runs
        self._commits = commits
        self._atlases = atlases
        self._queries = queries
        self._policy_index = policy_index
        self._policies = policies
        self._reasoning = reasoning
        self._policy_sources = policy_sources
        self._freshness = freshness
        self._policy_source_resolver = policy_source_resolver
        self._repository_validator = repository_validator

    def advise(
        self,
        case_id: str,
        *,
        atlas_version_id: str | None = None,
        repository_root: Path | None = None,
        run_id: str | None = None,
        input_case_revision: int | None = None,
        progress: ConsultationProgressSink | None = None,
    ) -> ConsultationRun:
        """Advise from persisted evidence."""
        started = datetime.now(UTC)
        revision = self._cases.get(case_id, input_case_revision)
        case = revision.snapshot
        consultation_run_id = run_id or new_id("run")
        stage_timings: dict[str, float] = {}
        prompt_identities: list[str] = []
        advisor_forces: list[DesignForce] = []
        forces: list[DesignForce] = []
        clusters: list[ConcernCluster] = []
        plans: list[ClusterQueryPlan] = []
        packets: list[FocusedAnalysisPacket] = []
        analyses: list[ConcernAnalysis] = []
        alternatives: list[CaseAlternative] = []
        scenarios: list[ScenarioEvaluation] = []
        report: RecommendationReport | None = None
        unrepaired_report: RecommendationReport | None = None
        markdown: str | None = None
        initial_errors: list[str] = []
        repair_actions: list[str] = []
        final_errors: list[str] = []
        execution_metadata: dict[str, object] = {
            "truncations": [],
            "query_plan_repairs": [],
            "model_output_repairs": [],
            "zoom_iterations": 0,
            "atlas_queries": 0,
            "retrieved_policies": 0,
        }
        atlas_query_count = 0
        retrieved_policy_count = 0
        current_stage = ConsultationFailureStage.ATLAS_RESOLUTION
        resolved_atlas: Atlas | None = None
        policy_version: PolicyIndexVersion | None = None

        try:
            self._progress_started(
                progress,
                ConsultationFailureStage.ATLAS_RESOLUTION,
                "Preparing repository context",
            )
            resolved_atlas = self._timed(
                stage_timings,
                "atlas_resolution",
                lambda: self._resolve_atlas(
                    case,
                    atlas_version_id=atlas_version_id,
                    repository_root=repository_root,
                ),
            )
            if resolved_atlas is not None:
                repository_path = Path(resolved_atlas.version.root_path)
                if self._repository_validator is not None:
                    self._repository_validator(repository_path)
                freshness = self._freshness
                if freshness is None:
                    raise RuntimeError(
                        "Brownfield consultation requires an atlas freshness checker"
                    )
                self._timed(
                    stage_timings,
                    "atlas_freshness",
                    lambda: freshness.ensure_fresh(resolved_atlas),
                )
            self._progress_artifact(
                progress,
                ConsultationFailureStage.ATLAS_RESOLUTION,
                "Repository context ready",
                (
                    "Greenfield consultation; no repository atlas selected."
                    if resolved_atlas is None
                    else f"Using atlas {resolved_atlas.version.version_id}."
                ),
                {
                    "atlas_version_id": (
                        resolved_atlas.version.version_id if resolved_atlas is not None else None
                    ),
                    "repository_root": (
                        resolved_atlas.version.root_path if resolved_atlas is not None else None
                    ),
                },
            )
            self._progress_completed(
                progress,
                ConsultationFailureStage.ATLAS_RESOLUTION,
                "Repository context prepared",
            )
            current_stage = ConsultationFailureStage.POLICY
            self._progress_started(
                progress,
                ConsultationFailureStage.POLICY,
                "Preparing policy corpus",
            )
            repository_policy_root = (
                Path(resolved_atlas.version.root_path) if resolved_atlas is not None else None
            )
            if self._policy_source_resolver is not None:
                policy_sources = self._policy_source_resolver(repository_policy_root)
            else:
                policy_sources = list(self._policy_sources)
                if repository_policy_root is not None:
                    policy_sources.append(repository_policy_root / ".archcompass" / "policies")
            policy_version = self._timed(
                stage_timings,
                "policy_preflight",
                lambda: self._policy_index.ensure_current(policy_sources),
            )
            self._progress_artifact(
                progress,
                ConsultationFailureStage.POLICY,
                "Policy index ready",
                f"Using immutable policy index {policy_version.version_id}.",
                {
                    "policy_index_version_id": policy_version.version_id,
                    "embedding_model": policy_version.embedding_model,
                },
            )
            self._progress_completed(
                progress,
                ConsultationFailureStage.POLICY,
                "Policy corpus prepared",
            )
            context = self._global_context(case, resolved_atlas)

            current_stage = ConsultationFailureStage.DESIGN_FORCES
            self._progress_started(
                progress,
                ConsultationFailureStage.DESIGN_FORCES,
                "Discovering design forces",
            )
            advisor_forces = self._reason(
                ReasoningTask.DISCOVER_DESIGN_FORCES,
                prompt_identities,
                stage_timings,
                lambda: self._reasoning.discover_design_forces(context),
            )
            forces = self._merge_user_design_forces(case, advisor_forces)
            advisor_forces = forces[len(case.design_forces) :]
            self._progress_artifact(
                progress,
                ConsultationFailureStage.DESIGN_FORCES,
                "Design forces discovered",
                f"Found {len(forces)} forces shaping this decision.",
                {"design_forces": [item.model_dump(mode="json") for item in forces]},
            )
            self._progress_completed(
                progress,
                ConsultationFailureStage.DESIGN_FORCES,
                "Design forces discovered",
            )

            current_stage = ConsultationFailureStage.CLUSTERING
            self._progress_started(
                progress,
                ConsultationFailureStage.CLUSTERING,
                "Organizing concerns",
            )
            clusters = self._reason(
                ReasoningTask.CLUSTER_DESIGN_FORCES,
                prompt_identities,
                stage_timings,
                lambda: self._reasoning.cluster_design_forces(context, forces),
            )
            partition_diagnostics = cluster_partition_diagnostics(forces, clusters)
            if partition_diagnostics:
                raise ClusterPartitionError(partition_diagnostics)
            self._progress_artifact(
                progress,
                ConsultationFailureStage.CLUSTERING,
                "Concern clusters formed",
                f"Organized the forces into {len(clusters)} focused clusters.",
                {"clusters": [item.model_dump(mode="json") for item in clusters]},
            )
            self._progress_completed(
                progress,
                ConsultationFailureStage.CLUSTERING,
                "Concerns organized",
            )

            selected_by_cluster: dict[str, list[str]] = {
                cluster.cluster_id: [] for cluster in clusters
            }
            summaries_by_cluster: dict[str, dict[str, FocusedNodeSummary]] = {
                cluster.cluster_id: {} for cluster in clusters
            }
            excerpts_by_cluster: dict[str, list[SourceExcerpt]] = {
                cluster.cluster_id: [] for cluster in clusters
            }
            relationships_by_cluster: dict[str, dict[str, AtlasEdge]] = {
                cluster.cluster_id: {} for cluster in clusters
            }
            test_ids_by_cluster: dict[str, set[str]] = {
                cluster.cluster_id: set() for cluster in clusters
            }
            excerpt_lines_by_cluster = {cluster.cluster_id: 0 for cluster in clusters}

            if resolved_atlas is not None:
                nodes = {node.atlas_id: node for node in resolved_atlas.nodes}
                for iteration in range(1, self._config.consultation.max_zoom_iterations + 1):
                    current_stage = ConsultationFailureStage.QUERY_PLANNING
                    self._progress_started(
                        progress,
                        ConsultationFailureStage.QUERY_PLANNING,
                        f"Planning repository zoom {iteration}",
                    )
                    iteration_plans = self._reason(
                        ReasoningTask.PLAN_ATLAS_QUERIES,
                        prompt_identities,
                        stage_timings,
                        lambda iteration=iteration: self._reasoning.plan_atlas_queries(
                            context,
                            forces,
                            clusters,
                            iteration=iteration,
                            prior_results={
                                cluster_id: list(items.values())
                                for cluster_id, items in summaries_by_cluster.items()
                            },
                        ),
                        timing_suffix=str(iteration),
                    )
                    iteration_plans = self._repair_cluster_plans(
                        iteration_plans,
                        clusters=clusters,
                        iteration=iteration,
                        metadata=execution_metadata,
                    )
                    self._validate_cluster_plans(iteration_plans, clusters, iteration)
                    executable = self._drop_unsurfaced_query_references(
                        iteration_plans,
                        surfaced_by_cluster={
                            cluster_id: set(items)
                            for cluster_id, items in summaries_by_cluster.items()
                        },
                        metadata=execution_metadata,
                    )
                    clamped = self._clamp_iteration_plans(
                        executable,
                        self._config.consultation.max_queries_per_iteration,
                        execution_metadata,
                    )
                    plans.extend(clamped)
                    query_count = sum(len(item.plan.queries) for item in clamped)
                    self._progress_artifact(
                        progress,
                        ConsultationFailureStage.QUERY_PLANNING,
                        f"Repository zoom {iteration} planned",
                        f"Planned {query_count} bounded atlas queries.",
                        {
                            "iteration": iteration,
                            "query_plans": [item.model_dump(mode="json") for item in clamped],
                        },
                    )
                    self._progress_completed(
                        progress,
                        ConsultationFailureStage.QUERY_PLANNING,
                        f"Repository zoom {iteration} planned",
                    )
                    execution_metadata["zoom_iterations"] = iteration
                    if query_count == 0:
                        break
                    current_stage = ConsultationFailureStage.QUERY_EXECUTION
                    self._progress_started(
                        progress,
                        ConsultationFailureStage.QUERY_EXECUTION,
                        f"Inspecting repository evidence for zoom {iteration}",
                    )
                    for cluster_plan in clamped:
                        cluster_id = cluster_plan.cluster_id
                        for query_index, query in enumerate(cluster_plan.plan.queries, start=1):
                            result = self._timed(
                                stage_timings,
                                (f"query_execution.{iteration}.{cluster_id}.{query_index}"),
                                lambda query=query: self._queries.execute(resolved_atlas, query),
                            )
                            atlas_query_count += 1
                            execution_metadata["atlas_queries"] = atlas_query_count
                            self._accumulate_query_result(
                                cluster_id=cluster_id,
                                result=result,
                                nodes=nodes,
                                selected=selected_by_cluster,
                                summaries=summaries_by_cluster,
                                excerpts=excerpts_by_cluster,
                                relationships=relationships_by_cluster,
                                test_ids=test_ids_by_cluster,
                                excerpt_line_counts=excerpt_lines_by_cluster,
                                execution_metadata=execution_metadata,
                            )
                            self._progress_artifact(
                                progress,
                                ConsultationFailureStage.QUERY_EXECUTION,
                                "Repository evidence surfaced",
                                result.summary,
                                {
                                    "iteration": iteration,
                                    "cluster_id": cluster_id,
                                    "query": query.model_dump(mode="json"),
                                    "node_ids": result.node_ids,
                                    "metric_values": [
                                        item.model_dump(mode="json")
                                        for item in result.metric_values
                                    ],
                                    "relationship_count": len(result.relationships),
                                    "excerpt_count": len(result.excerpts),
                                },
                            )
                    self._progress_completed(
                        progress,
                        ConsultationFailureStage.QUERY_EXECUTION,
                        f"Repository zoom {iteration} completed",
                    )

            all_retrieved: dict[str, list[RetrievedPolicy]] = {}
            for cluster in clusters:
                current_stage = ConsultationFailureStage.POLICY_RETRIEVAL
                self._progress_started(
                    progress,
                    ConsultationFailureStage.POLICY_RETRIEVAL,
                    f"Retrieving policies for {cluster.title}",
                )
                force_lookup = {force.force_id: force for force in forces}
                cluster_query = self._policy_retrieval_query(
                    case=case,
                    cluster=cluster,
                    force_lookup=force_lookup,
                    atlas=resolved_atlas,
                    selected_node_ids=selected_by_cluster[cluster.cluster_id],
                )
                retrieved = self._timed(
                    stage_timings,
                    f"policy_retrieval.{cluster.cluster_id}",
                    lambda cluster_query=cluster_query: self._policies.retrieve(
                        cluster_query,
                        top_k=self._config.retrieval.top_k,
                        version_id=policy_version.version_id,
                        applicability=context.policy_applicability,
                    ),
                )
                all_retrieved[cluster.cluster_id] = retrieved
                retrieved_policy_count += len(retrieved)
                execution_metadata["retrieved_policies"] = retrieved_policy_count
                packet = self._build_packet(
                    case=case,
                    cluster=cluster,
                    atlas=resolved_atlas,
                    selected_ids=selected_by_cluster[cluster.cluster_id],
                    summaries=list(summaries_by_cluster[cluster.cluster_id].values()),
                    excerpts=excerpts_by_cluster[cluster.cluster_id],
                    relationships=list(relationships_by_cluster[cluster.cluster_id].values()),
                    test_ids=sorted(test_ids_by_cluster[cluster.cluster_id]),
                    policies=retrieved,
                    execution_metadata=execution_metadata,
                )
                packets.append(packet)
                self._progress_artifact(
                    progress,
                    ConsultationFailureStage.POLICY_RETRIEVAL,
                    f"Evidence packet ready: {cluster.title}",
                    (
                        f"{len(packet.node_summaries)} nodes, "
                        f"{len(packet.policies)} policies, "
                        f"{len(packet.excerpts)} excerpts."
                    ),
                    {"packet": packet.model_dump(mode="json")},
                )
                self._progress_completed(
                    progress,
                    ConsultationFailureStage.POLICY_RETRIEVAL,
                    f"Policies retrieved for {cluster.title}",
                )

                current_stage = ConsultationFailureStage.CONCERN_ANALYSIS
                self._progress_started(
                    progress,
                    ConsultationFailureStage.CONCERN_ANALYSIS,
                    f"Analyzing {cluster.title}",
                )
                analysis = self._reason(
                    ReasoningTask.ANALYZE_CONCERN_CLUSTER,
                    prompt_identities,
                    stage_timings,
                    lambda packet=packet: self._reasoning.analyze_concern_cluster(context, packet),
                    timing_suffix=cluster.cluster_id,
                )
                analysis = self._prepare_concern_analysis(
                    analysis,
                    packet=packet,
                    metadata=execution_metadata,
                )
                self._validate_concern_analysis(analysis, packet)
                analyses.append(analysis)
                self._progress_artifact(
                    progress,
                    ConsultationFailureStage.CONCERN_ANALYSIS,
                    f"Concern analyzed: {cluster.title}",
                    f"Produced {len(analysis.findings)} evidence-classified findings.",
                    {"analysis": analysis.model_dump(mode="json")},
                )
                self._progress_completed(
                    progress,
                    ConsultationFailureStage.CONCERN_ANALYSIS,
                    f"Analysis completed for {cluster.title}",
                )

            analyses = self._canonicalize_analysis_claim_ids(
                analyses,
                metadata=execution_metadata,
            )
            current_stage = ConsultationFailureStage.ALTERNATIVES
            self._progress_started(
                progress,
                ConsultationFailureStage.ALTERNATIVES,
                "Generating credible alternatives",
            )
            alternatives = self._reason(
                ReasoningTask.GENERATE_ALTERNATIVES,
                prompt_identities,
                stage_timings,
                lambda: self._reasoning.generate_alternatives(context, analyses),
            )
            self._progress_artifact(
                progress,
                ConsultationFailureStage.ALTERNATIVES,
                "Alternatives generated",
                f"Generated {len(alternatives)} credible options.",
                {"alternatives": [item.model_dump(mode="json") for item in alternatives]},
            )
            self._progress_completed(
                progress,
                ConsultationFailureStage.ALTERNATIVES,
                "Alternatives generated",
            )

            current_stage = ConsultationFailureStage.SCENARIOS
            self._progress_started(
                progress,
                ConsultationFailureStage.SCENARIOS,
                "Testing future scenarios",
            )
            scenarios = self._reason(
                ReasoningTask.EVALUATE_SCENARIOS,
                prompt_identities,
                stage_timings,
                lambda: self._reasoning.evaluate_scenarios(context, alternatives, analyses),
            )
            self._validate_scenario_coverage(scenarios, alternatives)
            self._progress_artifact(
                progress,
                ConsultationFailureStage.SCENARIOS,
                "Scenarios evaluated",
                f"Compared every alternative across {len(scenarios)} scenarios.",
                {"scenarios": [item.model_dump(mode="json") for item in scenarios]},
            )
            self._progress_completed(
                progress,
                ConsultationFailureStage.SCENARIOS,
                "Scenario evaluation completed",
            )

            current_stage = ConsultationFailureStage.SYNTHESIS
            self._progress_started(
                progress,
                ConsultationFailureStage.SYNTHESIS,
                "Synthesizing recommendation",
            )
            report = self._reason(
                ReasoningTask.SYNTHESIZE_RECOMMENDATION,
                prompt_identities,
                stage_timings,
                lambda: self._reasoning.synthesize_recommendation(
                    case,
                    context,
                    forces,
                    clusters,
                    analyses,
                    alternatives,
                    scenarios,
                    packets,
                ),
            )
            provider_repairs = self._reasoning.consume_repair_actions()
            output_repairs = execution_metadata.get("model_output_repairs")
            if isinstance(output_repairs, list):
                output_repairs.extend(provider_repairs)
                report, synthesis_repairs = self._restore_synthesis_artifacts(
                    report,
                    forces=forces,
                    alternatives=alternatives,
                    scenarios=scenarios,
                    packets=packets,
                )
                output_repairs.extend(synthesis_repairs)
            try:
                canonical_findings = canonicalize_report_findings(
                    report,
                    packets=packets,
                    analyses=analyses,
                )
            except ValueError as exc:
                raise ModelOutputValidationError(
                    f"Final synthesis finding evidence is inconsistent: {exc}"
                ) from exc
            report = canonical_findings.report
            finding_evidence_by_cluster = canonical_findings.evidence_by_cluster
            if isinstance(output_repairs, list):
                output_repairs.extend(canonical_findings.actions)
            unrepaired_report = report
            self._validate_synthesis_coverage(
                report,
                forces,
                alternatives,
                packets,
            )
            self._progress_artifact(
                progress,
                ConsultationFailureStage.SYNTHESIS,
                "Recommendation synthesized",
                report.decision_summary.text,
                {
                    "disposition": report.disposition,
                    "confidence": report.confidence.model_dump(mode="json"),
                },
            )
            self._progress_completed(
                progress,
                ConsultationFailureStage.SYNTHESIS,
                "Recommendation synthesized",
            )

            current_stage = ConsultationFailureStage.VALIDATION
            self._progress_started(
                progress,
                ConsultationFailureStage.VALIDATION,
                "Validating evidence references",
            )
            allowed_nodes = self._allowed_nodes(resolved_atlas, packets)
            allowed_policy_ids = {
                item.policy.id for retrieved in all_retrieved.values() for item in retrieved
            }
            initial_errors = validate_report_evidence(
                report,
                allowed_nodes=allowed_nodes,
                allowed_policy_ids=allowed_policy_ids,
                finding_evidence_by_cluster=finding_evidence_by_cluster,
            )
            final_errors = list(initial_errors)
            if initial_errors:
                repaired = repair_report_evidence_with_history(
                    report,
                    allowed_nodes=allowed_nodes,
                    allowed_policy_ids=allowed_policy_ids,
                    finding_evidence_by_cluster=finding_evidence_by_cluster,
                )
                repaired_findings = canonicalize_report_findings(
                    repaired.report,
                    packets=packets,
                    analyses=analyses,
                )
                report = repaired_findings.report
                repair_actions = repaired.actions
                if isinstance(output_repairs, list):
                    output_repairs.extend(repaired_findings.actions)
                final_errors = validate_report_evidence(
                    report,
                    allowed_nodes=allowed_nodes,
                    allowed_policy_ids=allowed_policy_ids,
                    finding_evidence_by_cluster=finding_evidence_by_cluster,
                )
                try:
                    self._validate_synthesis_coverage(
                        report,
                        forces,
                        alternatives,
                        packets,
                    )
                except ModelOutputValidationError as exc:
                    final_errors.append(str(exc))
            if final_errors:
                raise EvidenceReferenceError(
                    "Recommendation evidence validation failed: " + "; ".join(final_errors)
                )
            self._progress_artifact(
                progress,
                ConsultationFailureStage.VALIDATION,
                "Evidence validation completed",
                (
                    "The report passed validation without repair."
                    if not initial_errors
                    else f"Applied {len(repair_actions)} deterministic repair actions."
                ),
                {
                    "initial_errors": initial_errors,
                    "repair_actions": repair_actions,
                    "final_errors": final_errors,
                },
            )
            self._progress_completed(
                progress,
                ConsultationFailureStage.VALIDATION,
                "Evidence validated",
            )

            current_stage = ConsultationFailureStage.RENDERING
            self._progress_started(
                progress,
                ConsultationFailureStage.RENDERING,
                "Rendering report",
            )
            markdown = self._timed(stage_timings, "rendering", lambda: render_markdown(report))
            run = ConsultationRun(
                schema_version=3,
                run_id=consultation_run_id,
                status=ConsultationStatus.SUCCEEDED,
                case_id=case.case_id,
                input_case_revision=revision.revision,
                result_case_revision=revision.revision + 1,
                atlas_version_id=(resolved_atlas.version.version_id if resolved_atlas else None),
                policy_index_version_id=policy_version.version_id,
                reasoning_model=self._reasoning.model_identity,
                embedding_model=policy_version.embedding_model,
                config_hash=self._config.identity_hash,
                prompt_identities=prompt_identities,
                design_forces=forces,
                clusters=clusters,
                query_plans=plans,
                focused_packets=packets,
                concern_analyses=analyses,
                alternatives=alternatives,
                scenarios=scenarios,
                report=report,
                markdown_report=markdown,
                initial_validation_errors=initial_errors,
                repair_actions=repair_actions,
                final_validation_errors=[],
                stage_timings=stage_timings,
                started_at=started,
                completed_at=utc_now(),
                execution_metadata=execution_metadata,  # type: ignore[arg-type]
            )
            self._progress_completed(
                progress,
                ConsultationFailureStage.RENDERING,
                "Report rendered",
            )
            updated_case = self._updated_case(
                case,
                run=run,
                atlas=resolved_atlas,
                report=report,
                advisor_forces=advisor_forces,
                alternatives=alternatives,
                analyses=analyses,
            )
            current_stage = ConsultationFailureStage.COMMIT
            self._progress_started(
                progress,
                ConsultationFailureStage.COMMIT,
                "Saving immutable run and case revision",
            )
            self._timed(
                stage_timings,
                "commit",
                lambda: self._commits.commit_success(
                    run, updated_case, expected_revision=revision.revision
                ),
            )
            self._progress_completed(
                progress,
                ConsultationFailureStage.COMMIT,
                "Run and case revision saved",
            )
            self._progress_emit(
                progress,
                event_type=ProgressEventType.COMPLETED,
                stage=ConsultationFailureStage.COMMIT,
                title="Consultation completed",
                summary=report.decision_summary.text,
                data=cast(
                    dict[str, JsonValue],
                    {
                        "run_id": run.run_id,
                        "report_id": report.report_id,
                        "disposition": report.disposition,
                        "result_case_revision": run.result_case_revision,
                    },
                ),
            )
            return run
        except Exception as error:
            sanitized_error = self._sanitize_error(error, resolved_atlas)
            failure_diagnostics = (
                error.diagnostics if isinstance(error, ClusterPartitionError) else []
            )
            failed = ConsultationRun(
                schema_version=3,
                run_id=consultation_run_id,
                status=ConsultationStatus.FAILED,
                case_id=case.case_id,
                input_case_revision=revision.revision,
                atlas_version_id=(resolved_atlas.version.version_id if resolved_atlas else None),
                policy_index_version_id=(policy_version.version_id if policy_version else None),
                reasoning_model=self._reasoning.model_identity,
                embedding_model=(
                    policy_version.embedding_model
                    if policy_version
                    else self._config.models.embedding.model
                ),
                config_hash=self._config.identity_hash,
                prompt_identities=prompt_identities,
                design_forces=forces,
                clusters=clusters,
                query_plans=plans,
                focused_packets=packets,
                concern_analyses=analyses,
                alternatives=alternatives,
                scenarios=scenarios,
                report=unrepaired_report if final_errors else report,
                markdown_report=markdown,
                initial_validation_errors=initial_errors,
                repair_actions=repair_actions,
                final_validation_errors=final_errors,
                stage_timings=stage_timings,
                failure_stage=current_stage,
                sanitized_errors=[sanitized_error],
                failure_diagnostics=failure_diagnostics,
                started_at=started,
                completed_at=utc_now(),
                execution_metadata=execution_metadata,  # type: ignore[arg-type]
            )
            # Failure persistence is deliberately outside another catch. If it
            # fails, persistence is the unavoidable terminal exception.
            self._runs.save(failed)
            with suppress(Exception):
                self._progress_emit(
                    progress,
                    event_type=ProgressEventType.FAILED,
                    stage=current_stage,
                    title="Consultation failed",
                    summary=sanitized_error,
                    data={
                        "failure_diagnostics": [
                            item.model_dump(mode="json") for item in failure_diagnostics
                        ]
                    },
                )
            raise

    def _progress_started(
        self,
        progress: ConsultationProgressSink | None,
        stage: ConsultationFailureStage,
        title: str,
    ) -> None:
        self._progress_emit(
            progress,
            event_type=ProgressEventType.STAGE_STARTED,
            stage=stage,
            title=title,
        )

    def _progress_artifact(
        self,
        progress: ConsultationProgressSink | None,
        stage: ConsultationFailureStage,
        title: str,
        summary: str,
        data: dict[str, object],
    ) -> None:
        self._progress_emit(
            progress,
            event_type=ProgressEventType.ARTIFACT_AVAILABLE,
            stage=stage,
            title=title,
            summary=summary,
            data=cast(dict[str, JsonValue], data),
        )

    def _progress_completed(
        self,
        progress: ConsultationProgressSink | None,
        stage: ConsultationFailureStage,
        title: str,
    ) -> None:
        self._progress_emit(
            progress,
            event_type=ProgressEventType.STAGE_COMPLETED,
            stage=stage,
            title=title,
        )

    @staticmethod
    def _progress_emit(
        progress: ConsultationProgressSink | None,
        *,
        event_type: ProgressEventType,
        stage: ConsultationFailureStage,
        title: str,
        summary: str = "",
        data: dict[str, JsonValue] | None = None,
    ) -> None:
        if progress is None:
            return
        progress.emit(
            event_type=event_type,
            stage=stage,
            title=title,
            summary=summary,
            data=data,
        )

    def _resolve_atlas(
        self,
        case: ArchitectureCase,
        *,
        atlas_version_id: str | None,
        repository_root: Path | None,
    ) -> Atlas | None:
        if repository_root is not None:
            atlas = self._atlases.latest_for_path(repository_root)
            if atlas is None:
                raise AtlasNotFoundError(f"No indexed atlas exists for {repository_root.resolve()}")
            return atlas
        if atlas_version_id is not None:
            return self._atlases.get(atlas_version_id)
        if case.repository is None:
            return None
        if case.repository.atlas_version_id is not None:
            atlas = self._atlases.get(case.repository.atlas_version_id)
            if Path(atlas.version.root_path).resolve() != (
                Path(case.repository.root_path).expanduser().resolve()
            ):
                raise AtlasNotFoundError(
                    "The case atlas version does not belong to its recorded repository"
                )
            return atlas
        atlas = self._atlases.latest_for_path(Path(case.repository.root_path))
        if atlas is None:
            raise AtlasNotFoundError(f"No indexed atlas exists for {case.repository.root_path}")
        return atlas

    def _reason(
        self,
        task: ReasoningTask,
        prompt_identities: list[str],
        timings: dict[str, float],
        operation: Callable[[], Result],
        *,
        timing_suffix: str | None = None,
    ) -> Result:
        prompt_identities.append(self._reasoning.prompt_identity(task))
        timing_key = task.value if timing_suffix is None else f"{task.value}.{timing_suffix}"
        return self._timed(timings, timing_key, operation)

    @staticmethod
    def _timed(timings: dict[str, float], key: str, operation: Callable[[], Result]) -> Result:
        before = perf_counter()
        try:
            return operation()
        finally:
            timings[key] = timings.get(key, 0.0) + (perf_counter() - before)

    @staticmethod
    def _validate_cluster_plans(
        plans: list[ClusterQueryPlan],
        clusters: list[ConcernCluster],
        iteration: int,
    ) -> None:
        expected = {cluster.cluster_id for cluster in clusters}
        actual = [plan.cluster_id for plan in plans]
        if set(actual) != expected or len(actual) != len(set(actual)):
            raise ModelOutputValidationError(
                "Cluster query plans must contain exactly one plan per concern cluster"
            )
        if any(item.plan.iteration != iteration for item in plans):
            raise ModelOutputValidationError(
                "Cluster query plan iteration does not match the requested iteration"
            )

    @staticmethod
    def _repair_cluster_plans(
        plans: list[ClusterQueryPlan],
        *,
        clusters: list[ConcernCluster],
        iteration: int,
        metadata: dict[str, object],
    ) -> list[ClusterQueryPlan]:
        expected = {cluster.cluster_id for cluster in clusters}
        accepted: dict[str, ClusterQueryPlan] = {}
        repairs = metadata.get("query_plan_repairs")

        def record(repair: dict[str, object]) -> None:
            if isinstance(repairs, list):
                repairs.append(repair)

        for item in plans:
            if item.cluster_id not in expected:
                record(
                    {
                        "kind": "dropped_unknown_cluster_plan",
                        "cluster_id": item.cluster_id,
                        "iteration": iteration,
                        "plan": item.model_dump(mode="json"),
                    }
                )
                continue
            if item.cluster_id in accepted:
                record(
                    {
                        "kind": "dropped_duplicate_cluster_plan",
                        "cluster_id": item.cluster_id,
                        "iteration": iteration,
                        "plan": item.model_dump(mode="json"),
                    }
                )
                continue
            if item.plan.iteration != iteration:
                record(
                    {
                        "kind": "corrected_query_plan_iteration",
                        "cluster_id": item.cluster_id,
                        "from_iteration": item.plan.iteration,
                        "to_iteration": iteration,
                    }
                )
                item = item.model_copy(
                    update={"plan": item.plan.model_copy(update={"iteration": iteration})}
                )
            accepted[item.cluster_id] = item

        normalized: list[ClusterQueryPlan] = []
        for cluster in clusters:
            item = accepted.get(cluster.cluster_id)
            if item is None:
                record(
                    {
                        "kind": "added_empty_cluster_plan",
                        "cluster_id": cluster.cluster_id,
                        "iteration": iteration,
                    }
                )
                item = ClusterQueryPlan(
                    cluster_id=cluster.cluster_id,
                    plan=AtlasQueryPlan(
                        iteration=iteration,
                        rationale="The model omitted this cluster; no atlas queries were executed.",
                        queries=[],
                    ),
                )
            normalized.append(item)
        return normalized

    @staticmethod
    def _clamp_iteration_plans(
        plans: list[ClusterQueryPlan],
        budget: int,
        metadata: dict[str, object],
    ) -> list[ClusterQueryPlan]:
        accepted: dict[str, list[AtlasQuery]] = {item.cluster_id: [] for item in plans}
        next_index = {item.cluster_id: 0 for item in plans}
        remaining = budget
        while remaining:
            progressed = False
            for item in plans:
                index = next_index[item.cluster_id]
                if index >= len(item.plan.queries):
                    continue
                accepted[item.cluster_id].append(item.plan.queries[index])
                next_index[item.cluster_id] = index + 1
                remaining -= 1
                progressed = True
                if remaining == 0:
                    break
            if not progressed:
                break

        clamped: list[ClusterQueryPlan] = []
        for item in plans:
            queries = accepted[item.cluster_id]
            dropped = len(item.plan.queries) - len(queries)
            if dropped:
                truncations = metadata["truncations"]
                if isinstance(truncations, list):
                    truncations.append(
                        {
                            "kind": "query_budget",
                            "cluster_id": item.cluster_id,
                            "iteration": item.plan.iteration,
                            "dropped": dropped,
                        }
                    )
            clamped.append(
                item.model_copy(update={"plan": item.plan.model_copy(update={"queries": queries})})
            )
        return clamped

    @staticmethod
    def _drop_unsurfaced_query_references(
        plans: list[ClusterQueryPlan],
        *,
        surfaced_by_cluster: dict[str, set[str]],
        metadata: dict[str, object],
    ) -> list[ClusterQueryPlan]:
        repaired: list[ClusterQueryPlan] = []
        repairs = metadata.get("query_plan_repairs")
        for item in plans:
            allowed = surfaced_by_cluster.get(item.cluster_id, set())
            queries = []
            for query in item.plan.queries:
                referenced = {
                    value
                    for field in ("node_id", "source_id", "target_id")
                    if isinstance((value := getattr(query, field, None)), str)
                }
                unknown = sorted(referenced - allowed)
                if unknown:
                    if isinstance(repairs, list):
                        repairs.append(
                            {
                                "kind": "dropped_unsurfaced_node_query",
                                "cluster_id": item.cluster_id,
                                "iteration": item.plan.iteration,
                                "unknown_node_ids": unknown,
                                "query": query.model_dump(mode="json"),
                            }
                        )
                    continue
                queries.append(query)
            repaired.append(
                item.model_copy(update={"plan": item.plan.model_copy(update={"queries": queries})})
            )
        return repaired

    def _accumulate_query_result(
        self,
        *,
        cluster_id: str,
        result: AtlasQueryResult,
        nodes: dict[str, AtlasNode],
        selected: dict[str, list[str]],
        summaries: dict[str, dict[str, FocusedNodeSummary]],
        excerpts: dict[str, list[SourceExcerpt]],
        relationships: dict[str, dict[str, AtlasEdge]],
        test_ids: dict[str, set[str]],
        excerpt_line_counts: dict[str, int],
        execution_metadata: dict[str, object],
    ) -> None:
        selected_ids = selected[cluster_id]
        returned_summaries = {summary.node_id: summary for summary in result.node_summaries}
        reasons = self._selection_reasons(result)
        for node_id in result.node_ids:
            if node_id in selected_ids:
                existing = summaries[cluster_id].get(node_id)
                if existing is not None:
                    merged = {
                        reason.model_dump_json(): reason
                        for reason in [
                            *existing.selection_reasons,
                            *reasons.get(node_id, []),
                        ]
                    }
                    summaries[cluster_id][node_id] = existing.model_copy(
                        update={"selection_reasons": list(merged.values())}
                    )
                continue
            if len(selected_ids) >= self._config.consultation.max_query_results:
                self._record_truncation(
                    execution_metadata,
                    kind="node_budget",
                    cluster_id=cluster_id,
                    dropped=1,
                )
                continue
            node = nodes.get(node_id)
            if node is None:
                continue
            selected_ids.append(node_id)
            returned = returned_summaries.get(node_id)
            summaries[cluster_id][node_id] = (
                FocusedNodeSummary.from_summary(
                    returned,
                    summary=result.summary,
                    selection_reasons=reasons.get(node_id, []),
                )
                if returned is not None
                else FocusedNodeSummary.from_node(
                    node,
                    summary=result.summary,
                ).model_copy(update={"selection_reasons": reasons.get(node_id, [])})
            )

        relationship_limit = self._config.consultation.max_query_results * 4
        cluster_relationships = relationships[cluster_id]
        for edge in result.relationships:
            if edge.edge_id in cluster_relationships:
                continue
            if len(cluster_relationships) >= relationship_limit:
                self._record_truncation(
                    execution_metadata,
                    kind="relationship_budget",
                    cluster_id=cluster_id,
                    dropped=1,
                )
                continue
            cluster_relationships[edge.edge_id] = edge
        remaining_tests = self._config.consultation.max_query_results - len(test_ids[cluster_id])
        if remaining_tests > 0:
            test_ids[cluster_id].update(result.test_ids[:remaining_tests])
        if len(result.test_ids) > max(remaining_tests, 0):
            self._record_truncation(
                execution_metadata,
                kind="test_evidence_budget",
                cluster_id=cluster_id,
                dropped=len(result.test_ids) - max(remaining_tests, 0),
            )

        for excerpt in result.excerpts:
            if excerpt.node_id not in selected_ids:
                continue
            remaining = (
                self._config.consultation.max_excerpt_lines - excerpt_line_counts[cluster_id]
            )
            if remaining <= 0:
                self._record_truncation(
                    execution_metadata,
                    kind="excerpt_budget",
                    cluster_id=cluster_id,
                    dropped=len(excerpt.text.splitlines()),
                )
                continue
            lines = excerpt.text.splitlines()
            kept_lines = lines[:remaining]
            if len(kept_lines) < len(lines):
                self._record_truncation(
                    execution_metadata,
                    kind="excerpt_budget",
                    cluster_id=cluster_id,
                    dropped=len(lines) - len(kept_lines),
                )
            if not kept_lines:
                continue
            location = SourceLocation(
                path=excerpt.location.path,
                start_line=excerpt.location.start_line,
                end_line=excerpt.location.start_line + len(kept_lines) - 1,
            )
            excerpts[cluster_id].append(
                excerpt.model_copy(update={"location": location, "text": "\n".join(kept_lines)})
            )
            excerpt_line_counts[cluster_id] += len(kept_lines)

    @staticmethod
    def _selection_reasons(
        result: AtlasQueryResult,
    ) -> dict[str, list[AtlasSelectionReason]]:
        reason_kind = {
            "repository_summary": AtlasSelectionReasonKind.OVERVIEW,
            "subsystem_summary": AtlasSelectionReasonKind.RELATION,
            "node_details": AtlasSelectionReasonKind.EXPLICIT_DETAILS,
            "direct_dependencies": AtlasSelectionReasonKind.RELATION,
            "direct_dependants": AtlasSelectionReasonKind.RELATION,
            "known_callers": AtlasSelectionReasonKind.RELATION,
            "implementations": AtlasSelectionReasonKind.RELATION,
            "related_tests": AtlasSelectionReasonKind.RELATION,
            "forward_neighbourhood": AtlasSelectionReasonKind.NEIGHBOURHOOD,
            "reverse_neighbourhood": AtlasSelectionReasonKind.NEIGHBOURHOOD,
            "shortest_dependency_path": AtlasSelectionReasonKind.PATH,
            "cyclic_components": AtlasSelectionReasonKind.CYCLE,
            "signals": AtlasSelectionReasonKind.SIGNAL,
            "hotspots": AtlasSelectionReasonKind.METRIC_RANK,
            "search_nodes": AtlasSelectionReasonKind.NAME_MATCH,
            "source_excerpt": AtlasSelectionReasonKind.EXCERPT,
        }[result.query.kind]
        metric_by_node = {observation.node_id: observation for observation in result.metric_values}
        related_node_id = next(
            (
                value
                for field in ("node_id", "source_id")
                if isinstance((value := getattr(result.query, field, None)), str)
            ),
            None,
        )
        reasons: dict[str, list[AtlasSelectionReason]] = {}
        for node_id in result.node_ids:
            metric = metric_by_node.get(node_id)
            if metric is not None and metric.rank is not None:
                explanation = (
                    f"rank {metric.rank} by {metric.metric}={metric.value}; {metric.definition}"
                )
            else:
                explanation = result.summary or (
                    f"Selected by {result.query.kind.replace('_', ' ')}"
                )
            reasons[node_id] = [
                AtlasSelectionReason(
                    kind=reason_kind,
                    explanation=explanation,
                    metric=metric.metric if metric is not None else None,
                    related_node_id=(
                        related_node_id
                        if related_node_id is not None and related_node_id != node_id
                        else None
                    ),
                )
            ]
        return reasons

    @staticmethod
    def _record_truncation(
        metadata: dict[str, object],
        *,
        kind: str,
        cluster_id: str,
        dropped: int,
    ) -> None:
        truncations = metadata["truncations"]
        if isinstance(truncations, list):
            truncations.append(
                {
                    "kind": kind,
                    "cluster_id": cluster_id,
                    "dropped": dropped,
                }
            )

    @staticmethod
    def _policy_retrieval_query(
        *,
        case: ArchitectureCase,
        cluster: ConcernCluster,
        force_lookup: dict[str, DesignForce],
        atlas: Atlas | None,
        selected_node_ids: list[str],
    ) -> str:
        """Build a bounded policy query from case intent and surfaced evidence."""

        parts = [
            f"Concern: {cluster.title}",
            f"Investigation: {cluster.rationale}",
            f"Problem: {case.problem_statement}",
            f"Desired outcome: {case.desired_outcome}",
        ]
        for force_id in cluster.design_force_ids:
            if force := force_lookup.get(force_id):
                parts.append(f"Design force: {force.title}. {force.description}")
        for requirement in case.functional_requirements[:6]:
            parts.append(f"Requirement: {requirement}")
        for quality in case.quality_attributes[:6]:
            parts.append(f"Quality attribute: {quality}")
        for constraint in case.technical_constraints[:6]:
            parts.append(f"Technical constraint: {constraint}")
        for change in case.expected_future_changes[:6]:
            parts.append(f"Expected change: {change}")

        if atlas is not None:
            selected = set(selected_node_ids)
            signals = sorted(
                (
                    signal
                    for signal in atlas.signals
                    if signal.node_id in selected
                ),
                key=lambda signal: (signal.code, signal.node_id, signal.message),
            )
            for signal in signals[:8]:
                parts.append(
                    "Repository signal "
                    f"{signal.code}: {signal.message} "
                    f"Definition: {signal.definition or 'not supplied'}. "
                    f"Limitations: {signal.limitations or 'not supplied'}."
                )

        return "\n".join(parts)[:POLICY_QUERY_CHARACTER_BUDGET]

    @staticmethod
    def _build_packet(
        *,
        case: ArchitectureCase,
        cluster: ConcernCluster,
        atlas: Atlas | None,
        selected_ids: list[str],
        summaries: list[FocusedNodeSummary],
        excerpts: list[SourceExcerpt],
        relationships: list[AtlasEdge],
        test_ids: list[str],
        policies: list[RetrievedPolicy],
        execution_metadata: dict[str, object],
    ) -> FocusedAnalysisPacket:
        selected = set(selected_ids)
        metrics = (
            [profile for profile in atlas.metrics if profile.node_id in selected] if atlas else []
        )
        nodes = {node.atlas_id: node for node in atlas.nodes} if atlas else {}
        profiles = {profile.node_id: profile for profile in metrics}
        signals_by_node: dict[str, list[ObscuritySignal]] = {}
        if atlas:
            for signal in atlas.signals:
                if signal.node_id in selected:
                    signals_by_node.setdefault(signal.node_id, []).append(signal)
        node_evidence: list[AtlasNodeEvidence] = []
        for summary in summaries:
            node = nodes.get(summary.node_id)
            if node is None:
                continue
            profile = profiles.get(summary.node_id)
            node_evidence.append(
                AtlasNodeEvidence(
                    node=ConsultationWorkflow._atlas_node_summary(node),
                    reasons=summary.selection_reasons,
                    metrics=(salient_profile_observations(profile) if profile is not None else []),
                    signals=signals_by_node.get(summary.node_id, [])[:5],
                )
            )
        allowed_relationship_nodes = {*selected_ids, *test_ids}
        surfaced_relationships = [
            edge
            for edge in relationships
            if edge.source_id in allowed_relationship_nodes
            and edge.target_id in allowed_relationship_nodes
            and edge.source_id in nodes
            and edge.target_id in nodes
        ]
        dropped_relationships = len(relationships) - len(surfaced_relationships)
        if dropped_relationships:
            ConsultationWorkflow._record_truncation(
                execution_metadata,
                kind="relationship_endpoint_not_surfaced",
                cluster_id=cluster.cluster_id,
                dropped=dropped_relationships,
            )
        relationship_evidence = [
            AtlasRelationshipEvidence(
                edge_id=edge.edge_id,
                edge_type=edge.edge_type,
                source=ConsultationWorkflow._atlas_node_summary(nodes[edge.source_id]),
                target=ConsultationWorkflow._atlas_node_summary(nodes[edge.target_id]),
                confidence=edge.confidence,
                location=edge.location,
            )
            for edge in surfaced_relationships
        ]
        test_evidence = [
            ConsultationWorkflow._atlas_node_summary(nodes[node_id])
            for node_id in test_ids
            if node_id in nodes
        ]
        return FocusedAnalysisPacket(
            cluster=cluster,
            node_summaries=summaries,
            node_evidence=node_evidence,
            metrics=metrics,
            relationships=surfaced_relationships,
            relationship_evidence=relationship_evidence,
            test_ids=[item.node_id for item in test_evidence],
            test_evidence=test_evidence,
            excerpts=excerpts,
            policies=policies,
            assumptions=[item.text for item in case.assumptions],
            uncertainty=(
                ["Repository evidence is unavailable."]
                if atlas is None
                else [
                    "Static call resolution is conservative and runtime behavior is not observed."
                ]
            ),
        )

    @staticmethod
    def _canonicalize_analysis_claim_ids(
        analyses: list[ConcernAnalysis],
        *,
        metadata: dict[str, object],
    ) -> list[ConcernAnalysis]:
        """Make cluster-local claim identities unambiguous before synthesis."""
        occurrences = Counter(
            claim.claim_id
            for analysis in analyses
            for claim in analysis.findings
        )
        reserved_ids = {"none", "null", "n/a", "unknown"}
        used_ids = {
            claim_id
            for claim_id, count in occurrences.items()
            if count == 1 and claim_id.casefold() not in reserved_ids
        }
        repairs = metadata.get("model_output_repairs")
        updated_analyses: list[ConcernAnalysis] = []
        for analysis in analyses:
            findings = []
            changed = False
            for ordinal, claim in enumerate(analysis.findings, start=1):
                if (
                    occurrences[claim.claim_id] == 1
                    and claim.claim_id.casefold() not in reserved_ids
                ):
                    findings.append(claim)
                    continue
                serialized = canonical_json(
                    {
                        "cluster_id": analysis.cluster_id,
                        "ordinal": ordinal,
                        "claim": claim,
                    }
                )
                digest = sha256(serialized.encode("utf-8")).hexdigest()
                replacement = f"claim_{digest[:24]}"
                suffix = 24
                while replacement in used_ids:
                    suffix += 4
                    replacement = f"claim_{digest[:suffix]}"
                used_ids.add(replacement)
                findings.append(claim.model_copy(update={"claim_id": replacement}))
                changed = True
                if isinstance(repairs, list):
                    repairs.append(
                        {
                            "kind": "reassigned_ambiguous_analysis_claim_id",
                            "cluster_id": analysis.cluster_id,
                            "from_claim_id": claim.claim_id,
                            "to_claim_id": replacement,
                        }
                    )
            updated_analyses.append(
                analysis.model_copy(update={"findings": findings})
                if changed
                else analysis
            )
        return updated_analyses

    @staticmethod
    def _prepare_concern_analysis(
        analysis: ConcernAnalysis,
        *,
        packet: FocusedAnalysisPacket,
        metadata: dict[str, object],
    ) -> ConcernAnalysis:
        updates: dict[str, object] = {}
        repairs = metadata.get("model_output_repairs")
        if analysis.cluster_id != packet.cluster.cluster_id:
            if isinstance(repairs, list):
                repairs.append(
                    {
                        "kind": "corrected_concern_analysis_cluster",
                        "from_cluster_id": analysis.cluster_id,
                        "to_cluster_id": packet.cluster.cluster_id,
                    }
                )
            updates["cluster_id"] = packet.cluster.cluster_id
        if analysis.concern != packet.cluster.title:
            if isinstance(repairs, list):
                repairs.append(
                    {
                        "kind": "corrected_concern_analysis_title",
                        "cluster_id": packet.cluster.cluster_id,
                        "from_concern": analysis.concern,
                        "to_concern": packet.cluster.title,
                    }
                )
            updates["concern"] = packet.cluster.title
        if updates:
            analysis = analysis.model_copy(update=updates)
        return ConsultationWorkflow._drop_unsupported_concern_evidence(
            analysis,
            packet=packet,
            metadata=metadata,
        )

    @staticmethod
    def _drop_unsupported_concern_evidence(
        analysis: ConcernAnalysis,
        *,
        packet: FocusedAnalysisPacket,
        metadata: dict[str, object],
    ) -> ConcernAnalysis:
        policy_ids = {item.policy.id for item in packet.policies}
        node_summaries = {summary.node_id: summary for summary in packet.node_summaries}
        findings = []
        repairs = metadata.get("model_output_repairs")
        pending_repairs: list[dict[str, object]] = []

        def record(kind: str, payload: dict[str, object]) -> None:
            pending_repairs.append({"kind": kind, **payload})

        for finding in analysis.findings:
            if finding.classification == ClaimClassification.REPOSITORY_OBSERVATION:
                supported = bool(finding.atlas_references) and all(
                    location_within(
                        _surfaced_span(node_summaries, reference.node_id),
                        reference.location,
                    )
                    for reference in finding.atlas_references
                )
                if not supported:
                    record(
                        "dropped_unsupported_repository_finding",
                        {
                            "cluster_id": packet.cluster.cluster_id,
                            "claim": finding.model_dump(mode="json"),
                        },
                    )
                    continue
            if finding.classification == ClaimClassification.POLICY_GUIDANCE and (
                not finding.policy_ids or not set(finding.policy_ids) <= policy_ids
            ):
                record(
                    "dropped_unsupported_policy_finding",
                    {
                        "cluster_id": packet.cluster.cluster_id,
                        "claim": finding.model_dump(mode="json"),
                    },
                )
                continue
            findings.append(finding)

        conflicts = []
        for conflict in analysis.policy_conflicts:
            if set(conflict.policy_ids) <= policy_ids:
                conflicts.append(conflict)
                continue
            record(
                "dropped_unsupported_policy_conflict",
                {
                    "cluster_id": packet.cluster.cluster_id,
                    "conflict": conflict.model_dump(mode="json"),
                },
            )

        if not findings:
            if isinstance(repairs, list) and pending_repairs:
                repairs.append(
                    {
                        "kind": "rejected_empty_concern_evidence_repair",
                        "cluster_id": packet.cluster.cluster_id,
                        "proposed_repairs": pending_repairs,
                    }
                )
            return analysis
        if isinstance(repairs, list):
            repairs.extend(pending_repairs)
        return analysis.model_copy(update={"findings": findings, "policy_conflicts": conflicts})

    @staticmethod
    def _validate_concern_analysis(
        analysis: ConcernAnalysis, packet: FocusedAnalysisPacket
    ) -> None:
        if analysis.cluster_id != packet.cluster.cluster_id:
            raise ModelOutputValidationError(
                "Concern analysis does not reference its input cluster"
            )
        policy_ids = {item.policy.id for item in packet.policies}
        node_summaries = {summary.node_id: summary for summary in packet.node_summaries}
        for finding in analysis.findings:
            if finding.classification == ClaimClassification.REPOSITORY_OBSERVATION:
                if not finding.atlas_references:
                    raise ModelOutputValidationError(
                        "Repository findings require a surfaced atlas node and source location"
                    )
                for reference in finding.atlas_references:
                    if not location_within(
                        _surfaced_span(node_summaries, reference.node_id),
                        reference.location,
                    ):
                        raise ModelOutputValidationError(
                            "Repository finding has an invalid or unsurfaced source location"
                        )
            if finding.classification == ClaimClassification.POLICY_GUIDANCE and (
                not finding.policy_ids or not set(finding.policy_ids) <= policy_ids
            ):
                raise ModelOutputValidationError("Policy guidance finding invented a policy ID")
        for conflict in analysis.policy_conflicts:
            if not set(conflict.policy_ids) <= policy_ids:
                raise ModelOutputValidationError(
                    "Concern analysis invented a policy ID in a conflict"
                )

    @staticmethod
    def _validate_scenario_coverage(
        scenarios: list[ScenarioEvaluation], alternatives: list[CaseAlternative]
    ) -> None:
        expected = {alternative.id for alternative in alternatives}
        for scenario in scenarios:
            actual = set(scenario.alternative_results)
            if actual != expected:
                raise ModelOutputValidationError(
                    "Every scenario must evaluate every alternative exactly once"
                )

    @staticmethod
    def _restore_synthesis_artifacts(
        report: RecommendationReport,
        *,
        forces: list[DesignForce],
        alternatives: list[CaseAlternative],
        scenarios: list[ScenarioEvaluation],
        packets: list[FocusedAnalysisPacket],
    ) -> tuple[RecommendationReport, list[dict[str, object]]]:
        """Restore validated upstream artifacts that synthesis may only reproduce."""
        canonical = {
            "important_design_forces": forces,
            "alternatives_considered": alternatives,
            "scenario_analysis": scenarios,
        }
        updates: dict[str, object] = {}
        actions: list[dict[str, object]] = []
        for field, expected in canonical.items():
            actual = getattr(report, field)
            if actual == expected:
                continue
            updates[field] = expected
            actions.append(
                {
                    "kind": "restored_canonical_synthesis_artifact",
                    "field": field,
                    "model_output": [item.model_dump(mode="json") for item in actual],
                    "canonical_input": [item.model_dump(mode="json") for item in expected],
                }
            )
        canonical_policy_by_id = {
            summary.id: summary
            for summary in canonical_policy_evidence(
                item for packet in packets for item in packet.policies
            )
        }
        policy_evidence: list[PolicyEvidenceSummary] = []
        policy_evidence_changed = False
        for summary in report.policy_evidence:
            expected_summary = canonical_policy_by_id.get(summary.id)
            if expected_summary is None:
                policy_evidence.append(summary)
                continue
            policy_evidence.append(expected_summary)
            if summary == expected_summary:
                continue
            policy_evidence_changed = True
            actions.append(
                {
                    "kind": "restored_canonical_policy_evidence",
                    "policy_id": summary.id,
                    "model_output": summary.model_dump(mode="json"),
                    "canonical_input": expected_summary.model_dump(mode="json"),
                }
            )
        if policy_evidence_changed:
            updates["policy_evidence"] = policy_evidence
        if not updates:
            return report, actions
        return report.model_copy(update=updates), actions

    @staticmethod
    def _validate_synthesis_coverage(
        report: RecommendationReport,
        forces: list[DesignForce],
        alternatives: list[CaseAlternative],
        packets: list[FocusedAnalysisPacket],
    ) -> None:
        if {force.force_id for force in report.important_design_forces} != {
            force.force_id for force in forces
        }:
            raise ModelOutputValidationError(
                "Final synthesis did not preserve the discovered design forces"
            )
        if {item.id for item in report.alternatives_considered} != {
            item.id for item in alternatives
        }:
            raise ModelOutputValidationError(
                "Final synthesis did not preserve the evaluated alternatives"
            )
        cluster_ids = {packet.cluster.cluster_id for packet in packets}
        finding_cluster_ids = {
            finding.concern_cluster_id
            for finding in report.findings
            if finding.concern_cluster_id is not None
        }
        if finding_cluster_ids != cluster_ids:
            raise ModelOutputValidationError(
                "Final synthesis must provide findings for every concern cluster"
            )
        expected_policy_evidence = {
            summary.id: summary
            for summary in canonical_policy_evidence(
                item for packet in packets for item in packet.policies
            )
        }
        for summary in report.policy_evidence:
            expected = expected_policy_evidence.get(summary.id)
            if expected is None:
                raise ModelOutputValidationError("Final synthesis invented a policy evidence ID")
            if summary != expected:
                raise ModelOutputValidationError(
                    f"Final synthesis altered canonical metadata for policy {summary.id}"
                )

    @staticmethod
    def _allowed_nodes(
        atlas: Atlas | None, packets: list[FocusedAnalysisPacket]
    ) -> dict[str, AtlasNode]:
        if atlas is None:
            return {}
        allowed_ids = {node_id for packet in packets for node_id in packet.surfaced_node_ids}
        return {node.atlas_id: node for node in atlas.nodes if node.atlas_id in allowed_ids}

    @staticmethod
    def _updated_case(
        case: ArchitectureCase,
        *,
        run: ConsultationRun,
        atlas: Atlas | None,
        report: RecommendationReport,
        advisor_forces: list[DesignForce],
        alternatives: list[CaseAlternative],
        analyses: list[ConcernAnalysis],
    ) -> ArchitectureCase:
        cited_policy_ids = {
            policy_id
            for claim in [
                *report.relevant_policies,
                *report.evidence_appendix,
            ]
            for policy_id in claim.policy_ids
        }
        cited_policy_ids.update(item.id for item in report.policy_evidence)
        cited_policy_ids.update(
            policy_id
            for conflict in [
                *report.policy_conflicts,
                *[conflict for analysis in analyses for conflict in analysis.policy_conflicts],
            ]
            for policy_id in conflict.policy_ids
        )
        return case.model_copy(
            update={
                "advisor_design_forces": [
                    CaseStatement(
                        id=force.force_id,
                        text=f"{force.title}: {force.description}",
                        kind=StatementKind.FORCE,
                        source=run.run_id,
                    )
                    for force in advisor_forces
                ],
                "repository": (
                    RepositoryReference(
                        root_path=atlas.version.root_path,
                        atlas_version_id=atlas.version.version_id,
                    )
                    if atlas
                    else case.repository
                ),
                "referenced_policy_ids": sorted(cited_policy_ids),
                "candidate_alternatives": alternatives,
                "current_recommendation": RecommendationState(
                    summary=report.decision_summary.text,
                    rationale=report.recommended_architecture.text,
                    run_id=run.run_id,
                    disposition=report.disposition,
                ),
                "confidence": Confidence.model_validate(report.confidence),
                "reversal_conditions": [item.text for item in report.reversal_conditions],
                "revisit_triggers": [item.text for item in report.revisit_triggers],
                "updated_at": utc_now(),
            }
        )

    @staticmethod
    def _sanitize_error(error: Exception, atlas: Atlas | None) -> str:
        if isinstance(error, ClusterPartitionError):
            message = str(error)
        elif isinstance(error, ModelOutputValidationError):
            detail = str(error)
            safe_synthesis_messages = {
                "Final synthesis did not preserve the discovered design forces",
                "Final synthesis did not preserve the evaluated alternatives",
                "Final synthesis must provide findings for every concern cluster",
                "Final synthesis invented a policy evidence ID",
            }
            message = (
                detail
                if detail in safe_synthesis_messages
                else "Structured model output failed validation"
            )
        else:
            message = " ".join(str(error).split())
        if atlas is not None:
            message = message.replace(atlas.version.root_path, "<repository>")
        message = re.sub(r"(?<![:\w])/[^\s;,)]+", "<path>", message)
        message = message[:500]
        return f"{type(error).__name__}: {message or 'operation failed'}"

    @staticmethod
    def _merge_user_design_forces(
        case: ArchitectureCase,
        advisor_forces: list[DesignForce],
    ) -> list[DesignForce]:
        user_forces: list[DesignForce] = []
        for statement in case.design_forces:
            raw_title, separator, raw_description = statement.text.partition(":")
            title = raw_title.strip() if separator else statement.text.strip()
            description = (
                raw_description.strip()
                if separator and raw_description.strip()
                else statement.text.strip()
            )
            user_forces.append(
                DesignForce(
                    force_id=statement.id,
                    title=title,
                    description=description,
                    importance="user-specified",
                )
            )
        used_ids = {force.force_id for force in user_forces}
        normalized_advisor_forces: list[DesignForce] = []
        for force in advisor_forces:
            normalized = force
            while normalized.force_id in used_ids:
                normalized = normalized.model_copy(update={"force_id": new_id("force")})
            used_ids.add(normalized.force_id)
            normalized_advisor_forces.append(normalized)
        return [*user_forces, *normalized_advisor_forces]

    @staticmethod
    def _atlas_node_summary(node: AtlasNode) -> AtlasNodeSummary:
        return AtlasNodeSummary(
            node_id=node.atlas_id,
            qualified_name=node.qualified_name,
            node_type=node.node_type,
            path=node.path,
            location=(
                SourceLocation(
                    path=node.path,
                    start_line=node.start_line,
                    end_line=node.end_line,
                )
                if node.start_line is not None and node.end_line is not None
                else None
            ),
            is_public=node.is_public,
        )

    @staticmethod
    def _atlas_overview(atlas: Atlas) -> AtlasOverview:
        root = next(
            (node for node in atlas.nodes if node.node_type == NodeType.REPOSITORY),
            None,
        )
        top_level = sorted(
            [node for node in atlas.nodes if root is not None and node.parent_id == root.atlas_id],
            key=lambda node: (node.node_type.value, node.qualified_name),
        )[:20]
        profiles = {profile.node_id: profile for profile in atlas.metrics}
        signals_by_node: dict[str, list[ObscuritySignal]] = {}
        for signal in atlas.signals:
            signals_by_node.setdefault(signal.node_id, []).append(signal)
        signal_priority = {
            "broad-input-boundary-preparation": 0,
            "parallel-boundary-preparation": 1,
            "cyclic-dependency": 2,
        }
        representative_signals: list[ObscuritySignal] = []
        signals_by_code: dict[str, list[ObscuritySignal]] = {}
        for signal in atlas.signals:
            signals_by_code.setdefault(signal.code, []).append(signal)
        for code in sorted(
            signals_by_code,
            key=lambda value: (signal_priority.get(value, 2), value),
        ):
            representative_signals.extend(
                sorted(
                    signals_by_code[code],
                    key=lambda signal: (signal.node_id, signal.message),
                )[:2]
            )
            if len(representative_signals) >= 20:
                break
        representative_signals = representative_signals[:20]

        candidate_types = {
            NodeType.MODULE,
            NodeType.TEST_MODULE,
            NodeType.CONFIGURATION,
            NodeType.CLASS,
            NodeType.INTERFACE,
        }

        def hotspot_values(node: AtlasNode) -> tuple[int, int, int, int]:
            profile = profiles.get(node.atlas_id)
            if profile is None:
                return (0, 0, 0, 0)
            return (
                profile.change_amplification.likely_affected_modules,
                profile.dependency.reverse_dependency_reach,
                profile.dependency.fan_out,
                profile.local.branch_count,
            )

        candidates = [
            node
            for node in atlas.nodes
            if node.node_type in candidate_types and any(hotspot_values(node))
        ]
        candidates.sort(
            key=lambda node: (
                *[-value for value in hotspot_values(node)],
                node.qualified_name,
                node.atlas_id,
            )
        )
        hotspots: list[AtlasNodeEvidence] = []
        metric_names = (
            "change_amplification.likely_affected_modules",
            "dependency.reverse_dependency_reach",
            "dependency.fan_out",
            "local.branch_count",
        )
        for node in candidates[:8]:
            profile = profiles[node.atlas_id]
            values = hotspot_values(node)
            selected_index = max(
                range(len(values)),
                key=lambda index: (values[index], -index),
            )
            metric_name = canonical_metric_name(metric_names[selected_index])
            hotspots.append(
                AtlasNodeEvidence(
                    node=ConsultationWorkflow._atlas_node_summary(node),
                    reasons=[
                        AtlasSelectionReason(
                            kind=AtlasSelectionReasonKind.METRIC_RANK,
                            explanation=(
                                f"Selected for elevated {metric_name}={values[selected_index]}."
                            ),
                            metric=metric_name,
                        )
                    ],
                    metrics=salient_profile_observations(profile),
                    signals=signals_by_node.get(node.atlas_id, [])[:5],
                )
            )
        return AtlasOverview(
            atlas_version_id=atlas.version.version_id,
            repository_identity=atlas.version.repository_identity,
            node_count=len(atlas.nodes),
            edge_count=len(atlas.edges),
            signal_count=len(atlas.signals),
            node_type_counts=dict(
                sorted(Counter(node.node_type.value for node in atlas.nodes).items())
            ),
            edge_type_counts=dict(
                sorted(Counter(edge.edge_type.value for edge in atlas.edges).items())
            ),
            signal_code_counts=dict(
                sorted(Counter(signal.code for signal in atlas.signals).items())
            ),
            signals=representative_signals,
            top_level_nodes=[ConsultationWorkflow._atlas_node_summary(node) for node in top_level],
            hotspots=hotspots,
            limitations=[
                "The atlas is derived from conservative static resolution; runtime dispatch "
                "and dynamic imports may be absent.",
                "Change-amplification and cognitive-scope values are structural proxies, "
                "not model interpretations or maintainability scores.",
                "Atlas signals are bounded static observations or explicitly labelled "
                "structural proxies; they identify investigation targets, not architecture "
                "violations.",
            ],
        )

    @staticmethod
    def _global_context(case: ArchitectureCase, atlas: Atlas | None) -> GlobalContext:
        return GlobalContext(
            case_id=case.case_id,
            revision=case.revision,
            title=case.title,
            problem=case.problem_statement,
            desired_outcome=case.desired_outcome,
            actors_and_workflows=case.actors_and_workflows,
            goals=[*case.functional_requirements, *case.quality_attributes],
            constraints=[
                *case.technical_constraints,
                *case.organisational_constraints,
                *[item.text for item in case.derived_constraints],
            ],
            future_changes=case.expected_future_changes,
            non_goals=case.non_goals,
            confirmed_facts=[item.text for item in case.confirmed_facts],
            assumptions=[item.text for item in case.assumptions],
            unresolved_questions=[item.text for item in case.unresolved_questions],
            user_design_forces=[item.text for item in case.design_forces],
            policy_applicability=PolicyApplicabilityContext(
                user=case.policy_applicability.user,
                organisation=case.policy_applicability.organisation,
                repository=(atlas.version.repository_identity if atlas is not None else None),
            ),
            atlas_overview=(
                ConsultationWorkflow._atlas_overview(atlas) if atlas is not None else None
            ),
            atlas_summary=(
                f"{len(atlas.nodes)} nodes, {len(atlas.edges)} edges, "
                f"{len(atlas.signals)} objective signals"
                if atlas
                else None
            ),
        )
