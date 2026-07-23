"""Unified greenfield and brownfield consultation workflow."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from archcompass.application.evidence import (
    repair_report_evidence,
    validate_report_evidence,
)
from archcompass.application.reporting import render_markdown
from archcompass.configuration import AppConfig
from archcompass.domain.atlas import Atlas, AtlasQueryPlan, AtlasQueryResult
from archcompass.domain.base import utc_now
from archcompass.domain.case import (
    ArchitectureCase,
    CaseStatement,
    Confidence,
    RecommendationState,
    StatementKind,
)
from archcompass.domain.consultation import (
    ConsultationRun,
    ConsultationStatus,
    FocusedAnalysisPacket,
    GlobalContext,
)
from archcompass.domain.errors import EvidenceReferenceError
from archcompass.domain.policy import RetrievedPolicy
from archcompass.ports.repositories import (
    AtlasRepository,
    CaseRepository,
    ConsultationCommitRepository,
    ConsultationRunRepository,
)
from archcompass.ports.services import (
    AtlasQueryService,
    PolicyIndex,
    PolicyRetriever,
    ReasoningProvider,
)


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
        reasoning: ReasoningProvider,
        policy_sources: tuple[Path, ...],
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

    def advise(self, case_id: str, *, atlas: Atlas | None = None) -> ConsultationRun:
        started = datetime.now(UTC)
        revision = self._cases.get(case_id)
        policy_sources = list(self._policy_sources)
        if atlas is not None:
            policy_sources.append(
                Path(atlas.version.root_path) / ".archcompass" / "policies"
            )
        policy_version = self._policy_index.ensure_current(policy_sources)
        case = revision.snapshot
        context = self._global_context(case, atlas)
        forces = self._reasoning.discover_design_forces(context)
        all_results: list[AtlasQueryResult] = []
        plans: list[AtlasQueryPlan] = []
        if atlas is not None:
            for iteration in range(1, self._config.consultation.max_zoom_iterations + 1):
                plan = self._reasoning.plan_atlas_queries(
                    context,
                    forces,
                    iteration=iteration,
                    prior_results=all_results,
                )
                if len(plan.queries) > self._config.consultation.max_queries_per_iteration:
                    plan = plan.model_copy(
                        update={
                            "queries": plan.queries[
                                : self._config.consultation.max_queries_per_iteration
                            ]
                        }
                    )
                plans.append(plan)
                if not plan.queries:
                    break
                all_results.extend(
                    self._queries.execute(atlas, query) for query in plan.queries
                )
        force_query = " ".join(
            f"{force.title} {force.description}" for force in forces
        )
        retrieved: list[RetrievedPolicy] = self._policies.retrieve(
            force_query,
            top_k=self._config.retrieval.top_k,
            version_id=policy_version.version_id,
        )
        packet = FocusedAnalysisPacket(
            concern="; ".join(force.title for force in forces),
            reason="The selected forces share responsibility and change-locality consequences.",
            design_force_ids=[force.force_id for force in forces],
            query_results=all_results,
            policies=retrieved,
            assumptions=[item.text for item in case.assumptions],
            uncertainty=(
                ["Repository evidence is unavailable."]
                if atlas is None
                else [
                    "Static call resolution is conservative and runtime behavior is not observed."
                ]
            ),
        )
        analyses = [self._reasoning.analyze_concern_cluster(context, packet)]
        alternatives = self._reasoning.generate_alternatives(context, analyses)
        scenarios = self._reasoning.evaluate_scenarios(context, alternatives, analyses)
        report = self._reasoning.synthesize_recommendation(
            case, context, analyses, alternatives, scenarios, [packet]
        )
        allowed_node_ids = {
            node_id for result in all_results for node_id in result.node_ids
        }
        allowed_nodes = (
            {
                node.atlas_id: node
                for node in atlas.nodes
                if node.atlas_id in allowed_node_ids
            }
            if atlas
            else {}
        )
        allowed_policy_ids = {item.policy.id for item in retrieved}
        errors = validate_report_evidence(
            report,
            allowed_nodes=allowed_nodes,
            allowed_policy_ids=allowed_policy_ids,
        )
        repaired = False
        if errors:
            repaired = True
            report = repair_report_evidence(
                report,
                allowed_nodes=allowed_nodes,
                allowed_policy_ids=allowed_policy_ids,
            )
            errors = validate_report_evidence(
                report,
                allowed_nodes=allowed_nodes,
                allowed_policy_ids=allowed_policy_ids,
            )
        if errors:
            failed = ConsultationRun(
                status=ConsultationStatus.FAILED,
                case_id=case.case_id,
                input_case_revision=revision.revision,
                atlas_version_id=atlas.version.version_id if atlas else None,
                policy_index_version_id=policy_version.version_id,
                reasoning_model=self._reasoning.model_identity,
                embedding_model=policy_version.embedding_model,
                config_hash=self._config.identity_hash,
                prompt_identities=self._reasoning.prompt_identities,
                design_forces=forces,
                query_plans=plans,
                focused_packets=[packet],
                alternatives=alternatives,
                scenarios=scenarios,
                validation_errors=errors,
                repair_attempted=repaired,
                started_at=started,
                completed_at=utc_now(),
            )
            self._runs.save(failed)
            raise EvidenceReferenceError(
                "Recommendation evidence validation failed: " + "; ".join(errors)
            )
        markdown = render_markdown(report)
        run = ConsultationRun(
            status=ConsultationStatus.SUCCEEDED,
            case_id=case.case_id,
            input_case_revision=revision.revision,
            result_case_revision=revision.revision + 1,
            atlas_version_id=atlas.version.version_id if atlas else None,
            policy_index_version_id=policy_version.version_id,
            reasoning_model=self._reasoning.model_identity,
            embedding_model=policy_version.embedding_model,
            config_hash=self._config.identity_hash,
            prompt_identities=self._reasoning.prompt_identities,
            design_forces=forces,
            query_plans=plans,
            focused_packets=[packet],
            alternatives=alternatives,
            scenarios=scenarios,
            report=report,
            markdown_report=markdown,
            validation_errors=[],
            repair_attempted=repaired,
            started_at=started,
            completed_at=utc_now(),
            execution_metadata={
                "zoom_iterations": len(plans),
                "atlas_queries": sum(len(plan.queries) for plan in plans),
                "retrieved_policies": len(retrieved),
            },
        )
        updated_case = case.model_copy(
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
                "referenced_policy_ids": sorted(allowed_policy_ids),
                "candidate_alternatives": alternatives,
                "current_recommendation": RecommendationState(
                    summary=report.decision_summary,
                    rationale=report.recommended_architecture,
                    run_id=run.run_id,
                ),
                "confidence": Confidence.model_validate(report.confidence),
                "reversal_conditions": report.reversal_conditions,
                "revisit_triggers": report.revisit_triggers,
                "updated_at": utc_now(),
            }
        )
        self._commits.commit_success(
            run, updated_case, expected_revision=revision.revision
        )
        return run

    @staticmethod
    def _global_context(
        case: ArchitectureCase, atlas: Atlas | None
    ) -> GlobalContext:
        return GlobalContext(
            case_id=case.case_id,
            revision=case.revision,
            title=case.title,
            problem=case.problem_statement,
            desired_outcome=case.desired_outcome,
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
            atlas_summary=(
                f"{len(atlas.nodes)} nodes, {len(atlas.edges)} edges, "
                f"{len(atlas.signals)} objective signals"
                if atlas
                else None
            ),
        )
