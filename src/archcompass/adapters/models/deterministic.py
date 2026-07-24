"""Deterministic model substitutes for tests and reproducible evaluations."""

from __future__ import annotations

import math
import re
from hashlib import sha256
from typing import ClassVar

from archcompass.domain.atlas import (
    AtlasQuery,
    AtlasQueryPlan,
    HotspotsQuery,
    RepositorySummaryQuery,
    SourceExcerptQuery,
)
from archcompass.domain.case import (
    ArchitectureCase,
    CaseAlternative,
    Confidence,
    ConfidenceLevel,
)
from archcompass.domain.consultation import (
    ADRRecord,
    AtlasEvidenceReference,
    Claim,
    ClaimClassification,
    ClusterQueryPlan,
    ConcernAnalysis,
    ConcernCluster,
    DesignForce,
    FocusedAnalysisPacket,
    FocusedNodeSummary,
    GlobalContext,
    RecommendationDisposition,
    RecommendationReport,
    ScenarioEvaluation,
    SupportedStatement,
)
from archcompass.domain.policy import PolicyEvidenceSummary


class DeterministicEmbeddingProvider:
    def __init__(self, dimensions: int = 64) -> None:
        self._dimensions = dimensions

    @property
    def identity(self) -> tuple[str, str, int]:
        return ("fake", "deterministic-token-hash-v1", self._dimensions)

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [self._embed_one(text) for text in texts]

    def _embed_one(self, text: str) -> list[float]:
        vector = [0.0] * self._dimensions
        tokens = re.findall(r"[a-z0-9-]+", text.casefold())
        for token in tokens:
            digest = sha256(token.encode("utf-8")).digest()
            index = int.from_bytes(digest[:4], "big") % self._dimensions
            vector[index] += 1.0 if digest[4] % 2 == 0 else -1.0
        magnitude = math.sqrt(sum(value * value for value in vector)) or 1.0
        return [value / magnitude for value in vector]


