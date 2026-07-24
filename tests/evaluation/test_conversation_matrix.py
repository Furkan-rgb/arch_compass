from __future__ import annotations

from hashlib import sha256

import pytest
from pydantic import BaseModel

from archcompass.adapters.models.deterministic import DeterministicReasoningProvider
from archcompass.domain.atlas import (
    AtlasNodeSummary,
    NodeType,
    SourceExcerpt,
    SourceLocation,
)
from archcompass.domain.base import canonical_json
from archcompass.domain.case import (
    CaseAlternative,
    Confidence,
    ConfidenceLevel,
)
from archcompass.domain.consultation import (
    ArchitecturalFinding,
    AtlasEvidenceReference,
    Claim,
    ClaimClassification,
    DesignForce,
    FindingImportance,
    RecommendationDisposition,
    ScenarioEvaluation,
    SupportedStatement,
)
from archcompass.domain.conversation import (
    AnswerStatementKind,
    ConversationAtlasEvidence,
    ConversationEvidenceKind,
    ConversationEvidenceReference,
    ConversationEvidenceScope,
    ConversationMessageView,
    ConversationRole,
    FindingDigest,
    GetSourceExcerptAction,
    PinnedCaseSummary,
    ReportConversationContext,
    ReportQuestionPlan,
    ReportQuestionPlanningContext,
    ReportQuestionType,
    ReportSummary,
)
from archcompass.domain.errors import ConversationValidationError
from archcompass.domain.policy import (
    PolicyChunk,
    PolicyDocument,
    PolicyEvidenceSummary,
    PolicyScope,
    PolicySource,
    PolicyStrength,
    RetrievedPolicy,
)

_FINDING_TITLES = (
    "Responsibility Ownership",
    "Change Locality",
    "Provider Boundary",
    "Evidence Validation",
    "Scenario Isolation",
    "Policy Applicability",
    "Source Traceability",
    "Bounded Retrieval",
    "Summary Continuity",
    "Migration Safety",
    "Implementation Sequencing",
    "Production Evidence Gap",
)


def _supported(text: str) -> SupportedStatement:
    return SupportedStatement(
        text=text,
        classification=ClaimClassification.ADVISOR_INFERENCE,
        supporting_claim_ids=["claim-report"],
    )


def _location(ordinal: int) -> SourceLocation:
    return SourceLocation(
        path=f"src/component_{ordinal:02d}.py",
        start_line=10,
        end_line=20,
    )


def _node(ordinal: int) -> AtlasNodeSummary:
    return AtlasNodeSummary(
        node_id=f"node-{ordinal:02d}",
        qualified_name=f"component_{ordinal:02d}.boundary",
        node_type=NodeType.FUNCTION,
        path=_location(ordinal).path,
        location=_location(ordinal),
        is_public=True,
    )


def _findings() -> list[ArchitecturalFinding]:
    findings: list[ArchitecturalFinding] = []
    for ordinal, title in enumerate(_FINDING_TITLES, start=1):
        importance = (
            FindingImportance.CRITICAL
            if ordinal == 12
            else FindingImportance.HIGH
            if ordinal in {1, 4}
            else FindingImportance.MEDIUM
        )
        findings.append(
            ArchitecturalFinding(
                finding_id=f"FIND-{ordinal:03d}",
                title=title,
                summary=f"Finding {ordinal} keeps architectural evidence explicit.",
                concern_cluster_id=f"cluster-{ordinal:02d}",
                importance=importance,
                importance_rationale=(
                    f"Finding {ordinal} has a distinct consequence in the pinned case."
                ),
                confidence=Confidence(
                    level=ConfidenceLevel.HIGH,
                    rationale=f"Finding {ordinal} is backed by retained report evidence.",
                ),
                consequence=f"Consequence {ordinal} affects the recommended boundary.",
                claim_ids=[f"claim-{ordinal:02d}"],
                atlas_node_ids=[f"node-{ordinal:02d}"],
                policy_ids=(
                    ["policy-boundaries"]
                    if ordinal == 6
                    else []
                ),
                affected_locations=[_node(ordinal)],
                recommended_response=f"Apply response {ordinal} at the owning boundary.",
                uncertainty=[f"Runtime behavior for finding {ordinal} was not measured."],
            )
        )
    return findings


