"""Unified, auditable greenfield and brownfield consultation workflow."""

from __future__ import annotations

import re
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from time import perf_counter
from typing import TypeVar

from archcompass.application.evidence import (
    repair_report_evidence_with_history,
    validate_report_evidence,
)
from archcompass.application.reporting import render_markdown
from archcompass.configuration import AppConfig
from archcompass.domain.atlas import (
    Atlas,
    AtlasEdge,
    AtlasNode,
    EdgeType,
    SourceExcerpt,
    SourceLocation,
)
from archcompass.domain.base import new_id, utc_now
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
    cluster_partition_errors,
)
from archcompass.domain.errors import (
    AtlasNotFoundError,
    EvidenceReferenceError,
    ModelOutputValidationError,
)
from archcompass.domain.policy import PolicyIndexVersion, RetrievedPolicy
from archcompass.ports.atlas import AtlasFreshnessChecker, AtlasQueryService
from archcompass.ports.policies import PolicyIndex, PolicyRetriever
from archcompass.ports.reasoning import FocusedReasoningProvider
from archcompass.ports.repositories import (
    AtlasRepository,
    CaseRepository,
    ConsultationCommitRepository,
    ConsultationRunRepository,
)

Result = TypeVar("Result")


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
        atlas: Atlas | None = None,
    ) -> ConsultationRun:
        """Advise from persisted evidence.

        ``atlas`` is a schema-v1 call compatibility shim: its content is ignored
        and its ID is reloaded from the atlas repository. Unsaved aggregates fail.
        """
        started = datetime.now(UTC)
        revision = self._cases.get(case_id)
        case = revision.snapshot
        run_id = new_id("run")
        stage_timings: dict[str, float] = {}
        prompt_identities: list[str] = []
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
            resolved_atlas = self._timed(
                stage_timings,
                "atlas_resolution",
                lambda: self._resolve_atlas(
                    case,
                    atlas_version_id=atlas_version_id,
                    repository_root=repository_root,
                    legacy_atlas=atlas,
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
            current_stage = ConsultationFailureStage.POLICY
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
            context = self._global_context(case, resolved_atlas)

            current_stage = ConsultationFailureStage.DESIGN_FORCES
            forces = self._reason(
                "discover_design_forces",
                prompt_identities,
                stage_timings,
                lambda: self._reasoning.discover_design_forces(context),
            )

            current_stage = ConsultationFailureStage.CLUSTERING
            clusters = self._reason(
                "cluster_design_forces",
                prompt_identities,
                stage_timings,
                lambda: self._reasoning.cluster_design_forces(context, forces),
            )
            partition_errors = cluster_partition_errors(forces, clusters)
            if partition_errors:
                raise ModelOutputValidationError("; ".join(partition_errors))

            selected_by_cluster: dict[str, list[str]] = {
                cluster.cluster_id: [] for cluster in clusters
            }
            summaries_by_cluster: dict[str, dict[str, FocusedNodeSummary]] = {
                cluster.cluster_id: {} for cluster in clusters
            }
            excerpts_by_cluster: dict[str, list[SourceExcerpt]] = {
                cluster.cluster_id: [] for cluster in clusters
            }
            excerpt_lines_by_cluster = {cluster.cluster_id: 0 for cluster in clusters}

            if resolved_atlas is not None:
                nodes = {node.atlas_id: node for node in resolved_atlas.nodes}
                for iteration in range(1, self._config.consultation.max_zoom_iterations + 1):
                    current_stage = ConsultationFailureStage.QUERY_PLANNING
                    iteration_plans = self._reason(
                        "plan_atlas_queries",
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
                    self._validate_cluster_plans(iteration_plans, clusters, iteration)
                    clamped = self._clamp_iteration_plans(
                        iteration_plans,
                        self._config.consultation.max_queries_per_iteration,
                        execution_metadata,
                    )
                    plans.extend(clamped)
                    query_count = sum(len(item.plan.queries) for item in clamped)
                    execution_metadata["zoom_iterations"] = iteration
                    if query_count == 0:
                        break
                    current_stage = ConsultationFailureStage.QUERY_EXECUTION
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
                                result_node_ids=result.node_ids,
                                result_summary=result.summary,
                                result_excerpts=result.excerpts,
                                nodes=nodes,
                                selected=selected_by_cluster,
                                summaries=summaries_by_cluster,
                                excerpts=excerpts_by_cluster,
                                excerpt_line_counts=excerpt_lines_by_cluster,
                                execution_metadata=execution_metadata,
                            )

            all_retrieved: dict[str, list[RetrievedPolicy]] = {}
            for cluster in clusters:
                current_stage = ConsultationFailureStage.POLICY_RETRIEVAL
                force_lookup = {force.force_id: force for force in forces}
                cluster_query = " ".join(
                    [
                        cluster.title,
                        cluster.rationale,
                        *[
                            (f"{force_lookup[force_id].title} {force_lookup[force_id].description}")
                            for force_id in cluster.design_force_ids
                        ],
                    ]
                )
                retrieved = self._timed(
                    stage_timings,
                    f"policy_retrieval.{cluster.cluster_id}",
                    lambda cluster_query=cluster_query: self._policies.retrieve(
                        cluster_query,
                        top_k=self._config.retrieval.top_k,
                        version_id=policy_version.version_id,
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
                    policies=retrieved,
                )
                packets.append(packet)

                current_stage = ConsultationFailureStage.CONCERN_ANALYSIS
                analysis = self._reason(
                    "analyze_concern_cluster",
                    prompt_identities,
                    stage_timings,
                    lambda packet=packet: self._reasoning.analyze_concern_cluster(context, packet),
                    timing_suffix=cluster.cluster_id,
                )
                self._validate_concern_analysis(analysis, packet)
                analyses.append(analysis)

            current_stage = ConsultationFailureStage.ALTERNATIVES
            alternatives = self._reason(
                "generate_alternatives",
                prompt_identities,
                stage_timings,
                lambda: self._reasoning.generate_alternatives(context, analyses),
            )

            current_stage = ConsultationFailureStage.SCENARIOS
            scenarios = self._reason(
                "evaluate_scenarios",
                prompt_identities,
                stage_timings,
                lambda: self._reasoning.evaluate_scenarios(context, alternatives, analyses),
            )
            self._validate_scenario_coverage(scenarios, alternatives)

            current_stage = ConsultationFailureStage.SYNTHESIS
            report = self._reason(
                "synthesize_recommendation",
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
            unrepaired_report = report
            self._validate_synthesis_coverage(
                report,
                forces,
                alternatives,
                packets,
            )

            current_stage = ConsultationFailureStage.VALIDATION
            allowed_nodes = self._allowed_nodes(resolved_atlas, packets)
            allowed_policy_ids = {
                item.policy.id for retrieved in all_retrieved.values() for item in retrieved
            }
            initial_errors = validate_report_evidence(
                report,
                allowed_nodes=allowed_nodes,
                allowed_policy_ids=allowed_policy_ids,
            )
            if initial_errors:
                repaired = repair_report_evidence_with_history(
                    report,
                    allowed_nodes=allowed_nodes,
                    allowed_policy_ids=allowed_policy_ids,
                )
                report = repaired.report
                repair_actions = repaired.actions
                final_errors = validate_report_evidence(
                    report,
                    allowed_nodes=allowed_nodes,
                    allowed_policy_ids=allowed_policy_ids,
                )
            if final_errors:
                raise EvidenceReferenceError(
                    "Recommendation evidence validation failed: " + "; ".join(final_errors)
                )

            current_stage = ConsultationFailureStage.RENDERING
            markdown = self._timed(stage_timings, "rendering", lambda: render_markdown(report))
            run = ConsultationRun(
                schema_version=2,
                run_id=run_id,
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
            updated_case = self._updated_case(
                case,
                run=run,
                atlas=resolved_atlas,
                report=report,
                forces=forces,
                alternatives=alternatives,
                analyses=analyses,
            )
            current_stage = ConsultationFailureStage.COMMIT
            self._timed(
                stage_timings,
                "commit",
                lambda: self._commits.commit_success(
                    run, updated_case, expected_revision=revision.revision
                ),
            )
            return run
        except Exception as error:
            failed = ConsultationRun(
                schema_version=2,
                run_id=run_id,
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
                sanitized_errors=[self._sanitize_error(error, resolved_atlas)],
                started_at=started,
                completed_at=utc_now(),
                execution_metadata=execution_metadata,  # type: ignore[arg-type]
            )
            # Failure persistence is deliberately outside another catch. If it
            # fails, persistence is the unavoidable terminal exception.
            self._runs.save(failed)
            raise

    def _resolve_atlas(
        self,
        case: ArchitectureCase,
        *,
        atlas_version_id: str | None,
        repository_root: Path | None,
        legacy_atlas: Atlas | None,
    ) -> Atlas | None:
        if repository_root is not None:
            atlas = self._atlases.latest_for_path(repository_root)
            if atlas is None:
                raise AtlasNotFoundError(f"No indexed atlas exists for {repository_root.resolve()}")
            return atlas
        if atlas_version_id is not None:
            return self._atlases.get(atlas_version_id)
        if legacy_atlas is not None:
            # Ignore the supplied aggregate and prove persistence by reloading it.
            return self._atlases.get(legacy_atlas.version.version_id)
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
        task: str,
        prompt_identities: list[str],
        timings: dict[str, float],
        operation: Callable[[], Result],
        *,
        timing_suffix: str | None = None,
    ) -> Result:
        prompt_identities.append(self._reasoning.prompt_identity(task))
        timing_key = task if timing_suffix is None else f"{task}.{timing_suffix}"
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
    def _clamp_iteration_plans(
        plans: list[ClusterQueryPlan],
        budget: int,
        metadata: dict[str, object],
    ) -> list[ClusterQueryPlan]:
        remaining = budget
        clamped: list[ClusterQueryPlan] = []
        for item in plans:
            queries = item.plan.queries[:remaining]
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
            remaining -= len(queries)
        return clamped

    def _accumulate_query_result(
        self,
        *,
        cluster_id: str,
        result_node_ids: list[str],
        result_summary: str,
        result_excerpts: list[SourceExcerpt],
        nodes: dict[str, AtlasNode],
        selected: dict[str, list[str]],
        summaries: dict[str, dict[str, FocusedNodeSummary]],
        excerpts: dict[str, list[SourceExcerpt]],
        excerpt_line_counts: dict[str, int],
        execution_metadata: dict[str, object],
    ) -> None:
        selected_ids = selected[cluster_id]
        for node_id in result_node_ids:
            if node_id in selected_ids:
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
            summaries[cluster_id][node_id] = FocusedNodeSummary.from_node(
                node, summary=result_summary
            )

        for excerpt in result_excerpts:
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
    def _build_packet(
        *,
        case: ArchitectureCase,
        cluster: ConcernCluster,
        atlas: Atlas | None,
        selected_ids: list[str],
        summaries: list[FocusedNodeSummary],
        excerpts: list[SourceExcerpt],
        policies: list[RetrievedPolicy],
    ) -> FocusedAnalysisPacket:
        selected = set(selected_ids)
        metrics = (
            [profile for profile in atlas.metrics if profile.node_id in selected] if atlas else []
        )
        relationships: list[AtlasEdge] = (
            [
                edge
                for edge in atlas.edges
                if edge.source_id in selected and edge.target_id in selected
            ]
            if atlas
            else []
        )
        test_ids: set[str] = set()
        if atlas:
            node_types = {node.atlas_id: node.node_type for node in atlas.nodes}
            for edge in relationships:
                if edge.edge_type == EdgeType.TESTS:
                    for node_id in (edge.source_id, edge.target_id):
                        node_type = node_types.get(node_id)
                        if node_type is not None and node_type.value.startswith("test"):
                            test_ids.add(node_id)
        return FocusedAnalysisPacket(
            cluster=cluster,
            node_summaries=summaries,
            metrics=metrics,
            relationships=relationships,
            test_ids=sorted(test_ids),
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
                    summary = node_summaries.get(reference.node_id)
                    location = reference.location
                    if (
                        summary is None
                        or summary.location is None
                        or location is None
                        or location.path != summary.location.path
                        or location.start_line < summary.location.start_line
                        or location.end_line > summary.location.end_line
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
        retrieved: dict[str, RetrievedPolicy] = {}
        matched_sections: dict[str, set[str]] = {}
        for packet in packets:
            for item in packet.policies:
                retrieved.setdefault(item.policy.id, item)
                matched_sections.setdefault(item.policy.id, set()).update(
                    " ".join(chunk.section.split()).casefold()
                    for chunk in item.chunks
                )
        for summary in report.policy_evidence:
            item = retrieved.get(summary.id)
            if item is None:
                raise ModelOutputValidationError(
                    "Final synthesis invented a policy evidence ID"
                )
            policy = item.policy
            if (
                summary.title != policy.title
                or summary.scope != policy.scope
                or summary.strength != policy.strength
            ):
                raise ModelOutputValidationError(
                    f"Final synthesis altered canonical metadata for policy {summary.id}"
                )
            sections = {
                " ".join(section.split()).casefold()
                for section in summary.matched_sections
            }
            if not sections <= matched_sections[summary.id]:
                raise ModelOutputValidationError(
                    f"Final synthesis invented matched sections for policy {summary.id}"
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
        forces: list[DesignForce],
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
                "design_forces": [
                    CaseStatement(
                        id=force.force_id,
                        text=f"{force.title}: {force.description}",
                        kind=StatementKind.FORCE,
                        source=run.run_id,
                    )
                    for force in forces
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
        if isinstance(error, ModelOutputValidationError):
            message = "Structured model output failed validation"
        else:
            message = " ".join(str(error).split())
        if atlas is not None:
            message = message.replace(atlas.version.root_path, "<repository>")
        message = re.sub(r"(?<![:\w])/[^\s;,)]+", "<path>", message)
        message = message[:500]
        return f"{type(error).__name__}: {message or 'operation failed'}"

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
            atlas_summary=(
                f"{len(atlas.nodes)} nodes, {len(atlas.edges)} edges, "
                f"{len(atlas.signals)} objective signals"
                if atlas
                else None
            ),
        )
