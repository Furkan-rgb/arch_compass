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
from typing import TypeVar

from archcompass.application.evidence import (
    canonicalize_report_findings,
    repair_report_evidence_with_history,
    validate_report_evidence,
)
from archcompass.application.reporting import render_markdown
from archcompass.application.synthesis import (
    ProposalCompositionError,
    build_claim_pool,
    compose_recommendation,
    proposal_content_hash,
    validate_proposal,
)
from archcompass.configuration import AppConfig
from archcompass.domain.atlas import (
    Atlas,
    AtlasEdge,
    AtlasNode,
    SourceExcerpt,
    SourceLocation,
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
from archcompass.domain.policy import (
    PolicyApplicabilityContext,
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
from archcompass.workflows.evidence_accumulation import (
    accumulate_query_result,
    atlas_overview,
    build_packet,
)
from archcompass.workflows.query_plans import (
    clamp_iteration_plans,
    drop_unsurfaced_query_references,
    repair_cluster_plans,
    validate_cluster_plans,
)
from archcompass.workflows.stage_progress import StageProgress

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
        stages = StageProgress(progress)
        resolved_atlas: Atlas | None = None
        policy_version: PolicyIndexVersion | None = None

        try:
            stages.begin(
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
            stages.artifact(
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
            stages.finish(
                "Repository context prepared",
            )
            stages.begin(
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
            stages.artifact(
                "Policy index ready",
                f"Using immutable policy index {policy_version.version_id}.",
                {
                    "policy_index_version_id": policy_version.version_id,
                    "embedding_model": policy_version.embedding_model,
                },
            )
            stages.finish(
                "Policy corpus prepared",
            )
            context = self._global_context(case, resolved_atlas)

            stages.begin(
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
            stages.artifact(
                "Design forces discovered",
                f"Found {len(forces)} forces shaping this decision.",
                {"design_forces": [item.model_dump(mode="json") for item in forces]},
            )
            stages.finish(
                "Design forces discovered",
            )

            stages.begin(
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
            stages.artifact(
                "Concern clusters formed",
                f"Organized the forces into {len(clusters)} focused clusters.",
                {"clusters": [item.model_dump(mode="json") for item in clusters]},
            )
            stages.finish(
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
                    stages.begin(
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
                    iteration_plans = repair_cluster_plans(
                        iteration_plans,
                        clusters=clusters,
                        iteration=iteration,
                        metadata=execution_metadata,
                    )
                    validate_cluster_plans(iteration_plans, clusters, iteration)
                    executable = drop_unsurfaced_query_references(
                        iteration_plans,
                        surfaced_by_cluster={
                            cluster_id: set(items)
                            for cluster_id, items in summaries_by_cluster.items()
                        },
                        metadata=execution_metadata,
                    )
                    clamped = clamp_iteration_plans(
                        executable,
                        self._config.consultation.max_queries_per_iteration,
                        execution_metadata,
                    )
                    plans.extend(clamped)
                    query_count = sum(len(item.plan.queries) for item in clamped)
                    stages.artifact(
                        f"Repository zoom {iteration} planned",
                        f"Planned {query_count} bounded atlas queries.",
                        {
                            "iteration": iteration,
                            "query_plans": [item.model_dump(mode="json") for item in clamped],
                        },
                    )
                    stages.finish(
                f"Repository zoom {iteration} planned",
            )
                    execution_metadata["zoom_iterations"] = iteration
                    if query_count == 0:
                        break
                    stages.begin(
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
                            accumulate_query_result(
                                self._config.consultation,
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
                            stages.artifact(
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
                    stages.finish(
                f"Repository zoom {iteration} completed",
            )

            all_retrieved: dict[str, list[RetrievedPolicy]] = {}
            for cluster in clusters:
                stages.begin(
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
                packet = build_packet(
                    self._config.consultation,
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
                stages.artifact(
                    f"Evidence packet ready: {cluster.title}",
                    (
                        f"{len(packet.node_summaries)} nodes, "
                        f"{len(packet.policies)} policies, "
                        f"{len(packet.excerpts)} excerpts."
                    ),
                    {"packet": packet.model_dump(mode="json")},
                )
                stages.finish(
                f"Policies retrieved for {cluster.title}",
            )

                stages.begin(
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
                stages.artifact(
                    f"Concern analyzed: {cluster.title}",
                    f"Produced {len(analysis.findings)} evidence-classified findings.",
                    {"analysis": analysis.model_dump(mode="json")},
                )
                stages.finish(
                f"Analysis completed for {cluster.title}",
            )

            analyses = self._canonicalize_analysis_claim_ids(
                analyses,
                metadata=execution_metadata,
            )
            stages.begin(
                ConsultationFailureStage.ALTERNATIVES,
                "Generating credible alternatives",
            )
            alternatives = self._reason(
                ReasoningTask.GENERATE_ALTERNATIVES,
                prompt_identities,
                stage_timings,
                lambda: self._reasoning.generate_alternatives(context, analyses),
            )
            stages.artifact(
                "Alternatives generated",
                f"Generated {len(alternatives)} credible options.",
                {"alternatives": [item.model_dump(mode="json") for item in alternatives]},
            )
            stages.finish(
                "Alternatives generated",
            )

            stages.begin(
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
            stages.artifact(
                "Scenarios evaluated",
                f"Compared every alternative across {len(scenarios)} scenarios.",
                {"scenarios": [item.model_dump(mode="json") for item in scenarios]},
            )
            stages.finish(
                "Scenario evaluation completed",
            )

            stages.begin(
                ConsultationFailureStage.SYNTHESIS,
                "Synthesizing recommendation",
            )
            pool = build_claim_pool(case=case, clusters=clusters, analyses=analyses)
            cluster_refs = {
                pool.cluster_ref_by_id[cluster.cluster_id]: cluster.title
                for cluster in clusters
            }
            proposal = self._reason(
                ReasoningTask.SYNTHESIZE_RECOMMENDATION,
                prompt_identities,
                stage_timings,
                lambda: self._reasoning.propose_recommendation(
                    case,
                    context,
                    forces,
                    clusters,
                    analyses,
                    alternatives,
                    scenarios,
                    packets,
                    available_claims=pool.available,
                    cluster_refs=cluster_refs,
                ),
            )
            output_repairs = execution_metadata.get("model_output_repairs")
            proposal_errors = validate_proposal(proposal, pool=pool)
            if proposal_errors:
                if isinstance(output_repairs, list):
                    output_repairs.append(
                        {
                            "kind": "repaired_recommendation_proposal",
                            "errors": proposal_errors,
                        }
                    )
                proposal = self._reason(
                    ReasoningTask.REPAIR_RECOMMENDATION_PROPOSAL,
                    prompt_identities,
                    stage_timings,
                    lambda: self._reasoning.repair_recommendation_proposal(
                        proposal,
                        proposal_errors,
                        available_claims=pool.available,
                        cluster_refs=cluster_refs,
                    ),
                )
            try:
                composition = compose_recommendation(
                    proposal,
                    pool=pool,
                    forces=forces,
                    alternatives=alternatives,
                    scenarios=scenarios,
                    analyses=analyses,
                    packets=packets,
                )
            except ProposalCompositionError as exc:
                raise ModelOutputValidationError(
                    f"The synthesis proposal could not be composed: {exc}"
                ) from exc
            report = composition.report
            # Composition is the normal path, not a repair: keep it out of the repair audit.
            execution_metadata["synthesis_proposal_hash"] = proposal_content_hash(proposal)
            execution_metadata["synthesis_composition"] = composition.actions  # type: ignore[assignment]
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
            stages.artifact(
                "Recommendation synthesized",
                report.decision_summary.text,
                {
                    "disposition": report.disposition,
                    "confidence": report.confidence.model_dump(mode="json"),
                },
            )
            stages.finish(
                "Recommendation synthesized",
            )

            stages.begin(
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
            stages.artifact(
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
            stages.finish(
                "Evidence validated",
            )

            stages.begin(
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
            stages.finish(
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
            stages.begin(
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
            stages.finish(
                "Run and case revision saved",
            )
            stages.completed(
                "Consultation completed",
                report.decision_summary.text,
                {
                    "run_id": run.run_id,
                    "report_id": report.report_id,
                    "disposition": report.disposition,
                    "result_case_revision": run.result_case_revision,
                },
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
                failure_stage=stages.current,
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
                stages.failed(
                    sanitized_error,
                    {
                        "failure_diagnostics": [
                            item.model_dump(mode="json") for item in failure_diagnostics
                        ]
                    },
                )
            raise

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

    @staticmethod

    @staticmethod

    @staticmethod


    @staticmethod

    @staticmethod

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

    @staticmethod

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
                atlas_overview(atlas) if atlas is not None else None
            ),
            atlas_summary=(
                f"{len(atlas.nodes)} nodes, {len(atlas.edges)} edges, "
                f"{len(atlas.signals)} objective signals"
                if atlas
                else None
            ),
        )
