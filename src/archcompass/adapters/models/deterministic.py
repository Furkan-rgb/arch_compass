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
    MetricNature,
    NodeDetailsQuery,
    SignalsQuery,
    SourceExcerptQuery,
)
from archcompass.domain.case import (
    ArchitectureCase,
    CaseAlternative,
    Confidence,
    ConfidenceLevel,
)
from archcompass.domain.consultation import (
    ArchitecturalFinding,
    AtlasEvidenceReference,
    Claim,
    ClaimClassification,
    ClusterQueryPlan,
    ConcernAnalysis,
    ConcernCluster,
    DesignForce,
    FindingImportance,
    FocusedAnalysisPacket,
    FocusedNodeSummary,
    GlobalContext,
    RecommendationDisposition,
    ScenarioEvaluation,
)
from archcompass.domain.conversation import (
    AnswerClaim,
    AnswerStatement,
    AnswerStatementKind,
    CompareFindingsAction,
    ConversationAnswer,
    ConversationEvidenceKind,
    ConversationMessageView,
    ConversationRetrievalAction,
    ConversationSummary,
    ConversationSummaryItem,
    ExplainMetricDefinitionAction,
    FindingDigest,
    GetAlternativeAction,
    GetDependencyNeighbourhoodAction,
    GetFindingAction,
    GetPoliciesAction,
    GetScenarioAction,
    ListFindingsAction,
    ReportConversationContext,
    ReportQuestionPlan,
    ReportQuestionPlanningContext,
    ReportQuestionType,
    SearchAtlasNodesAction,
)
from archcompass.domain.errors import ConversationValidationError
from archcompass.domain.proposals import (
    AvailableClaim,
    ProposedADR,
    ProposedAdvisorClaim,
    ProposedFinding,
    ProposedRecommendation,
    ProposedStatement,
)
from archcompass.ports.reasoning import ReasoningTask


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
    _PROMPTS: ClassVar[dict[ReasoningTask, str]] = {
        ReasoningTask.DISCOVER_DESIGN_FORCES: "discover-design-forces:v3",
        ReasoningTask.CLUSTER_DESIGN_FORCES: "cluster-design-forces:v2",
        ReasoningTask.PLAN_ATLAS_QUERIES: "plan-cluster-atlas-queries:v4",
        ReasoningTask.ANALYZE_CONCERN_CLUSTER: "analyze-concern:v2",
        ReasoningTask.GENERATE_ALTERNATIVES: "generate-alternatives:v2",
        ReasoningTask.EVALUATE_SCENARIOS: "evaluate-scenarios:v2",
        ReasoningTask.SYNTHESIZE_RECOMMENDATION: "synthesize-recommendation:v3",
        ReasoningTask.REPAIR_RECOMMENDATION_PROPOSAL: "repair-recommendation-proposal:v1",
        ReasoningTask.CLASSIFY_REPORT_QUESTION: "classify-report-question:v2",
        ReasoningTask.ANSWER_REPORT_QUESTION: "answer-report-question:v3",
        ReasoningTask.SUMMARIZE_REPORT_CONVERSATION: "summarize-report-conversation:v2",
        ReasoningTask.REPAIR_CONVERSATION_ANSWER: "repair-conversation-answer:v2",
    }

    @property
    def model_identity(self) -> str:
        return "fake:deterministic-architecture-v3"

    def prompt_identity(self, task: ReasoningTask) -> str:
        return self._PROMPTS[task]

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
        if context.atlas_overview is not None and context.atlas_overview.signals:
            leading = context.atlas_overview.signals[0]
            forces.append(
                DesignForce(
                    title=f"Structural observation: {leading.code}",
                    description=(
                        f"The repository overview ranked {leading.code} first. "
                        f"{leading.message} This is a {leading.nature.value}; the static shape "
                        "alone does not establish misplaced responsibility, so it justifies an "
                        "investigation rather than a conclusion."
                    ),
                    importance="high",
                )
            )
        return forces

    def cluster_design_forces(
        self, context: GlobalContext, forces: list[DesignForce]
    ) -> list[ConcernCluster]:
        del context
        grouped: dict[str, list[str]] = {
            "ownership": [],
            "lifecycle": [],
            "change": [],
            "uncertainty": [],
        }
        for force in forces:
            grouped[self._force_category(force)].append(force.force_id)

        specifications = (
            (
                "ownership",
                "Responsibility ownership",
                "Identify the boundary that should own changing knowledge and decisions.",
            ),
            (
                "lifecycle",
                "Lifecycle and operations",
                "Investigate resource ownership, operational state, and cleanup independently.",
            ),
            (
                "change",
                "Change locality and evolution",
                "Assess dependency spread and credible variation independently of ownership.",
            ),
            (
                "uncertainty",
                "Evidence uncertainty",
                "Keep missing evidence and unresolved assumptions explicit and bounded.",
            ),
        )
        return [
            ConcernCluster(
                title=title,
                rationale=rationale,
                design_force_ids=grouped[category],
            )
            for category, title, rationale in specifications
            if grouped[category]
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
        force_lookup = {force.force_id: force for force in forces}
        plans: list[ClusterQueryPlan] = []
        for cluster in clusters:
            if iteration == 1:
                category = self._cluster_category(cluster, force_lookup)
                metric, rationale = {
                    "ownership": (
                        "dependency.fan_in",
                        "Locate highly depended-upon boundaries that may own shared knowledge.",
                    ),
                    "change": (
                        "dependency.fan_out",
                        "Locate dependency-spreading callers that amplify coordinated change.",
                    ),
                    "lifecycle": (
                        "local.branch_count",
                        "Locate decision-heavy code where operational state may be hidden.",
                    ),
                    "uncertainty": (
                        "cognitive_scope.dependency_neighbourhood_modules",
                        "Locate broad structural areas where missing evidence is consequential.",
                    ),
                }[category]
                signal_queries: list[AtlasQuery] = []
                boundary_signal_codes = (
                    [context.atlas_overview.signals[0].code]
                    if context.atlas_overview is not None
                    and context.atlas_overview.signals
                    and category == "ownership"
                    else []
                )
                if boundary_signal_codes:
                    signal_queries.append(
                        SignalsQuery(
                            kind="signals",
                            codes=boundary_signal_codes,
                            limit=8,
                        )
                    )
                plan = AtlasQueryPlan(
                    iteration=iteration,
                    rationale=rationale,
                    queries=[
                        *signal_queries,
                        HotspotsQuery(
                            kind="hotspots",
                            metric=metric,
                            limit=6,
                        ),
                    ],
                )
            elif iteration == 2 and prior_results.get(cluster.cluster_id):
                follow_up_queries: list[AtlasQuery] = []
                for summary in prior_results[cluster.cluster_id]:
                    if not follow_up_queries:
                        follow_up_queries.append(
                            NodeDetailsQuery(
                                kind="node_details",
                                node_id=summary.node_id,
                            )
                        )
                    if summary.location is not None:
                        follow_up_queries.append(
                            SourceExcerptQuery(
                                kind="source_excerpt",
                                node_id=summary.node_id,
                                context_lines=2,
                                max_lines=40,
                            )
                        )
                    if len(follow_up_queries) == 4:
                        break
                plan = AtlasQueryPlan(
                    iteration=iteration,
                    rationale="Inspect a bounded sample of surfaced source nodes.",
                    queries=follow_up_queries,
                )
            else:
                plan = AtlasQueryPlan(
                    iteration=iteration,
                    rationale="Existing evidence is sufficient.",
                    queries=[],
                )
            plans.append(ClusterQueryPlan(cluster_id=cluster.cluster_id, plan=plan))
        return plans

    @staticmethod
    def _force_category(force: DesignForce) -> str:
        text = f"{force.title} {force.description}".casefold()
        if any(
            token in text
            for token in (
                "lifecycle",
                "lifetime",
                "resource ownership",
                "operational",
                "cleanup",
            )
        ):
            return "lifecycle"
        if any(
            token in text
            for token in (
                "uncertain",
                "unknown",
                "missing evidence",
            )
        ):
            return "uncertainty"
        if any(
            token in text
            for token in (
                "change",
                "variation",
                "evolution",
                "locality",
                "growth",
            )
        ):
            return "change"
        return "ownership"

    @classmethod
    def _cluster_category(
        cls,
        cluster: ConcernCluster,
        force_lookup: dict[str, DesignForce],
    ) -> str:
        categories = {
            cls._force_category(force_lookup[force_id])
            for force_id in cluster.design_force_ids
            if force_id in force_lookup
        }
        if len(categories) == 1:
            return categories.pop()
        if "change" in categories:
            return "change"
        if "lifecycle" in categories:
            return "lifecycle"
        if "uncertainty" in categories:
            return "uncertainty"
        return "ownership"

    def analyze_concern_cluster(
        self,
        context: GlobalContext,
        packet: FocusedAnalysisPacket,
    ) -> ConcernAnalysis:
        del context
        findings: list[Claim] = []
        evidence_by_node = {
            evidence.node.node_id: evidence for evidence in packet.node_evidence
        }
        for summary in packet.node_summaries[:4]:
            if summary.location is None:
                continue
            node_evidence = evidence_by_node.get(summary.node_id)
            # Relay whatever the packet surfaced for this node. Recognising particular
            # codes would make the fake's output a function of the fixture rather than
            # of its inputs, which is what the evaluation tier must not reward.
            # Quote only a structural proxy: it is the kind of value that needs
            # architectural interpretation, so relaying its own message is the point.
            # Quoting every routine measurement instead would inflate the claim text
            # until the conversation retrieval budget clamps out real evidence.
            leading_signal = (
                next(
                    (
                        signal
                        for signal in node_evidence.signals
                        if signal.nature is MetricNature.STRUCTURAL_PROXY
                    ),
                    None,
                )
                if node_evidence is not None
                else None
            )
            findings.append(
                Claim(
                    text=(
                        (
                            # "proxy", never "signal": the answer fact-checker treats
                            # "signal <code>" as a citation and would reject prose that
                            # names a code its cited support does not carry.
                            f"Atlas structural proxy {leading_signal.code} reports: "
                            f"{leading_signal.message} This locates "
                            f"{summary.qualified_name or summary.node_id} for investigation. "
                            f"The value is a {leading_signal.nature.value}; the static shape "
                            "alone does not prove misplaced responsibility."
                        )
                        if leading_signal is not None
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
        """Offer the same two credible options for every case.

        Choosing options by scanning the case prose made this fake recognise the
        evaluation fixtures, so the deterministic tier ended up asserting what the fake
        remembered. Preserving the current design is always credible, and one focused
        boundary is always the minimum alternative to it; anything more specific is a
        judgement only a real model can make.
        """

        del context, analyses
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

    def propose_recommendation(
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
        available_claims: list[AvailableClaim],
        cluster_refs: dict[str, str],
    ) -> ProposedRecommendation:
        del context, clusters, alternatives, scenarios

        # Derived from the evidence this provider was actually handed, not from words in
        # the case. A run whose concern analyses surfaced no repository observation has
        # nothing supporting a structural change, and "keep it local" is a complete
        # recommendation in that situation (master plan invariant 16).
        repository_backed_analysis = any(
            finding.classification == ClaimClassification.REPOSITORY_OBSERVATION
            for analysis in analyses
            for finding in analysis.findings
        )
        if not repository_backed_analysis:
            disposition = RecommendationDisposition.KEEP_LOCAL
            decision = (
                "Keep the current structure. No repository observation was surfaced for any "
                "concern cluster, so no evidence supports moving a responsibility yet."
            )
            responsibilities = [
                "The existing owner keeps the behaviour until evidence indicates otherwise.",
            ]
            interfaces: list[str] = []
            amplification = (
                "No blast radius was measured, because no repository evidence reached the "
                "analysis. Change amplification is unknown rather than low."
            )
            trade_offs = [
                "Deferring a boundary avoids interface and configuration overhead now.",
                "It also defers discovering whether one is needed.",
            ]
            sequence = [
                "Record the decision and the evidence that was unavailable.",
                "Revisit once repository evidence or a second implementation appears.",
            ]
        else:
            disposition = RecommendationDisposition.INTRODUCE_BOUNDARY
            decision = (
                "Introduce one focused responsibility boundary around the surfaced evidence, "
                "and preserve all other local behaviour."
            )
            responsibilities = [
                "Assign one owner to each piece of knowledge that changes together.",
                "Leave behaviour with no surfaced evidence exactly where it is.",
            ]
            interfaces = [
                "One narrow port owning the responsibility the evidence located.",
            ]
            amplification = (
                "The surfaced nodes are the measured extent of the change; nodes outside the "
                "focused packets were not examined and are not claimed to be unaffected."
            )
            trade_offs = [
                "One explicit contract in exchange for a contained reason to change.",
                "Static evidence locates structure but cannot prove runtime behaviour.",
            ]
            sequence = [
                "Name the responsibility and its owner.",
                "Move knowledge without changing behaviour.",
                "Add contract tests before removing duplication.",
            ]

        inference_ref = "X1"
        refs_by_cluster: dict[str, list[str]] = {ref: [] for ref in cluster_refs}
        for claim in available_claims:
            if claim.cluster_ref in refs_by_cluster:
                refs_by_cluster[claim.cluster_ref].append(claim.ref)
        support = [*(claim.ref for claim in available_claims), inference_ref]

        def statement(value: str) -> ProposedStatement:
            return ProposedStatement(
                text=value,
                classification=ClaimClassification.ADVISOR_INFERENCE,
                claim_refs=support,
            )

        repository_backed = any(
            claim.classification == ClaimClassification.REPOSITORY_OBSERVATION
            for claim in available_claims
        )
        confidence = Confidence(
            level=(
                ConfidenceLevel.HIGH if packets and repository_backed else ConfidenceLevel.MEDIUM
            ),
            rationale=(
                "Repository evidence and policies support the allocation."
                if repository_backed
                else "The recommendation is grounded in case context without repository evidence."
            ),
        )
        analysis_by_cluster_ref = {
            cluster_ref_of: analysis
            for analysis in analyses
            for cluster_ref_of in [
                next(
                    (
                        claim.cluster_ref
                        for claim in available_claims
                        if claim.cluster_ref is not None
                        and claim.text
                        in {item.text for item in analysis.findings}
                    ),
                    None,
                )
            ]
            if cluster_ref_of is not None
        }
        packet_by_cluster_title = {packet.cluster.title: packet for packet in packets}
        findings: list[ProposedFinding] = []
        for cluster_ref, claim_refs in refs_by_cluster.items():
            if not claim_refs:
                continue
            analysis = analysis_by_cluster_ref.get(cluster_ref)
            title = cluster_refs[cluster_ref]
            packet = packet_by_cluster_title.get(title)
            high_importance = any(
                force.importance.casefold() in {"high", "critical"}
                for force in forces
                if packet is not None and force.force_id in packet.cluster.design_force_ids
            )
            findings.append(
                ProposedFinding(
                    cluster_ref=cluster_ref,
                    title=title,
                    summary=" ".join(
                        claim.text
                        for claim in available_claims
                        if claim.ref in set(claim_refs)
                    ),
                    importance=(
                        FindingImportance.HIGH if high_importance else FindingImportance.MEDIUM
                    ),
                    importance_rationale=(
                        "The concern combines a high-priority design force with located "
                        "repository or policy evidence."
                        if high_importance
                        else "The concern materially affects the recorded responsibility decision."
                    ),
                    confidence=confidence,
                    consequence=(
                        analysis.implications[0]
                        if analysis is not None and analysis.implications
                        else "The concern may increase change amplification."
                    ),
                    claim_refs=claim_refs,
                    recommended_response=decision,
                    uncertainty=(
                        packet.uncertainty
                        if packet is not None and packet.uncertainty
                        else [
                            "The finding reflects persisted static and contextual evidence; "
                            "runtime behavior may add information."
                        ]
                    ),
                )
            )
        for cluster_ref in cluster_refs:
            if any(item.cluster_ref == cluster_ref for item in findings):
                continue
            findings.append(
                ProposedFinding(
                    cluster_ref=cluster_ref,
                    title="Architecture recommendation",
                    summary=decision,
                    importance=FindingImportance.MEDIUM,
                    importance_rationale=(
                        "The recommendation is material, but no concern analysis or repository "
                        "evidence was supplied to this deterministic synthesis path."
                    ),
                    confidence=confidence,
                    consequence=(
                        "The recommendation should be revisited when concern analysis or "
                        "repository evidence becomes available."
                    ),
                    claim_refs=support,
                    recommended_response=decision,
                    uncertainty=[
                        "No concern analysis was supplied for this recommendation."
                    ],
                )
            )

        return ProposedRecommendation(
            disposition=disposition.value,
            problem_and_desired_outcome=(
                f"{case.problem_statement}\n\nDesired outcome: {case.desired_outcome}"
            ),
            confidence=confidence,
            advisor_claims=[
                ProposedAdvisorClaim(
                    ref=inference_ref,
                    text=(
                        "The recommendation follows from the combined ownership, locality, "
                        "policy, and repository evidence."
                    ),
                    classification=ClaimClassification.ADVISOR_INFERENCE,
                )
            ],
            findings=findings,
            decision_summary=statement(decision),
            recommended_architecture=statement(decision),
            responsibility_allocation=[statement(item) for item in responsibilities],
            conceptual_interfaces=[statement(item) for item in interfaces],
            change_amplification_analysis=statement(amplification),
            trade_offs=[statement(item) for item in trade_offs],
            implementation_sequence=[statement(item) for item in sequence],
            reversal_conditions=[
                statement(
                    "New evidence shows the responsibility changes independently from its owner."
                )
            ],
            revisit_triggers=[
                statement("A second concrete implementation appears."),
                statement("A future scenario becomes a committed requirement."),
            ],
            adr=ProposedADR(
                title=f"Architecture decision for {case.title}",
                context=case.problem_statement,
                decision=statement(decision),
                consequences=[
                    statement("Changing knowledge gains a single explicit owner."),
                    statement("Unused extension infrastructure is not introduced."),
                ],
            ),
        )

    def repair_recommendation_proposal(
        self,
        proposal: ProposedRecommendation,
        errors: list[str],
        *,
        available_claims: list[AvailableClaim],
        cluster_refs: dict[str, str],
    ) -> ProposedRecommendation:
        del errors, cluster_refs
        allowed = {claim.ref for claim in available_claims} | {
            claim.ref for claim in proposal.advisor_claims
        }
        cluster_of = {
            claim.ref: claim.cluster_ref
            for claim in available_claims
            if claim.cluster_ref is not None
        }

        def prune(statement: ProposedStatement) -> ProposedStatement:
            refs = [ref for ref in statement.claim_refs if ref in allowed]
            return statement.model_copy(update={"claim_refs": refs or sorted(allowed)[:1]})

        def prune_finding(finding: ProposedFinding) -> ProposedFinding:
            refs = [
                ref
                for ref in finding.claim_refs
                if ref in allowed
                and cluster_of.get(ref, finding.cluster_ref) == finding.cluster_ref
            ]
            own = sorted(
                ref for ref, owner in cluster_of.items() if owner == finding.cluster_ref
            )
            return finding.model_copy(update={"claim_refs": refs or own[:1]})

        return proposal.model_copy(
            update={
                "findings": [prune_finding(item) for item in proposal.findings],
                "decision_summary": prune(proposal.decision_summary),
                "recommended_architecture": prune(proposal.recommended_architecture),
                "responsibility_allocation": [
                    prune(item) for item in proposal.responsibility_allocation
                ],
                "conceptual_interfaces": [
                    prune(item) for item in proposal.conceptual_interfaces
                ],
                "change_amplification_analysis": prune(proposal.change_amplification_analysis),
                "trade_offs": [prune(item) for item in proposal.trade_offs],
                "implementation_sequence": [
                    prune(item) for item in proposal.implementation_sequence
                ],
                "reversal_conditions": [prune(item) for item in proposal.reversal_conditions],
                "revisit_triggers": [prune(item) for item in proposal.revisit_triggers],
            }
        )

    def classify_report_question(
        self,
        context: ReportQuestionPlanningContext,
    ) -> ReportQuestionPlan:
        question = context.question
        report_summary = context.report_summary
        findings = context.finding_digests
        text = question.casefold()
        finding_ids = self._finding_references(question, findings)
        comparison_question = any(
            term in text
            for term in ("compare", "difference", "versus", " vs ", "between")
        )
        normalized_question = " ".join(question.casefold().split())
        title_matches = [
            item.finding_id
            for item in findings
            if " ".join(item.title.casefold().split()) in normalized_question
        ]
        if len(title_matches) > 1 and not comparison_question:
            raise ConversationValidationError(
                "The question references multiple finding titles outside a comparison"
            )
        finding_ids = self._resolve_contextual_finding_references(
            context,
            finding_ids,
            comparison=comparison_question,
        )
        question_types: list[ReportQuestionType] = []
        actions: list[ConversationRetrievalAction] = []
        if comparison_question:
            question_types.append(ReportQuestionType.COMPARE_FINDINGS)
            if len(finding_ids) < 2:
                raise ConversationValidationError(
                    "A comparison requires at least two unambiguous finding references"
                )
            actions.append(
                CompareFindingsAction(kind="compare_findings", finding_ids=finding_ids)
            )
        elif any(term in text for term in ("most important", "highest priority", "priority")):
            question_types.append(ReportQuestionType.FINDING_PRIORITY)
        elif any(term in text for term in ("finding", "findings", "main result")):
            question_types.append(
                ReportQuestionType.FINDING_DETAILS
                if finding_ids
                else ReportQuestionType.LIST_FINDINGS
            )
            actions.extend(
                GetFindingAction(kind="get_finding", finding_id=finding_id)
                for finding_id in finding_ids
            )
            if not finding_ids:
                actions.append(ListFindingsAction(kind="list_findings", limit=12))
        elif finding_ids:
            question_types.append(ReportQuestionType.FINDING_DETAILS)
            actions.extend(
                GetFindingAction(kind="get_finding", finding_id=finding_id)
                for finding_id in finding_ids
            )
        if any(
            term in text
            for term in ("evidence", "support", "code behind", "depend", "blast radius")
        ):
            question_types.append(ReportQuestionType.EVIDENCE_TRACE)
        if any(term in text for term in ("source", "code")):
            question_types.append(ReportQuestionType.SOURCE_EXPLANATION)
        if "polic" in text:
            question_types.append(ReportQuestionType.POLICY_EXPLANATION)
        if "alternative" in text or "rejected" in text:
            question_types.append(ReportQuestionType.ALTERNATIVE_EXPLANATION)
            actions.extend(
                GetAlternativeAction(kind="get_alternative", alternative_id=item.id)
                for item in report_summary.alternatives[:5]
            )
        if "scenario" in text:
            question_types.append(ReportQuestionType.SCENARIO_EXPLANATION)
            actions.extend(
                GetScenarioAction(kind="get_scenario", ordinal=ordinal)
                for ordinal, _ in enumerate(report_summary.scenarios[:4], start=1)
            )
        if "assumption" in text:
            question_types.append(ReportQuestionType.ASSUMPTION_REVIEW)
        if any(term in text for term in ("implement first", "implementation order", "start first")):
            question_types.append(ReportQuestionType.IMPLEMENTATION_ORDER)
        if any(
            term in text
            for term in (
                "what if",
                "would change if",
                "still valid if",
                "if we ignored",
                "if ignored",
                "ignore this",
            )
        ):
            question_types.append(ReportQuestionType.COUNTERFACTUAL)
        atlas_search = re.search(
            r"\b(?:search|find)\s+(?:the\s+)?(?:pinned\s+)?"
            r"(?:atlas|repository)(?:\s+for)?\s+(.+)",
            text,
        )
        search_terms: list[str] = []
        if atlas_search:
            # Dotted names are real (module.symbol), but a sentence-ending period is
            # not part of the identifier being searched for.
            search_terms = [
                stripped
                for term in re.findall(r"[a-z0-9_.-]+", atlas_search.group(1))
                if (stripped := term.strip(".-"))
            ][:10]
            if search_terms:
                question_types.append(ReportQuestionType.EVIDENCE_TRACE)
                actions.append(
                    SearchAtlasNodesAction(
                        kind="search_atlas_nodes",
                        terms=search_terms,
                        limit=12,
                    )
                )
        claim_ids: list[str] = []
        node_ids = [
            item.artifact_id
            for item in context.prior_evidence_references
            if item.kind is ConversationEvidenceKind.ATLAS_NODE
            and item.artifact_id.casefold() in text
        ][:24]
        if (
            not node_ids
            and any(term in text for term in ("depend", "interface", "module", "node"))
            and any(
                phrase in text
                for phrase in ("this interface", "this module", "this node", "it")
            )
        ):
            recent_evidence_ids = next(
                (
                    item.relevant_evidence_ids
                    for item in reversed(context.recent_messages)
                    if item.relevant_evidence_ids
                ),
                list[str](),
            )
            contextual_nodes = list(
                dict.fromkeys(
                    reference.artifact_id
                    for reference in context.prior_evidence_references
                    if reference.kind is ConversationEvidenceKind.ATLAS_NODE
                    and reference.evidence_id in set(recent_evidence_ids)
                )
            )
            if len(contextual_nodes) != 1:
                raise ConversationValidationError(
                    "The recent conversation does not identify one unambiguous Atlas node"
                )
            node_ids = contextual_nodes
        policy_ids: list[str] = []
        if "metric" in text and any(
            term in text for term in ("define", "definition", "mean")
        ):
            metric_names = re.findall(
                r"\b(?:dependency|change_amplification|cognitive_scope|local)"
                r"\.[a-z_]+\b",
                text,
            )[:8]
            if metric_names:
                question_types.append(ReportQuestionType.EVIDENCE_TRACE)
                actions.append(
                    ExplainMetricDefinitionAction(
                        kind="explain_metric_definition",
                        metric_names=metric_names,
                    )
                )
        if ReportQuestionType.POLICY_EXPLANATION in question_types:
            selected_policy_ids = [item.id for item in report_summary.policies[:8]]
            if selected_policy_ids:
                actions.append(
                    GetPoliciesAction(
                        kind="get_policies",
                        policy_ids=selected_policy_ids,
                    )
                )
                policy_ids = selected_policy_ids
        if node_ids and any(term in text for term in ("depend", "blast radius")):
            actions.append(
                GetDependencyNeighbourhoodAction(
                    kind="get_dependency_neighbourhood",
                    node_id=node_ids[0],
                    direction="reverse",
                    depth=2,
                    limit=24,
                )
            )
        if not question_types:
            question_types = [
                ReportQuestionType.REPORT_SUMMARY
                if any(
                    term in text
                    for term in (
                        "summary",
                        "summarize",
                        "summarise",
                        "overview",
                        "recommendation",
                        "decision",
                    )
                )
                else ReportQuestionType.GENERAL_REPORT_QUESTION
            ]
        unique_actions: dict[str, ConversationRetrievalAction] = {}
        for action in actions:
            unique_actions.setdefault(action.model_dump_json(), action)
        return ReportQuestionPlan(
            question_types=list(dict.fromkeys(question_types)),
            finding_ids=finding_ids,
            report_claim_ids=claim_ids,
            atlas_node_ids=node_ids,
            policy_ids=policy_ids,
            search_terms=search_terms,
            retrieval_actions=list(unique_actions.values())[:8],
            rationale=(
                "Classified deterministically from the bounded pinned report, case, "
                "summary, recent-message, and prior-reference context."
            ),
        )

    @staticmethod
    def _resolve_contextual_finding_references(
        context: ReportQuestionPlanningContext,
        explicit: list[str],
        *,
        comparison: bool,
    ) -> list[str]:
        text = " ".join(context.question.casefold().split())
        recent = next(
            (
                item.relevant_finding_ids
                for item in reversed(context.recent_messages)
                if item.relevant_finding_ids
            ),
            list[str](),
        )
        summary_ids = (
            context.conversation_summary.discussed_finding_ids
            if context.conversation_summary is not None
            else []
        )
        singular = any(
            phrase in text
            for phrase in ("this finding", "that finding", "this issue", "that issue")
        )
        plural = any(
            phrase in text
            for phrase in ("these two", "both findings", "the two findings")
        )
        resolved = list(explicit)
        if singular:
            candidates = recent or summary_ids
            if len(candidates) != 1:
                raise ConversationValidationError(
                    "The bounded conversation context does not identify one finding"
                )
            resolved.extend(candidates)
        if plural:
            candidates = recent or summary_ids
            if len(candidates) != 2:
                raise ConversationValidationError(
                    "The bounded conversation context does not identify exactly two findings"
                )
            resolved.extend(candidates)
        if any(phrase in text for phrase in ("the former", "former finding")):
            candidates = recent or summary_ids
            if len(candidates) < 2:
                raise ConversationValidationError(
                    "The bounded conversation context has no unambiguous former finding"
                )
            resolved.append(candidates[0])
        if any(phrase in text for phrase in ("the latter", "latter finding")):
            candidates = recent or summary_ids
            if len(candidates) < 2:
                raise ConversationValidationError(
                    "The bounded conversation context has no unambiguous latter finding"
                )
            resolved.append(candidates[1])
        resolved = list(dict.fromkeys(resolved))
        if len(resolved) > 1 and singular and not comparison:
            raise ConversationValidationError(
                "The question resolves to multiple findings; use canonical finding IDs"
            )
        return resolved[:12]

    @staticmethod
    def _finding_references(
        question: str,
        findings: list[ArchitecturalFinding] | list[FindingDigest],
    ) -> list[str]:
        text = " ".join(question.casefold().split())
        referenced = [
            finding.finding_id
            for finding in findings
            if finding.finding_id.casefold() in text
            or " ".join(finding.title.casefold().split()) in text
        ]
        ordinal_words = {
            "first finding": 0,
            "second finding": 1,
            "third finding": 2,
            "fourth finding": 3,
            "fifth finding": 4,
            "sixth finding": 5,
            "seventh finding": 6,
            "eighth finding": 7,
            "ninth finding": 8,
            "tenth finding": 9,
            "eleventh finding": 10,
            "twelfth finding": 11,
        }
        for phrase, index in ordinal_words.items():
            if phrase in text and index < len(findings):
                referenced.append(findings[index].finding_id)
        for match in re.finditer(
            r"\b(?:(?:finding\s+)(\d+)|(\d+)(?:st|nd|rd|th)?\s+finding)\b",
            text,
        ):
            raw = match.group(1) or match.group(2)
            index = int(raw) - 1
            if 0 <= index < len(findings):
                referenced.append(findings[index].finding_id)
        return list(dict.fromkeys(referenced))[:12]

    def answer_report_question(
        self,
        context: ReportConversationContext,
    ) -> ConversationAnswer:
        text = context.question.casefold()
        question_types = set(context.question_plan.question_types)
        selected_ids = set(context.question_plan.finding_ids)
        relevant = [
            item
            for item in context.finding_digests
            if not selected_ids or item.finding_id in selected_ids
        ]
        if not relevant:
            relevant = list(context.finding_digests)
        detailed = {item.finding_id: item for item in context.retrieved_findings}
        report_context_references = [
            item
            for item in context.evidence_references
            if item.kind is ConversationEvidenceKind.REPORT_CONTEXT
        ]
        report_context_ids = [
            item.evidence_id
            for item in report_context_references
            if item.artifact_id == context.report_summary.report_id
        ]
        case_context_ids = [
            item.evidence_id
            for item in report_context_references
            if item.artifact_id
            == f"{context.pinned_case.case_id}@{context.pinned_case.revision}"
        ]
        report_support = AnswerClaim(
            text="This answer is bounded to the immutable report supplied for this conversation.",
            classification=ClaimClassification.ADVISOR_INFERENCE,
            evidence_ids=report_context_ids,
        )
        case_support = AnswerClaim(
            text="The counterfactual and assumption context comes from the exact pinned case.",
            classification=ClaimClassification.ADVISOR_INFERENCE,
            evidence_ids=case_context_ids,
        )
        answer_claims: list[AnswerClaim] = [report_support, case_support]
        claim_answer_ids: dict[str, str] = {}
        for claim in context.retrieved_claims[:8]:
            evidence_ids = [
                item.evidence_id
                for item in context.evidence_references
                if (
                    item.kind is ConversationEvidenceKind.REPORT_CLAIM
                    and item.artifact_id == claim.claim_id
                )
                or (
                    item.node_id is not None
                    and item.node_id
                    in {reference.node_id for reference in claim.atlas_references}
                )
            ]
            finding_ids = [
                finding_id
                for finding_id, finding in detailed.items()
                if claim.claim_id in finding.claim_ids
            ]
            candidate = AnswerClaim(
                text=claim.text,
                classification=claim.classification,
                evidence_ids=list(dict.fromkeys(evidence_ids))[:48],
                finding_ids=finding_ids,
                report_claim_ids=[claim.claim_id],
                policy_ids=[
                    policy_id
                    for policy_id in claim.policy_ids
                    if any(
                        item.policy.id == policy_id
                        for item in context.retrieved_policies
                    )
                ],
            )
            answer_claims.append(candidate)
            claim_answer_ids[claim.claim_id] = candidate.claim_id
        policy_answer_ids: list[str] = []
        if ReportQuestionType.POLICY_EXPLANATION in question_types:
            selected_policies = context.retrieved_policies
        else:
            selected_policies = []
        for policy in selected_policies:
            candidate = AnswerClaim(
                text=(
                    " | ".join(
                        f"{chunk.section}: {chunk.text}"
                        for chunk in policy.chunks
                    )
                    or policy.policy.body
                ),
                classification=ClaimClassification.POLICY_GUIDANCE,
                evidence_ids=[
                    item.evidence_id
                    for item in context.evidence_references
                    if item.kind is ConversationEvidenceKind.POLICY
                    and item.artifact_id == policy.policy.id
                ],
                policy_ids=[policy.policy.id],
            )
            answer_claims.append(candidate)
            policy_answer_ids.append(candidate.claim_id)
        artifact_kinds: set[ConversationEvidenceKind] = set()
        if ReportQuestionType.EVIDENCE_TRACE in question_types:
            artifact_kinds.update(
                {
                    ConversationEvidenceKind.ATLAS_NODE,
                    ConversationEvidenceKind.ATLAS_RELATIONSHIP,
                    ConversationEvidenceKind.ATLAS_METRIC,
                    ConversationEvidenceKind.ATLAS_SIGNAL,
                    ConversationEvidenceKind.SOURCE_EXCERPT,
                    ConversationEvidenceKind.TEST,
                    ConversationEvidenceKind.METRIC_DEFINITION,
                    ConversationEvidenceKind.RETRIEVAL_UNAVAILABLE,
                }
            )
        if ReportQuestionType.SOURCE_EXPLANATION in question_types:
            artifact_kinds.update(
                {
                    ConversationEvidenceKind.SOURCE_EXCERPT,
                    ConversationEvidenceKind.RETRIEVAL_UNAVAILABLE,
                }
            )
        if ReportQuestionType.ALTERNATIVE_EXPLANATION in question_types:
            artifact_kinds.add(ConversationEvidenceKind.ALTERNATIVE)
        if ReportQuestionType.SCENARIO_EXPLANATION in question_types:
            artifact_kinds.add(ConversationEvidenceKind.SCENARIO)
        artifact_answer_ids: dict[ConversationEvidenceKind, list[str]] = {}
        for reference in context.evidence_references:
            if reference.kind not in artifact_kinds:
                continue
            candidate = AnswerClaim(
                text=(
                    f"Supplied {reference.kind.value} artifact "
                    f"{reference.artifact_id} is available to this answer."
                ),
                classification=(
                    ClaimClassification.REPOSITORY_OBSERVATION
                    if reference.kind
                    in {
                        ConversationEvidenceKind.ATLAS_NODE,
                        ConversationEvidenceKind.ATLAS_RELATIONSHIP,
                        ConversationEvidenceKind.ATLAS_METRIC,
                        ConversationEvidenceKind.ATLAS_SIGNAL,
                        ConversationEvidenceKind.SOURCE_EXCERPT,
                        ConversationEvidenceKind.TEST,
                        ConversationEvidenceKind.METRIC_DEFINITION,
                    }
                    else ClaimClassification.ADVISOR_INFERENCE
                ),
                evidence_ids=[reference.evidence_id],
            )
            answer_claims.append(candidate)
            artifact_answer_ids.setdefault(reference.kind, []).append(candidate.claim_id)
            if len(answer_claims) == 20:
                break

        direct_support_ids = [report_support.claim_id]
        direct_finding_ids: list[str] = []
        uncertainty_texts: list[str] = []
        if any(term in text for term in ("latency", "production", "runtime")):
            direct = (
                "The pinned report and RepositoryAtlas contain no runtime production "
                "evidence for that question."
            )
            uncertainty_texts.append(
                "Runtime tracing and production telemetry are outside this consultation."
            )
        elif ReportQuestionType.FINDING_PRIORITY in question_types:
            order = {
                FindingImportance.CRITICAL: 3,
                FindingImportance.HIGH: 2,
                FindingImportance.MEDIUM: 1,
                FindingImportance.LOW: 0,
            }
            confidence_order = {
                ConfidenceLevel.HIGH: 2,
                ConfidenceLevel.MEDIUM: 1,
                ConfidenceLevel.LOW: 0,
            }
            priority_candidates = list(context.finding_digests)
            highest = max(
                priority_candidates,
                key=lambda item: (
                    order[item.importance],
                    confidence_order[item.confidence.level],
                    -context.finding_digests.index(item),
                ),
            )
            direct = (
                f"{highest.finding_id} — {highest.title} is the highest contextual priority. "
                f"{highest.importance_rationale} Consequence: {highest.consequence} "
                f"Confidence is {highest.confidence.level.value} because "
                f"{highest.confidence.rationale}"
            )
            relevant = [highest]
            direct_finding_ids = [highest.finding_id]
        elif ReportQuestionType.COMPARE_FINDINGS in question_types and len(relevant) >= 2:
            compared = relevant[: min(12, len(relevant))]
            direct = "Comparison: " + " ".join(
                (
                    f"{item.finding_id} — {item.title} is {item.importance.value} importance "
                    f"with {item.confidence.level.value} confidence; "
                    f"{item.consequence}"
                )
                for item in compared
            )
            relevant = compared
            direct_finding_ids = [item.finding_id for item in compared]
        elif ReportQuestionType.COUNTERFACTUAL in question_types:
            weakening = any(
                term in text
                for term in (
                    "never",
                    "no second",
                    "removed",
                    "remove ",
                    "not required",
                    "remain small",
                    "stays small",
                )
            )
            direction = "weakens" if weakening else "strengthens or redirects"
            direct = (
                "Under that hypothetical condition, the original recommendation remains the "
                f"historical decision. The changed condition {direction} the relevant design "
                "force; responsibility ownership and evidence-validation boundaries remain "
                "applicable where their underlying constraints are unchanged. An official "
                "change requires revising the ArchitectureCase and running a new consultation."
            )
            direct_finding_ids = [item.finding_id for item in relevant[:4]]
            direct_support_ids.append(case_support.claim_id)
            uncertainty_texts.append(
                "This is exploratory counterfactual analysis, not a revised recommendation."
            )
        elif ReportQuestionType.SOURCE_EXPLANATION in question_types:
            excerpts = [
                item
                for evidence in context.retrieved_atlas_evidence
                for item in evidence.excerpts
            ]
            direct = "The bounded source evidence is: " + "; ".join(
                (
                    f"{item.node_id} at {item.location.path}:"
                    f"{item.location.start_line}-{item.location.end_line}"
                )
                for item in excerpts
            )
            if not excerpts:
                direct = (
                    "The requested source excerpt is unavailable from the exact pinned "
                    "repository contents."
                )
            direct_finding_ids = [item.finding_id for item in relevant]
            direct_support_ids.extend(
                artifact_answer_ids.get(ConversationEvidenceKind.SOURCE_EXCERPT, [])
            )
            direct_support_ids.extend(
                artifact_answer_ids.get(
                    ConversationEvidenceKind.RETRIEVAL_UNAVAILABLE,
                    [],
                )
            )
        elif ReportQuestionType.EVIDENCE_TRACE in question_types:
            evidence_descriptions = [
                item.query_summary
                for item in context.retrieved_atlas_evidence
                if item.query_summary
            ]
            direct = "The selected findings are supported by: " + "; ".join(
                (
                    f"{item.finding_id} cites claims {', '.join(item.claim_ids)}, "
                    f"Atlas nodes {', '.join(item.atlas_node_ids) or 'none'}, and "
                    f"policies {', '.join(item.policy_ids) or 'none'}"
                )
                for item in context.retrieved_findings
            )
            if evidence_descriptions:
                direct += " Retrieved evidence: " + "; ".join(evidence_descriptions)
            direct_finding_ids = [item.finding_id for item in relevant]
            direct_support_ids.extend(claim_answer_ids.values())
            direct_support_ids.extend(
                claim_id
                for kind, claim_ids in artifact_answer_ids.items()
                if kind
                not in {
                    ConversationEvidenceKind.ALTERNATIVE,
                    ConversationEvidenceKind.SCENARIO,
                }
                for claim_id in claim_ids
            )
        elif (
            ReportQuestionType.POLICY_EXPLANATION in question_types
            and context.retrieved_policies
        ):
            direct = "The pinned policies inform the recommendation as follows: " + "; ".join(
                (
                    f"{item.policy.id} — {item.policy.title}: "
                    f"scope={item.policy.scope.value}, "
                    f"strength={item.policy.strength.value}, "
                    f"applies_to={item.policy.applies_to or 'all applicable cases'}. "
                    + (
                        " ".join(
                            f"{chunk.section}: {chunk.text}"
                            for chunk in item.chunks
                        )
                        or item.policy.body
                    )
                )
                for item in context.retrieved_policies
            )
            direct_support_ids.extend(policy_answer_ids)
        elif (
            ReportQuestionType.ALTERNATIVE_EXPLANATION in question_types
            and context.retrieved_alternatives
        ):
            direct = "The recorded alternatives are: " + "; ".join(
                f"{item.id} — {item.title}: {item.summary}"
                for item in context.retrieved_alternatives
            )
            direct_support_ids.extend(
                artifact_answer_ids.get(ConversationEvidenceKind.ALTERNATIVE, [])
            )
        elif (
            ReportQuestionType.SCENARIO_EXPLANATION in question_types
            and context.retrieved_scenarios
        ):
            direct = "The recorded scenario analysis is: " + "; ".join(
                (
                    f"{item.scenario}: assumptions={', '.join(item.assumptions) or 'none'}; "
                    f"{item.conclusion}"
                )
                for item in context.retrieved_scenarios
            )
            direct_support_ids.extend(
                artifact_answer_ids.get(ConversationEvidenceKind.SCENARIO, [])
            )
        elif ReportQuestionType.ASSUMPTION_REVIEW in question_types:
            assumptions = context.pinned_case.assumptions
            direct = (
                "The pinned case assumptions that may weaken the recommendation are: "
                + ("; ".join(assumptions) if assumptions else "none were recorded.")
            )
            direct_support_ids = [case_support.claim_id]
        elif ReportQuestionType.IMPLEMENTATION_ORDER in question_types:
            direct = "The recorded implementation order starts with: " + "; ".join(
                item.text for item in context.report_summary.implementation_sequence
            )
        elif ReportQuestionType.FINDING_DETAILS in question_types:
            direct = "Finding detail: " + "; ".join(
                (
                    f"{item.finding_id} — {item.title}: {item.summary} "
                    f"Importance: {item.importance.value}, because "
                    f"{item.importance_rationale} Consequence: {item.consequence} "
                    + (
                        f"Recommended response: {detailed[item.finding_id].recommended_response}"
                        if item.finding_id in detailed
                        else ""
                    )
                )
                for item in relevant
            )
            direct_finding_ids = [item.finding_id for item in relevant]
        elif ReportQuestionType.LIST_FINDINGS in question_types:
            direct = "The canonical findings are: " + "; ".join(
                f"{item.finding_id} — {item.title}: {item.summary}" for item in relevant
            )
            direct_finding_ids = [item.finding_id for item in relevant]
        else:
            if ReportQuestionType.REPORT_SUMMARY in question_types:
                direct = (
                    f"The pinned report recommends: "
                    f"{context.report_summary.decision_summary.text}"
                )
            else:
                direct = (
                    "The bounded consultation evidence does not support a factual answer "
                    "to that question."
                )
                uncertainty_texts.append(
                    "Ask about the report, its findings, evidence, policies, alternatives, "
                    "scenarios, assumptions, or implementation order."
                )
        direct_support_ids = list(dict.fromkeys(direct_support_ids))
        relevant_ids = list(dict.fromkeys(direct_finding_ids))[:12]
        direct_statement = AnswerStatement(
            text=direct,
            kind=AnswerStatementKind.DIRECT_ANSWER,
            answer_claim_ids=direct_support_ids,
            finding_ids=direct_finding_ids,
        )
        supporting_points = [
            AnswerStatement(
                text=f"{item.finding_id}: {item.importance_rationale}",
                kind=AnswerStatementKind.SUPPORTING_POINT,
                finding_ids=[item.finding_id],
            )
            for item in (relevant[:4] if direct_finding_ids else [])
        ]
        uncertainty = [
            AnswerStatement(
                text=item,
                kind=AnswerStatementKind.UNCERTAINTY,
                answer_claim_ids=[report_support.claim_id],
                finding_ids=direct_finding_ids[:4],
            )
            for item in uncertainty_texts
        ]
        used_answer_claim_ids = {
            claim_id
            for statement in [direct_statement, *supporting_points, *uncertainty]
            for claim_id in statement.answer_claim_ids
        }
        answer_claims = [
            item
            for item in answer_claims
            if item.claim_id in used_answer_claim_ids
        ][:20]
        # If a provider-neutral branch did not need detailed claims, retain only the
        # report-context claim that explicitly grounds the bounded answer.
        retained_claim_ids = {item.claim_id for item in answer_claims}
        direct_statement = direct_statement.model_copy(
            update={
                "answer_claim_ids": [
                    item
                    for item in direct_statement.answer_claim_ids
                    if item in retained_claim_ids
                ]
            }
        )
        return ConversationAnswer(
            direct_answer=direct_statement,
            supporting_points=supporting_points,
            claims=answer_claims,
            relevant_finding_ids=relevant_ids,
            uncertainty=uncertainty,
            suggested_follow_up_questions=[
                "Which evidence supports this finding?",
                "What would justify revisiting this recommendation?",
            ],
        )

    def summarize_report_conversation(
        self,
        current_summary: ConversationSummary | None,
        messages: list[ConversationMessageView],
    ) -> ConversationSummary:
        additions = " ".join(
            f"[{message.ordinal}] {message.role.value}: {message.text}"
            for message in messages
        ).strip()
        if len(additions) >= 6000:
            narrative = additions[-6000:]
        else:
            prior = current_summary.narrative.strip() if current_summary else ""
            available = 6000 - len(additions) - (1 if prior and additions else 0)
            retained_prior = prior[-max(0, available) :] if available else ""
            narrative = " ".join(
                item for item in (retained_prior, additions) if item
            )
        discussed_finding_ids: list[str] = []
        for finding_id in [
            *(
                current_summary.discussed_finding_ids
                if current_summary is not None
                else []
            ),
            *(
                finding_id
                for message in messages
                for finding_id in message.relevant_finding_ids
            ),
        ]:
            if finding_id not in discussed_finding_ids:
                discussed_finding_ids.append(finding_id)
        discussed_finding_ids = discussed_finding_ids[-12:]
        discussed_evidence_ids: list[str] = []
        for evidence_id in [
            *(
                current_summary.discussed_evidence_ids
                if current_summary is not None
                else []
            ),
            *(
                evidence_id
                for message in messages
                for evidence_id in message.relevant_evidence_ids
            ),
        ]:
            if evidence_id not in discussed_evidence_ids:
                discussed_evidence_ids.append(evidence_id)
        discussed_evidence_ids = discussed_evidence_ids[-96:]

        def retained_items(
            existing: list[ConversationSummaryItem],
            *,
            cues: tuple[str, ...],
        ) -> list[ConversationSummaryItem]:
            new_items = [
                ConversationSummaryItem(
                    text=message.text[:1000],
                    source_ordinals=[message.ordinal],
                    finding_ids=message.relevant_finding_ids,
                    evidence_ids=message.relevant_evidence_ids[:24],
                )
                for message in messages
                if message.role.value == "user"
                and any(cue in message.text.casefold() for cue in cues)
            ]
            by_ordinal: dict[tuple[int, ...], ConversationSummaryItem] = {
                tuple(item.source_ordinals): item for item in existing
            }
            for item in new_items:
                by_ordinal[tuple(item.source_ordinals)] = item
            return list(by_ordinal.values())[-12:]

        prior_corrections = (
            current_summary.user_corrections if current_summary is not None else []
        )
        prior_hypotheticals = (
            current_summary.hypotheticals if current_summary is not None else []
        )
        prior_unresolved = (
            current_summary.unresolved_questions if current_summary is not None else []
        )
        return ConversationSummary(
            narrative=narrative or "No conversation content was available.",
            discussed_finding_ids=discussed_finding_ids,
            discussed_evidence_ids=discussed_evidence_ids,
            user_corrections=retained_items(
                prior_corrections,
                cues=("actually", "correction", "instead", "i meant"),
            ),
            hypotheticals=retained_items(
                prior_hypotheticals,
                cues=("what if", "hypothetical", "suppose", "if "),
            ),
            unresolved_questions=retained_items(
                prior_unresolved,
                cues=("unresolved", "unknown", "not sure", "need to know"),
            ),
        )

    def repair_conversation_answer(
        self,
        answer: ConversationAnswer,
        errors: list[str],
        allowed_finding_ids: set[str],
        allowed_claim_ids: set[str],
        allowed_evidence_ids: set[str],
        allowed_policy_ids: set[str],
    ) -> ConversationAnswer:
        del errors
        repaired_claims: list[AnswerClaim] = []
        for claim in answer.claims:
            report_claim_ids = [
                claim_id
                for claim_id in claim.report_claim_ids
                if claim_id in allowed_claim_ids
            ]
            evidence_ids = [
                evidence_id
                for evidence_id in claim.evidence_ids
                if evidence_id in allowed_evidence_ids
            ]
            policy_ids = [
                policy_id for policy_id in claim.policy_ids if policy_id in allowed_policy_ids
            ]
            finding_ids = [
                finding_id
                for finding_id in claim.finding_ids
                if finding_id in allowed_finding_ids
            ]
            if not (report_claim_ids or evidence_ids or policy_ids or finding_ids):
                continue
            if (
                claim.classification == ClaimClassification.POLICY_GUIDANCE
                and not policy_ids
            ):
                continue
            repaired_claims.append(
                claim.model_copy(
                    update={
                        "report_claim_ids": report_claim_ids,
                        "evidence_ids": evidence_ids,
                        "policy_ids": policy_ids,
                        "finding_ids": finding_ids,
                    }
                )
            )
        retained_claim_ids = {item.claim_id for item in repaired_claims}

        def repair_statement(
            statement: AnswerStatement,
        ) -> AnswerStatement | None:
            repaired = statement.model_copy(
                update={
                    "answer_claim_ids": [
                        item
                        for item in statement.answer_claim_ids
                        if item in retained_claim_ids
                    ],
                    "finding_ids": [
                        item
                        for item in statement.finding_ids
                        if item in allowed_finding_ids
                    ],
                    "report_claim_ids": [
                        item
                        for item in statement.report_claim_ids
                        if item in allowed_claim_ids
                    ],
                }
            )
            if not (
                repaired.answer_claim_ids
                or repaired.finding_ids
                or repaired.report_claim_ids
            ):
                return None
            return repaired

        direct = repair_statement(answer.direct_answer)
        if direct is None:
            if not repaired_claims:
                return answer
            direct = AnswerStatement(
                text="The prior answer could not be retained beyond its validated support.",
                kind=AnswerStatementKind.DIRECT_ANSWER,
                answer_claim_ids=[repaired_claims[0].claim_id],
            )
        supporting_points = [
            repaired
            for item in answer.supporting_points
            if (repaired := repair_statement(item)) is not None
        ]
        uncertainty = [
            repaired
            for item in answer.uncertainty
            if (repaired := repair_statement(item)) is not None
        ]
        relevant_finding_ids = [
            finding_id
            for finding_id in answer.relevant_finding_ids
            if finding_id in allowed_finding_ids
        ]
        statement_finding_ids = {
            finding_id
            for statement in [direct, *supporting_points, *uncertainty]
            for finding_id in statement.finding_ids
        }
        relevant_finding_ids = list(
            dict.fromkeys([*relevant_finding_ids, *sorted(statement_finding_ids)])
        )
        return answer.model_copy(
            update={
                "direct_answer": direct,
                "supporting_points": supporting_points,
                "uncertainty": uncertainty,
                "claims": repaired_claims,
                "relevant_finding_ids": relevant_finding_ids,
            }
        )