def _claims(findings: list[ArchitecturalFinding]) -> list[Claim]:
    return [
        Claim(
            claim_id=finding.claim_ids[0],
            text=f"Observed exact support for {finding.finding_id}.",
            classification=ClaimClassification.REPOSITORY_OBSERVATION,
            atlas_references=[
                AtlasEvidenceReference(
                    node_id=finding.atlas_node_ids[0],
                    location=finding.affected_locations[0].location,
                )
            ],
            policy_ids=finding.policy_ids,
        )
        for finding in findings
    ]


def _alternatives() -> list[CaseAlternative]:
    return [
        CaseAlternative(
            id="alt-local",
            title="Keep behavior local",
            summary="Retain a direct implementation until credible variation appears.",
        ),
        CaseAlternative(
            id="alt-platform",
            title="Build a generic platform",
            summary="Introduce a broad extension platform before it is required.",
        ),
    ]


def _scenarios() -> list[ScenarioEvaluation]:
    return [
        ScenarioEvaluation(
            scenario="A second provider becomes mandatory",
            assumptions=["The second provider has materially different capabilities."],
            alternative_results={
                "alt-local": "Requires coordinated edits.",
                "alt-platform": "Accommodates the provider but adds early complexity.",
            },
            conclusion="A narrow provider-owned boundary is justified.",
        )
    ]


def _policy() -> RetrievedPolicy:
    return RetrievedPolicy(
        policy=PolicyDocument(
            id="policy-boundaries",
            title="Keep changing knowledge behind its owner",
            scope=PolicyScope.ORGANISATION,
            applies_to="team-blue",
            strength=PolicyStrength.REQUIRED,
            tags=["boundaries", "ownership"],
            source=PolicySource(author="ArchCompass"),
            body="Put changing provider knowledge behind the provider boundary.",
            source_path="policies/policy-boundaries.md",
            content_hash="policy-content-hash",
        ),
        chunks=[
            PolicyChunk(
                chunk_id="policy-boundaries-applicability",
                policy_id="policy-boundaries",
                section="Applicability",
                ordinal=0,
                text="Applies when provider-specific knowledge changes independently.",
                content_hash="policy-applicability-hash",
            ),
            PolicyChunk(
                chunk_id="policy-boundaries-guidance",
                policy_id="policy-boundaries",
                section="Guidance",
                ordinal=1,
                text="Place discovery and validation behind one owning boundary.",
                content_hash="policy-guidance-hash",
            ),
            PolicyChunk(
                chunk_id="policy-boundaries-exceptions",
                policy_id="policy-boundaries",
                section="Exceptions",
                ordinal=2,
                text="Keep a single stable implementation local when no variation is credible.",
                content_hash="policy-exceptions-hash",
            ),
        ],
        distance=0.05,
    )


def _pinned_case() -> PinnedCaseSummary:
    return PinnedCaseSummary(
        case_id="case-matrix",
        revision=3,
        title="Deterministic conversation matrix",
        problem_statement="Provider knowledge is spread across changing modules.",
        desired_outcome="Keep architectural decisions explainable from exact evidence.",
        actors_and_workflows=["A developer reviews a completed recommendation."],
        functional_requirements=["Answer questions about the immutable report."],
        quality_attributes=["Evidence traceability", "Change locality"],
        technical_constraints=["Use the exact pinned repository Atlas."],
        organisational_constraints=["The team owns one repository."],
        derived_constraints=["Conversation answers cannot revise the case."],
        confirmed_facts=["The report contains twelve canonical findings."],
        expected_future_changes=["A second provider may become mandatory."],
        non_goals=["Do not build a generic chat framework."],
        assumptions=["Provider behavior remains statically inspectable."],
    )


