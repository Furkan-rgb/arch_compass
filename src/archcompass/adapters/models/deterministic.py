"""Deterministic model substitutes for tests and reproducible evaluations."""

from __future__ import annotations

import math
import re
from hashlib import sha256

from archcompass.domain.atlas import (
    AtlasQueryPlan,
    AtlasQueryResult,
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
    ConcernAnalysis,
    DesignForce,
    FocusedAnalysisPacket,
    GlobalContext,
    RecommendationReport,
    ScenarioEvaluation,
)


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
    @property
    def model_identity(self) -> str:
        return "fake:deterministic-architecture-v1"

    @property
    def prompt_identities(self) -> list[str]:
        return [
            "discover-design-forces:v1",
            "plan-atlas-queries:v1",
            "analyze-concern:v1",
            "generate-alternatives:v1",
            "evaluate-scenarios:v1",
            "synthesize-recommendation:v1",
        ]

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

    def plan_atlas_queries(
        self,
        context: GlobalContext,
        forces: list[DesignForce],
        *,
        iteration: int,
        prior_results: list[AtlasQueryResult],
    ) -> AtlasQueryPlan:
        if iteration == 1:
            return AtlasQueryPlan(
                iteration=iteration,
                rationale="Establish repository shape and dependency concentration.",
                queries=[
                    RepositorySummaryQuery(kind="repository_summary", limit=30),
                    HotspotsQuery(
                        kind="hotspots", metric="reverse_dependency_reach", limit=10
                    ),
                ],
            )
        surfaced = [
            node_id
            for result in prior_results
            if result.query.kind == "hotspots"
            for node_id in result.node_ids
        ]
        if iteration == 2 and surfaced:
            return AtlasQueryPlan(
                iteration=iteration,
                rationale="Inspect a bounded sample of the most relevant surfaced nodes.",
                queries=[
                    SourceExcerptQuery(
                        kind="source_excerpt",
                        node_id=node_id,
                        context_lines=2,
                        max_lines=40,
                    )
                    for node_id in surfaced[:3]
                ],
            )
        return AtlasQueryPlan(
            iteration=iteration,
            rationale="Existing evidence is sufficient.",
            queries=[],
        )

    def analyze_concern_cluster(
        self, context: GlobalContext, packet: FocusedAnalysisPacket
    ) -> ConcernAnalysis:
        findings: list[Claim] = []
        for result in packet.query_results:
            for node_id in result.node_ids[:2]:
                findings.append(
                    Claim(
                        text=f"Repository evidence relevant to {packet.concern}: {result.summary}",
                        classification=ClaimClassification.REPOSITORY_OBSERVATION,
                        atlas_references=[AtlasEvidenceReference(node_id=node_id)],
                    )
                )
        for retrieved in packet.policies:
            findings.append(
                Claim(
                    text=f"{retrieved.policy.title} is relevant to {packet.concern}.",
                    classification=ClaimClassification.POLICY_GUIDANCE,
                    policy_ids=[retrieved.policy.id],
                )
            )
        if not findings:
            findings.append(
                Claim(
                    text=f"{packet.concern} must be evaluated from the confirmed case context.",
                    classification=ClaimClassification.ADVISOR_INFERENCE,
                )
            )
        return ConcernAnalysis(
            concern=packet.concern,
            findings=findings,
            implications=["Prefer one explicit owner for knowledge that changes together."],
        )

    def generate_alternatives(
        self, context: GlobalContext, analyses: list[ConcernAnalysis]
    ) -> list[CaseAlternative]:
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
                    summary="Centralize all provider capability knowledge in shared orchestration.",
                ),
                CaseAlternative(
                    title="Universal plugin platform",
                    summary="Define dynamic plugins, factories, and provider metadata up front.",
                ),
            ]
        return [
            CaseAlternative(
                title="Preserve the current design",
                summary=(
                    "Make no structural change until evidence identifies a concrete design force."
                ),
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
        scenarios = context.future_changes or ["The confirmed requirements remain stable"]
        return [
            ScenarioEvaluation(
                scenario=scenario,
                assumptions=[scenario],
                alternative_results=[
                    f"{alternative.title}: evaluated against {scenario}"
                    for alternative in alternatives
                ],
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
        analyses: list[ConcernAnalysis],
        alternatives: list[CaseAlternative],
        scenarios: list[ScenarioEvaluation],
        packets: list[FocusedAnalysisPacket],
    ) -> RecommendationReport:
        text = (
            f"{case.title} {case.problem_statement} "
            f"{' '.join(case.expected_future_changes)}"
        ).casefold()
        premature = "one implementation" in text or "premature" in text
        provider = any(token in text for token in ("qwen", "provider", "voice"))
        if premature:
            decision = (
                "Keep the implementation local. The proposed abstraction adds concepts and "
                "configuration without containing any credible variation."
            )
            responsibilities = [
                "The existing module continues to own the single behavior.",
                (
                    "Introduce a boundary only when a second implementation or independent "
                    "change appears."
                ),
            ]
        elif provider:
            decision = (
                "Use stable workflow boundaries while each provider owns capability discovery "
                "and provider-specific voice variation. Do not build a universal plugin platform."
            )
            responsibilities = [
                (
                    "Application workflow owns sequencing, resumability, and provider-neutral "
                    "job state."
                ),
                (
                    "Each provider adapter owns voice discovery, validation, and "
                    "provider-specific identifiers."
                ),
                "Presentation consumes provider-neutral capability results.",
            ]
        else:
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
                text=item.text,
                classification=ClaimClassification.CONFIRMED_REQUIREMENT,
            )
            for item in case.confirmed_facts
        ]
        assumptions = [
            Claim(text=item.text, classification=ClaimClassification.SCENARIO_ASSUMPTION)
            for item in [*case.assumptions, *case.unresolved_questions]
        ]
        forces = [
            DesignForce(
                force_id=statement.id,
                title=statement.text,
                description=statement.text,
                importance="high",
            )
            for statement in case.design_forces
        ] or [
            DesignForce(
                title="Locality of change",
                description="Knowledge that changes together should have one owner.",
                importance="high",
            )
        ]
        confidence = Confidence(
            level=ConfidenceLevel.HIGH if packets and repository_claims else ConfidenceLevel.MEDIUM,
            rationale=(
                "Repository evidence and policies support the allocation."
                if repository_claims
                else (
                    "The recommendation is grounded in case context; repository evidence is "
                    "absent."
                )
            ),
        )
        evidence = [*confirmed, *repository_claims, *policy_claims, *assumptions]
        return RecommendationReport(
            decision_summary=decision,
            problem_and_desired_outcome=(
                f"{case.problem_statement}\n\nDesired outcome: {case.desired_outcome}"
            ),
            confirmed_context=confirmed,
            assumptions_and_unresolved_questions=assumptions,
            important_design_forces=forces,
            repository_observations=repository_claims,
            relevant_policies=policy_claims,
            recommended_architecture=decision,
            responsibility_allocation=responsibilities,
            conceptual_interfaces=(
                [
                    "ProviderCapabilities.discover_voices() -> VoiceCatalog",
                    "NarrationProvider.synthesize(request) -> AudioArtifact",
                    "NarrationWorkflow.resume(job_id) -> JobStatus",
                ]
                if provider
                else []
            ),
            alternatives_considered=alternatives,
            scenario_analysis=scenarios,
            change_amplification_analysis=(
                "The recommendation contains provider changes within one adapter and prevents "
                "presentation and workflow modules from coordinating the same change."
                if provider
                else (
                    "No reduction in blast radius justifies an additional abstraction at this "
                    "time."
                )
            ),
            trade_offs=[
                "The chosen boundary adds one explicit contract.",
                "Static evidence cannot prove runtime behavior or human cognitive load.",
            ],
            implementation_sequence=[
                "Name the responsibility and its owner.",
                "Move knowledge behind the focused boundary without changing behavior.",
                "Add contract and workflow tests before removing duplicated knowledge.",
            ],
            confidence=confidence,
            reversal_conditions=[
                (
                    "New evidence shows the responsibility changes independently from its "
                    "proposed owner."
                )
            ],
            revisit_triggers=[
                "A second concrete implementation appears.",
                "A future scenario becomes a committed requirement.",
            ],
            adr=ADRRecord(
                title=f"Architecture decision for {case.title}",
                context=case.problem_statement,
                decision=decision,
                consequences=[
                    "Changing knowledge gains a single explicit owner.",
                    "Unused extension infrastructure is not introduced.",
                ],
            ),
            evidence_appendix=evidence,
        )