class DeterministicReasoningProvider:
    _PROMPTS: ClassVar[dict[str, str]] = {
        "discover_design_forces": "discover-design-forces:v2",
        "cluster_design_forces": "cluster-design-forces:v1",
        "plan_atlas_queries": "plan-cluster-atlas-queries:v2",
        "analyze_concern_cluster": "analyze-concern:v2",
        "generate_alternatives": "generate-alternatives:v2",
        "evaluate_scenarios": "evaluate-scenarios:v2",
        "synthesize_recommendation": "synthesize-recommendation:v2",
    }

    @property
    def model_identity(self) -> str:
        return "fake:deterministic-architecture-v2"

    def prompt_identity(self, task: str) -> str:
        return self._PROMPTS[task]

    def consume_repair_actions(self) -> list[dict[str, object]]:
        return []

    @property
    def prompt_identities(self) -> list[str]:
        """Compatibility for callers that inspect the provider catalog."""
        return list(self._PROMPTS.values())

    def discover_design_forces(self, context: GlobalContext) -> list[DesignForce]:
        forces = [
            DesignForce(
                title="Responsibility ownership",
                description="Place changing knowledge behind the boundary that owns it.",
                importance="high",
            ),
            DesignForce(
                title="Locality of change",
                description="Minimize the modules and interfaces changed by one decision.",
                importance="high",
            ),
        ]
        if context.future_changes:
            forces.append(
                DesignForce(
                    title="Credible future variation",
                    description=(
                        "Accommodate stated future changes without a universal plugin platform."
                    ),
                    importance="medium",
                )
            )
        if not context.atlas_summary:
            forces.append(
                DesignForce(
                    title="Evidence uncertainty",
                    description=(
                        "No repository evidence is available; implementation details remain "
                        "assumptions."
                    ),
                    importance="medium",
                )
            )
        return forces

    def cluster_design_forces(
        self, context: GlobalContext, forces: list[DesignForce]
    ) -> list[ConcernCluster]:
        del context
        return [
            ConcernCluster(
                title="Responsibility and change locality",
                rationale=(
                    "These forces jointly determine where changing knowledge should be owned."
                ),
                design_force_ids=[force.force_id for force in forces],
            )
        ]

    def plan_atlas_queries(
        self,
        context: GlobalContext,
        forces: list[DesignForce],
        clusters: list[ConcernCluster],
        *,
        iteration: int,
        prior_results: dict[str, list[FocusedNodeSummary]],
    ) -> list[ClusterQueryPlan]:
        del context, forces
        plans: list[ClusterQueryPlan] = []
        for cluster in clusters:
            if iteration == 1:
                plan = AtlasQueryPlan(
                    iteration=iteration,
                    rationale="Establish repository shape and dependency concentration.",
                    queries=[
                        RepositorySummaryQuery(kind="repository_summary", limit=30),
                        HotspotsQuery(
                            kind="hotspots",
                            metric="reverse_dependency_reach",
                            limit=10,
                        ),
                    ],
                )
            elif iteration == 2 and prior_results.get(cluster.cluster_id):
                excerpt_queries: list[AtlasQuery] = []
                for summary in prior_results[cluster.cluster_id]:
                    if summary.location is not None:
                        excerpt_queries.append(
                            SourceExcerptQuery(
                                kind="source_excerpt",
                                node_id=summary.node_id,
                                context_lines=2,
                                max_lines=40,
                            )
                        )
                    if len(excerpt_queries) == 3:
                        break
                plan = AtlasQueryPlan(
                    iteration=iteration,
                    rationale="Inspect a bounded sample of surfaced source nodes.",
                    queries=excerpt_queries,
                )
            else:
                plan = AtlasQueryPlan(
                    iteration=iteration,
                    rationale="Existing evidence is sufficient.",
                    queries=[],
                )
            plans.append(ClusterQueryPlan(cluster_id=cluster.cluster_id, plan=plan))
        return plans

    def analyze_concern_cluster(
        self,
        context: GlobalContext,
        packet: FocusedAnalysisPacket,
        *,
        validation_feedback: str | None = None,
    ) -> ConcernAnalysis:
        del context, validation_feedback
        findings: list[Claim] = []
        for summary in packet.node_summaries[:4]:
            if summary.location is None:
                continue
            provider_knowledge = any(
                token in f"{summary.path} {summary.qualified_name}".casefold()
                for token in ("provider", "voice", "preflight", "frontend")
            )
            findings.append(
                Claim(
                    text=(
                        (
                            f"{summary.qualified_name or summary.node_id} contains "
                            "provider-specific voice knowledge, contributing to duplicated "
                            "ownership and coordinated provider changes."
                        )
                        if provider_knowledge
                        else (
                            f"{summary.qualified_name or summary.node_id} is relevant to "
                            f"{packet.concern}."
                        )
                    ),
                    classification=ClaimClassification.REPOSITORY_OBSERVATION,
                    atlas_references=[
                        AtlasEvidenceReference(
                            node_id=summary.node_id,
                            location=summary.location,
                        )
                    ],
                )
            )
        for retrieved in packet.policies:
            findings.append(
                Claim(
                    text=f"{retrieved.policy.title} guides {packet.concern}.",
                    classification=ClaimClassification.POLICY_GUIDANCE,
                    policy_ids=[retrieved.policy.id],
                )
            )
        if not findings:
            findings.append(
                Claim(
                    text=f"{packet.concern} is evaluated from the confirmed case context.",
                    classification=ClaimClassification.ADVISOR_INFERENCE,
                )
            )
        return ConcernAnalysis(
            cluster_id=packet.cluster.cluster_id,
            concern=packet.concern,
            findings=findings,
            implications=["Prefer one explicit owner for knowledge that changes together."],
        )

    def generate_alternatives(
        self, context: GlobalContext, analyses: list[ConcernAnalysis]
    ) -> list[CaseAlternative]:
        del analyses
        text = f"{context.title} {context.problem} {' '.join(context.future_changes)}".casefold()
        if "one implementation" in text or "premature" in text:
            return [
                CaseAlternative(
                    title="Keep the behavior local",
                    summary="Retain the direct implementation until credible variation appears.",
                ),
                CaseAlternative(
                    title="Introduce abstraction now",
                    summary="Add an interface, factory, and configuration immediately.",
                ),
            ]
        if any(token in text for token in ("qwen", "provider", "voice")):
            return [
                CaseAlternative(
                    title="Provider-owned variation",
                    summary=(
                        "Keep stable orchestration outside and provider-specific capabilities "
                        "inside providers."
                    ),
                ),
                CaseAlternative(
                    title="Central capability registry",
                    summary="Centralize provider capability knowledge in shared orchestration.",
                ),
                CaseAlternative(
                    title="Universal plugin platform",
                    summary="Define dynamic plugins, factories, and metadata up front.",
                ),
            ]
        return [
            CaseAlternative(
                title="Preserve the current design",
                summary="Make no structural change without a concrete design force.",
            ),
            CaseAlternative(
                title="Introduce a focused boundary",
                summary="Create one boundary around the responsibility most likely to change.",
            ),
        ]

    def evaluate_scenarios(
        self,
        context: GlobalContext,
        alternatives: list[CaseAlternative],
        analyses: list[ConcernAnalysis],
    ) -> list[ScenarioEvaluation]:
        del analyses
        scenarios = context.future_changes or ["The confirmed requirements remain stable"]
        return [
            ScenarioEvaluation(
                scenario=scenario,
                assumptions=[scenario],
                alternative_results={
                    alternative.id: f"{alternative.title}: evaluated against {scenario}"
                    for alternative in alternatives
                },
                conclusion=(
                    "Prefer the option that contains changing knowledge with the fewest "
                    "coordinated edits."
                ),
            )
            for scenario in scenarios[:4]
        ]

    def synthesize_recommendation(
        self,
        case: ArchitectureCase,
        context: GlobalContext,
        forces: list[DesignForce],
        clusters: list[ConcernCluster],
        analyses: list[ConcernAnalysis],
        alternatives: list[CaseAlternative],
        scenarios: list[ScenarioEvaluation],
        packets: list[FocusedAnalysisPacket],
        *,
        validation_feedback: str | None = None,
    ) -> RecommendationReport:
        del context, clusters, validation_feedback
        text = (
            f"{case.title} {case.problem_statement} {' '.join(case.expected_future_changes)}"
        ).casefold()
        premature = "one implementation" in text or "premature" in text
        provider = not premature and any(
            token in text for token in ("qwen", "provider", "voice")
        )
        if premature:
            disposition = RecommendationDisposition.KEEP_LOCAL
            decision = (
                "Keep the implementation local. The proposed abstraction adds concepts and "
                "configuration without containing credible variation."
            )
            responsibilities = [
                "The existing module continues to own the single behavior.",
                "Introduce a boundary only when independent variation appears.",
            ]
        elif provider:
            disposition = RecommendationDisposition.MOVE_RESPONSIBILITY
            decision = (
                "Use stable workflow boundaries while each provider owns capability discovery "
                "and provider-specific voice variation. Do not build a universal plugin platform."
            )
            responsibilities = [
                "Application workflow owns sequencing and provider-neutral job state.",
                "Each provider adapter owns voice discovery and provider-specific identifiers.",
                "Presentation consumes provider-neutral capability results.",
            ]
        else:
            disposition = RecommendationDisposition.INTRODUCE_BOUNDARY
            decision = (
                "Introduce only the focused responsibility boundary supported by current design "
                "forces; preserve all other local behavior."
            )
            responsibilities = [
                "Assign one owner to each piece of knowledge that changes together."
            ]

        repository_claims = [
            claim
            for analysis in analyses
            for claim in analysis.findings
            if claim.classification == ClaimClassification.REPOSITORY_OBSERVATION
        ]
        policy_claims = [
            claim
            for analysis in analyses
            for claim in analysis.findings
            if claim.classification == ClaimClassification.POLICY_GUIDANCE
        ]
        confirmed = [
            Claim(
                claim_id=item.id,
                text=item.text,
                classification=ClaimClassification.CONFIRMED_REQUIREMENT,
            )
            for item in case.confirmed_facts
        ]
        assumptions = [
            Claim(
                claim_id=item.id,
                text=item.text,
                classification=ClaimClassification.SCENARIO_ASSUMPTION,
            )
            for item in [*case.assumptions, *case.unresolved_questions]
        ]
        inference = Claim(
            text=(
                "The recommendation follows from the combined ownership, locality, policy, "
                "and repository evidence."
            ),
            classification=ClaimClassification.ADVISOR_INFERENCE,
        )
        support_ids = [
            claim.claim_id for claim in [*confirmed, *repository_claims, *policy_claims, inference]
        ]

        # At least the synthesis inference is always available.
        def supported(value: str) -> SupportedStatement:
            return SupportedStatement(
                text=value,
                classification=ClaimClassification.ADVISOR_INFERENCE,
                supporting_claim_ids=support_ids,
            )

        confidence = Confidence(
            level=(
                ConfidenceLevel.HIGH if packets and repository_claims else ConfidenceLevel.MEDIUM
            ),
            rationale=(
                "Repository evidence and policies support the allocation."
                if repository_claims
                else "The recommendation is grounded in case context without repository evidence."
            ),
        )
        evidence = [
            *confirmed,
            *repository_claims,
            *policy_claims,
            *assumptions,
            inference,
        ]
        policy_evidence_by_id: dict[str, PolicyEvidenceSummary] = {}
        for packet in packets:
            for retrieved in packet.policies:
                policy_evidence_by_id.setdefault(
                    retrieved.policy.id,
                    PolicyEvidenceSummary.from_retrieved(retrieved),
                )
        conflicts = [conflict for analysis in analyses for conflict in analysis.policy_conflicts]
        return RecommendationReport(
            schema_version=2,
            disposition=disposition,
            decision_summary=supported(decision),
            problem_and_desired_outcome=(
                f"{case.problem_statement}\n\nDesired outcome: {case.desired_outcome}"
            ),
            confirmed_context=confirmed,
            assumptions_and_unresolved_questions=assumptions,
            important_design_forces=forces,
            repository_observations=repository_claims,
            relevant_policies=policy_claims,
            policy_evidence=list(policy_evidence_by_id.values()),
            policy_conflicts=conflicts,
            recommended_architecture=supported(decision),
            responsibility_allocation=[supported(item) for item in responsibilities],
            conceptual_interfaces=(
                [
                    supported("ProviderCapabilities.discover_voices() -> VoiceCatalog"),
                    supported("NarrationProvider.synthesize(request) -> AudioArtifact"),
                    supported("NarrationWorkflow.resume(job_id) -> JobStatus"),
                ]
                if provider
                else []
            ),
            alternatives_considered=alternatives,
            scenario_analysis=scenarios,
            change_amplification_analysis=supported(
                (
                    "Provider changes remain within one adapter instead of coordinating "
                    "presentation and workflow edits."
                )
                if provider
                else "No current blast-radius reduction justifies another abstraction."
            ),
            trade_offs=[
                supported(item)
                for item in (
                    [
                        (
                            "Keeping the behavior local avoids interface, factory, registry, "
                            "and configuration overhead."
                        ),
                        (
                            "Delaying abstraction trades immediate extension flexibility for "
                            "lower present complexity."
                        ),
                    ]
                    if premature
                    else [
                        "The chosen boundary adds one explicit contract.",
                        "Static evidence cannot prove runtime behavior.",
                    ]
                )
            ],
            implementation_sequence=[
                supported(item)
                for item in (
                    [
                        "Retain the direct local formatter and its behavior tests.",
                        (
                            "Do not add an interface, factory, registry, or configuration key "
                            "until a second credible implementation appears."
                        ),
                    ]
                    if premature
                    else [
                        "Name the responsibility and its owner.",
                        "Move knowledge without changing behavior.",
                        "Add contract and workflow tests before removing duplication.",
                    ]
                )
            ],
            confidence=confidence,
            reversal_conditions=[
                supported(
                    "New evidence shows the responsibility changes independently from its owner."
                )
            ],
            revisit_triggers=[
                supported("A second concrete implementation appears."),
                supported("A future scenario becomes a committed requirement."),
            ],
            adr=ADRRecord(
                title=f"Architecture decision for {case.title}",
                context=case.problem_statement,
                decision=supported(decision),
                consequences=[
                    supported("Changing knowledge gains a single explicit owner."),
                    supported("Unused extension infrastructure is not introduced."),
                ],
            ),
            evidence_appendix=evidence,
        )