def _report_summary() -> ReportSummary:
    return ReportSummary(
        report_id="report-matrix",
        disposition=RecommendationDisposition.MOVE_RESPONSIBILITY,
        decision_summary=_supported(
            "Move provider-specific discovery and validation behind its owning boundary."
        ),
        problem_and_desired_outcome=(
            "Contain provider knowledge while preserving exact evidence traceability."
        ),
        important_design_forces=[
            DesignForce(
                force_id="force-ownership",
                title="Responsibility ownership",
                description="Changing knowledge should have one owner.",
                importance="high",
            )
        ],
        recommended_architecture=_supported(
            "Use an application-owned evidence dossier and a narrow provider boundary."
        ),
        alternatives=_alternatives(),
        scenarios=_scenarios(),
        implementation_sequence=[
            _supported("First define the application-owned evidence contract."),
            _supported("Then move provider serialization behind the adapter."),
        ],
        confidence=Confidence(
            level=ConfidenceLevel.HIGH,
            rationale="The report retains exact structural and policy evidence.",
        ),
        reversal_conditions=[
            _supported("Reverse course if provider behavior never varies.")
        ],
        revisit_triggers=[
            _supported("Revisit when a second concrete provider is required.")
        ],
        policies=[
            PolicyEvidenceSummary(
                id="policy-boundaries",
                title="Keep changing knowledge behind its owner",
                scope=PolicyScope.ORGANISATION,
                applies_to="team-blue",
                strength=PolicyStrength.REQUIRED,
                matched_sections=["Applicability", "Guidance", "Exceptions"],
            )
        ],
    )


def _planning_context(
    question: str,
    *,
    findings: list[ArchitecturalFinding] | None = None,
    recent_messages: list[ConversationMessageView] | None = None,
) -> ReportQuestionPlanningContext:
    selected = findings or _findings()
    return ReportQuestionPlanningContext(
        question=question,
        pinned_case=_pinned_case(),
        report_summary=_report_summary(),
        finding_digests=[FindingDigest.from_finding(item) for item in selected],
        recent_messages=recent_messages or [],
        prior_evidence_references=[],
    )


def _artifact_id(value: BaseModel) -> str:
    return sha256(canonical_json(value).encode("utf-8")).hexdigest()


def _reference(
    kind: ConversationEvidenceKind,
    artifact_id: str,
    value: BaseModel,
    *,
    node_id: str | None = None,
    location: SourceLocation | None = None,
) -> ConversationEvidenceReference:
    return ConversationEvidenceReference(
        evidence_id=f"{kind.value}:{artifact_id}",
        kind=kind,
        artifact_id=artifact_id,
        scope=ConversationEvidenceScope.ORIGINAL_RUN,
        content_hash=sha256(canonical_json(value).encode("utf-8")).hexdigest(),
        node_id=node_id,
        location=location,
    )


def _answer_context(
    question: str,
    question_types: list[ReportQuestionType],
    *,
    finding_ids: list[str] | None = None,
) -> ReportConversationContext:
    all_findings = _findings()
    all_claims = _claims(all_findings)
    selected_ids = finding_ids or []
    retrieve_findings = (
        all_findings
        if ReportQuestionType.LIST_FINDINGS in question_types
        else [
            item
            for item in all_findings
            if item.finding_id in selected_ids
        ]
    )
    retrieve_claim_ids = {
        claim_id
        for finding in retrieve_findings
        for claim_id in finding.claim_ids
    }
    retrieve_claims = [
        item for item in all_claims if item.claim_id in retrieve_claim_ids
    ]
    retrieved_policies = (
        [_policy()]
        if ReportQuestionType.POLICY_EXPLANATION in question_types
        else []
    )
    retrieved_alternatives = (
        _alternatives()
        if ReportQuestionType.ALTERNATIVE_EXPLANATION in question_types
        else []
    )
    retrieved_scenarios = (
        _scenarios()
        if ReportQuestionType.SCENARIO_EXPLANATION in question_types
        else []
    )

    report_summary = _report_summary()
    pinned_case = _pinned_case()
    references = [
        _reference(
            ConversationEvidenceKind.REPORT_CONTEXT,
            report_summary.report_id,
            report_summary,
        ),
        _reference(
            ConversationEvidenceKind.REPORT_CONTEXT,
            f"{pinned_case.case_id}@{pinned_case.revision}",
            pinned_case,
        ),
    ]
    references.extend(
        _reference(
            ConversationEvidenceKind.FINDING,
            finding.finding_id,
            finding,
        )
        for finding in retrieve_findings
    )
    references.extend(
        _reference(
            ConversationEvidenceKind.REPORT_CLAIM,
            claim.claim_id,
            claim,
        )
        for claim in retrieve_claims
    )
    references.extend(
        _reference(
            ConversationEvidenceKind.POLICY,
            policy.policy.id,
            policy,
        )
        for policy in retrieved_policies
    )
    references.extend(
        _reference(
            ConversationEvidenceKind.ALTERNATIVE,
            alternative.id,
            alternative,
        )
        for alternative in retrieved_alternatives
    )
    references.extend(
        _reference(
            ConversationEvidenceKind.SCENARIO,
            _artifact_id(scenario),
            scenario,
        )
        for scenario in retrieved_scenarios
    )

    atlas_evidence: list[ConversationAtlasEvidence] = []
    if {
        ReportQuestionType.EVIDENCE_TRACE,
        ReportQuestionType.SOURCE_EXPLANATION,
    } & set(question_types):
        selected = next(
            (
                item
                for item in all_findings
                if item.finding_id in selected_ids
            ),
            all_findings[2],
        )
        node = selected.affected_locations[0]
        location = node.location
        assert location is not None
        excerpt = SourceExcerpt(
            node_id=node.node_id,
            location=location,
            text="def provider_boundary():\n    return validated_evidence\n",
        )
        node_reference = _reference(
            ConversationEvidenceKind.ATLAS_NODE,
            node.node_id,
            node,
            node_id=node.node_id,
            location=location,
        )
        excerpt_reference = _reference(
            ConversationEvidenceKind.SOURCE_EXCERPT,
            _artifact_id(excerpt),
            excerpt,
            node_id=node.node_id,
            location=location,
        )
        references.extend([node_reference, excerpt_reference])
        atlas_evidence.append(
            ConversationAtlasEvidence(
                action=GetSourceExcerptAction(
                    kind="get_source_excerpt",
                    node_id=node.node_id,
                    max_lines=60,
                ),
                evidence_references=[node_reference, excerpt_reference],
                query_summary=(
                    "The ordered dependency trace reaches the provider boundary and its test."
                ),
                ordered_node_ids=[node.node_id],
                nodes=[node],
                excerpts=[excerpt],
                test_ids=[],
            )
        )

    unique_references = {
        item.evidence_id: item
        for item in references
    }
    plan = ReportQuestionPlan(
        question_types=question_types,
        finding_ids=selected_ids,
        retrieval_actions=[],
        rationale="Exercise one deterministic answer category.",
    )
    return ReportConversationContext(
        conversation_id="conversation-matrix",
        run_id="run-matrix",
        case_id=pinned_case.case_id,
        case_revision=pinned_case.revision,
        atlas_version_id="atlas-matrix",
        policy_index_version_id="pidx-matrix",
        question=question,
        question_plan=plan,
        pinned_case=pinned_case,
        report_summary=report_summary,
        finding_digests=[
            FindingDigest.from_finding(item)
            for item in all_findings
        ],
        recent_messages=[],
        evidence_references=list(unique_references.values()),
        retrieved_findings=retrieve_findings,
        retrieved_claims=retrieve_claims,
        retrieved_concern_analyses=[],
        retrieved_atlas_evidence=atlas_evidence,
        retrieved_policies=retrieved_policies,
        retrieved_alternatives=retrieved_alternatives,
        retrieved_scenarios=retrieved_scenarios,
    )


@pytest.mark.evaluation
@pytest.mark.parametrize(
    ("question", "expected_type"),
    [
        ("Give me an explicit report summary.", ReportQuestionType.REPORT_SUMMARY),
        ("What are the main findings?", ReportQuestionType.LIST_FINDINGS),
        ("Explain FIND-004.", ReportQuestionType.FINDING_DETAILS),
        ("Which finding has the highest priority?", ReportQuestionType.FINDING_PRIORITY),
        (
            "Compare FIND-002 and FIND-009.",
            ReportQuestionType.COMPARE_FINDINGS,
        ),
        (
            "Trace the evidence supporting FIND-003.",
            ReportQuestionType.EVIDENCE_TRACE,
        ),
        (
            "Show the exact source for FIND-007.",
            ReportQuestionType.SOURCE_EXPLANATION,
        ),
        (
            "Which policies apply and what exceptions do they have?",
            ReportQuestionType.POLICY_EXPLANATION,
        ),
        (
            "Which alternative was rejected?",
            ReportQuestionType.ALTERNATIVE_EXPLANATION,
        ),
        (
            "How did the mandatory-provider scenario behave?",
            ReportQuestionType.SCENARIO_EXPLANATION,
        ),
        (
            "Which assumptions could weaken the recommendation?",
            ReportQuestionType.ASSUMPTION_REVIEW,
        ),
        (
            "What is the implementation order?",
            ReportQuestionType.IMPLEMENTATION_ORDER,
        ),
        (
            "What if a second provider becomes mandatory?",
            ReportQuestionType.COUNTERFACTUAL,
        ),
        (
            "What if provider variation is removed?",
            ReportQuestionType.COUNTERFACTUAL,
        ),
    ],
)
def test_deterministic_question_category_matrix(
    question: str,
    expected_type: ReportQuestionType,
) -> None:
    plan = DeterministicReasoningProvider().classify_report_question(
        _planning_context(question)
    )

    assert expected_type in plan.question_types


@pytest.mark.evaluation
@pytest.mark.parametrize(
    ("question", "question_types", "finding_ids", "expected_text"),
    [
        (
            "Give me an explicit report summary.",
            [ReportQuestionType.REPORT_SUMMARY],
            [],
            ("pinned report recommends",),
        ),
        (
            "What are the main findings?",
            [ReportQuestionType.LIST_FINDINGS],
            [],
            ("canonical findings", "FIND-001", "FIND-012"),
        ),
        (
            "Explain FIND-004.",
            [ReportQuestionType.FINDING_DETAILS],
            ["FIND-004"],
            ("finding detail", "FIND-004", "Recommended response"),
        ),
        (
            "Which finding has the highest priority?",
            [ReportQuestionType.FINDING_PRIORITY],
            [],
            ("FIND-012", "highest contextual priority"),
        ),
        (
            "Compare FIND-002 and FIND-009.",
            [ReportQuestionType.COMPARE_FINDINGS],
            ["FIND-002", "FIND-009"],
            ("Comparison", "FIND-002", "FIND-009"),
        ),
        (
            "Trace the evidence supporting FIND-003.",
            [ReportQuestionType.EVIDENCE_TRACE],
            ["FIND-003"],
            ("supported by", "claim-03", "node-03", "ordered dependency trace"),
        ),
        (
            "Show the exact source for FIND-007.",
            [ReportQuestionType.SOURCE_EXPLANATION],
            ["FIND-007"],
            ("bounded source evidence", "node-07", "src/component_07.py:10-20"),
        ),
        (
            "Which policies apply and what exceptions do they have?",
            [ReportQuestionType.POLICY_EXPLANATION],
            [],
            (
                "policy-boundaries",
                "applies_to=team-blue",
                "Applicability",
                "Exceptions",
            ),
        ),
        (
            "Which alternative was rejected?",
            [ReportQuestionType.ALTERNATIVE_EXPLANATION],
            [],
            ("recorded alternatives", "alt-local", "alt-platform"),
        ),
        (
            "How did the mandatory-provider scenario behave?",
            [ReportQuestionType.SCENARIO_EXPLANATION],
            [],
            ("recorded scenario analysis", "second provider", "narrow provider-owned boundary"),
        ),
        (
            "Which assumptions could weaken the recommendation?",
            [ReportQuestionType.ASSUMPTION_REVIEW],
            [],
            ("pinned case assumptions", "statically inspectable"),
        ),
        (
            "What is the implementation order?",
            [ReportQuestionType.IMPLEMENTATION_ORDER],
            [],
            ("recorded implementation order", "First define", "Then move"),
        ),
        (
            "What if a second provider becomes mandatory?",
            [ReportQuestionType.COUNTERFACTUAL],
            [],
            ("historical decision", "strengthens or redirects", "new consultation"),
        ),
        (
            "What if provider variation is removed?",
            [ReportQuestionType.COUNTERFACTUAL],
            [],
            ("historical decision", "weakens", "new consultation"),
        ),
        (
            "What is the current production runtime latency?",
            [ReportQuestionType.GENERAL_REPORT_QUESTION],
            [],
            ("no runtime production evidence",),
        ),
    ],
)
def test_deterministic_typed_answer_matrix(
    question: str,
    question_types: list[ReportQuestionType],
    finding_ids: list[str],
    expected_text: tuple[str, ...],
) -> None:
    context = _answer_context(
        question,
        question_types,
        finding_ids=finding_ids,
    )

    answer = DeterministicReasoningProvider().answer_report_question(context)

    assert answer.direct_answer.kind is AnswerStatementKind.DIRECT_ANSWER
    assert all(
        statement.answer_claim_ids
        or statement.finding_ids
        or statement.report_claim_ids
        for statement in [
            answer.direct_answer,
            *answer.supporting_points,
            *answer.uncertainty,
        ]
    )
    folded = answer.direct_answer.text.casefold()
    assert all(item.casefold() in folded for item in expected_text)
    if question_types == [ReportQuestionType.FINDING_PRIORITY]:
        assert len(context.finding_digests) == 12
        assert answer.relevant_finding_ids == ["FIND-012"]
    if question_types == [ReportQuestionType.LIST_FINDINGS]:
        assert answer.relevant_finding_ids == [
            f"FIND-{ordinal:03d}" for ordinal in range(1, 13)
        ]
    if question_types == [ReportQuestionType.POLICY_EXPLANATION]:
        assert any(
            claim.policy_ids == ["policy-boundaries"]
            for claim in answer.claims
        )
    if question_types == [ReportQuestionType.COUNTERFACTUAL]:
        assert answer.uncertainty
        assert "counterfactual" in answer.uncertainty[0].text.casefold()


@pytest.mark.evaluation
@pytest.mark.parametrize(
    ("question", "expected_ids"),
    [
        ("Explain FIND-004.", ["FIND-004"]),
        ("Explain Evidence Validation.", ["FIND-004"]),
        ("Explain finding 9.", ["FIND-009"]),
        ("Explain the eleventh finding.", ["FIND-011"]),
        (
            "Compare Responsibility Ownership and Change Locality.",
            ["FIND-001", "FIND-002"],
        ),
    ],
)
def test_finding_reference_resolution_matrix(
    question: str,
    expected_ids: list[str],
) -> None:
    plan = DeterministicReasoningProvider().classify_report_question(
        _planning_context(question)
    )

    assert plan.finding_ids == expected_ids


@pytest.mark.evaluation
def test_unambiguous_recent_finding_reference_is_resolved() -> None:
    recent = ConversationMessageView(
        ordinal=2,
        role=ConversationRole.ASSISTANT,
        text="FIND-006 explains the policy applicability concern.",
        relevant_finding_ids=["FIND-006"],
    )

    plan = DeterministicReasoningProvider().classify_report_question(
        _planning_context(
            "Explain that finding.",
            recent_messages=[recent],
        )
    )

    assert plan.finding_ids == ["FIND-006"]


@pytest.mark.evaluation
def test_duplicate_exact_title_is_ambiguous_outside_comparison() -> None:
    findings = _findings()
    findings[0] = findings[0].model_copy(update={"title": "Shared Boundary"})
    findings[1] = findings[1].model_copy(update={"title": "Shared Boundary"})

    with pytest.raises(
        ConversationValidationError,
        match="multiple finding titles",
    ):
        DeterministicReasoningProvider().classify_report_question(
            _planning_context("Explain Shared Boundary.", findings=findings)
        )


@pytest.mark.evaluation
def test_duplicate_exact_title_can_select_both_for_comparison() -> None:
    findings = _findings()
    findings[0] = findings[0].model_copy(update={"title": "Shared Boundary"})
    findings[1] = findings[1].model_copy(update={"title": "Shared Boundary"})

    plan = DeterministicReasoningProvider().classify_report_question(
        _planning_context("Compare Shared Boundary.", findings=findings)
    )

    assert plan.finding_ids == ["FIND-001", "FIND-002"]


@pytest.mark.evaluation
def test_comparison_without_explicit_references_is_rejected() -> None:
    with pytest.raises(
        ConversationValidationError,
        match=r"comparison.*finding",
    ):
        DeterministicReasoningProvider().classify_report_question(
            _planning_context("Compare the findings.")
        )


@pytest.mark.evaluation
@pytest.mark.parametrize(
    ("question", "requested_type", "expected_text"),
    [
        (
            "What exact evidence supports finding FIND-003?",
            ReportQuestionType.EVIDENCE_TRACE,
            ("selected findings are supported by", "claim-03", "node-03"),
        ),
        (
            "Which source lines support finding FIND-007?",
            ReportQuestionType.SOURCE_EXPLANATION,
            ("bounded source evidence", "src/component_07.py:10-20"),
        ),
        (
            "Which policy exceptions apply to finding FIND-006?",
            ReportQuestionType.POLICY_EXPLANATION,
            ("pinned policies", "policy-boundaries", "Exceptions"),
        ),
    ],
)
def test_mixed_finding_questions_render_the_requested_evidence_category(
    question: str,
    requested_type: ReportQuestionType,
    expected_text: tuple[str, ...],
) -> None:
    reasoner = DeterministicReasoningProvider()
    plan = reasoner.classify_report_question(_planning_context(question))

    assert ReportQuestionType.FINDING_DETAILS in plan.question_types
    assert requested_type in plan.question_types
    answer = reasoner.answer_report_question(
        _answer_context(
            question,
            plan.question_types,
            finding_ids=plan.finding_ids,
        )
    )

    rendered = answer.direct_answer.text.casefold()
    assert all(item.casefold() in rendered for item in expected_text)
    assert "finding detail:" not in rendered


@pytest.mark.evaluation
@pytest.mark.parametrize(
    "question",
    [
        "Who is the current on-call engineer?",
        "What was the production p95 latency yesterday?",
        "Which deployment is serving traffic right now?",
    ],
)
def test_explicit_unsupported_questions_are_general_and_bounded(
    question: str,
) -> None:
    reasoner = DeterministicReasoningProvider()
    plan = reasoner.classify_report_question(_planning_context(question))

    assert plan.question_types == [ReportQuestionType.GENERAL_REPORT_QUESTION]
    answer = reasoner.answer_report_question(
        _answer_context(question, plan.question_types)
    )

    rendered = answer.direct_answer.text.casefold()
    assert any(
        scope in rendered
        for scope in ("pinned report", "bounded consultation evidence")
    )
    assert any(
        marker in rendered
        for marker in (
            "contain no",
            "does not contain",
            "does not support",
            "unavailable",
            "cannot answer",
        )
    )
    assert answer.uncertainty
    assert "pinned report recommends:" not in rendered


@pytest.mark.evaluation
@pytest.mark.parametrize(
    "question",
    [
        "Summarize the report.",
        "What decision did the report make?",
        "Give me the recommendation.",
        "Provide an overview of the completed consultation.",
    ],
)
def test_explicit_summary_and_decision_questions_remain_report_summaries(
    question: str,
) -> None:
    reasoner = DeterministicReasoningProvider()
    plan = reasoner.classify_report_question(_planning_context(question))

    assert plan.question_types == [ReportQuestionType.REPORT_SUMMARY]
    answer = reasoner.answer_report_question(
        _answer_context(question, plan.question_types)
    )

    assert "pinned report recommends:" in answer.direct_answer.text.casefold()
