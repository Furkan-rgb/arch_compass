from __future__ import annotations

from collections.abc import Callable
from itertools import pairwise
from types import SimpleNamespace
from typing import cast

import pytest

from archcompass.application.conversation_retrieval import (
    ConversationEvidenceRetriever,
)
from archcompass.configuration import ConversationConfig
from archcompass.domain.atlas import (
    Atlas,
    AtlasEdge,
    AtlasMetricValue,
    AtlasNode,
    AtlasNodeEvidence,
    AtlasNodeSummary,
    AtlasQuery,
    AtlasQueryResult,
    EdgeType,
    NodeType,
    ObscuritySignal,
    SearchNodesQuery,
    ShortestPathQuery,
    SourceExcerpt,
    SourceExcerptQuery,
    SourceLocation,
)
from archcompass.domain.case import Confidence, ConfidenceLevel
from archcompass.domain.consultation import (
    ArchitecturalFinding,
    AtlasEvidenceReference,
    Claim,
    ClaimClassification,
    ConsultationRun,
    FindingImportance,
)
from archcompass.domain.conversation import (
    ConversationEvidenceScope,
    GetAtlasNodesAction,
    GetDependencyPathAction,
    GetFindingAction,
    GetPoliciesAction,
    GetReportClaimsAction,
    GetSourceExcerptAction,
    ReportQuestionPlan,
    ReportQuestionType,
    SearchAtlasNodesAction,
)
from archcompass.domain.errors import ConversationRetrievalError
from archcompass.domain.policy import (
    PolicyChunk,
    PolicyDocument,
    PolicyScope,
    PolicySource,
    PolicyStrength,
    RetrievedPolicy,
)
from archcompass.ports.atlas import AtlasQueryService
from archcompass.ports.repositories import AtlasRepository


class _AtlasStore:
    def __init__(self, nodes: list[AtlasNode] | None = None) -> None:
        self._nodes = nodes or []

    def get(self, version_id: str) -> Atlas:
        del version_id
        return cast(Atlas, SimpleNamespace(nodes=self._nodes))


class _QueryService:
    def __init__(self, handler: Callable[[AtlasQuery], AtlasQueryResult]) -> None:
        self._handler = handler
        self.queries: list[AtlasQuery] = []

    def execute(self, atlas: Atlas, query: AtlasQuery) -> AtlasQueryResult:
        del atlas
        self.queries.append(query)
        return self._handler(query)


def _report(findings: list[ArchitecturalFinding] | None = None) -> SimpleNamespace:
    return SimpleNamespace(
        findings=findings or [],
        confirmed_context=[],
        assumptions_and_unresolved_questions=[],
        repository_observations=[],
        relevant_policies=[],
        evidence_appendix=[],
    )


def _packet(*, policies: list[RetrievedPolicy] | None = None) -> SimpleNamespace:
    return SimpleNamespace(
        surfaced_node_ids=set(),
        policies=policies or [],
        node_evidence=[],
        test_evidence=[],
        relationships=[],
        relationship_evidence=[],
        metrics=[],
        excerpts=[],
        test_ids=[],
    )


def _run(
    *,
    findings: list[ArchitecturalFinding] | None = None,
    policies: list[RetrievedPolicy] | None = None,
    packets: list[SimpleNamespace] | None = None,
) -> ConsultationRun:
    return cast(
        ConsultationRun,
        SimpleNamespace(
            report=_report(findings),
            focused_packets=(
                packets
                if packets is not None
                else ([_packet(policies=policies)] if policies else [])
            ),
            concern_analyses=[],
            alternatives=[],
            scenarios=[],
            atlas_version_id="atlas-v1",
        ),
    )


def _retriever(
    queries: _QueryService,
    *,
    config: ConversationConfig | None = None,
    atlas_nodes: list[AtlasNode] | None = None,
) -> ConversationEvidenceRetriever:
    return ConversationEvidenceRetriever(
        atlases=cast(AtlasRepository, _AtlasStore(atlas_nodes)),
        queries=cast(AtlasQueryService, queries),
        config=config or ConversationConfig(),
    )


def _summary(node_id: str, *, qualified_name: str | None = None) -> AtlasNodeSummary:
    return AtlasNodeSummary(
        node_id=node_id,
        qualified_name=qualified_name or node_id,
        node_type=NodeType.MODULE,
        path=f"{node_id}.py",
    )


def _atlas_node(node_id: str) -> AtlasNode:
    return AtlasNode(
        atlas_id=node_id,
        path=f"{node_id}.py",
        symbol_name=node_id,
        qualified_name=node_id,
        node_type=NodeType.MODULE,
        start_line=1,
        end_line=10,
        parser_version="test",
    )


def _plan(*actions: object) -> ReportQuestionPlan:
    return ReportQuestionPlan(
        question_types=[ReportQuestionType.EVIDENCE_TRACE],
        retrieval_actions=list(actions),
        rationale="Exercise cumulative retrieval budgets.",
    )


def _finding(
    ordinal: int,
    *,
    node_ids: list[str] | None = None,
) -> ArchitecturalFinding:
    return ArchitecturalFinding(
        finding_id=f"FIND-{ordinal:03d}",
        title=f"Finding {ordinal}",
        summary="A bounded finding.",
        importance=FindingImportance.MEDIUM,
        importance_rationale="It affects the decision.",
        confidence=Confidence(
            level=ConfidenceLevel.HIGH,
            rationale="The retained report supports it.",
        ),
        consequence="The architecture should account for it.",
        claim_ids=[f"claim-{ordinal}"],
        atlas_node_ids=node_ids or [],
        recommended_response="Keep the responsibility bounded.",
    )


def _policy(ordinal: int) -> RetrievedPolicy:
    policy_id = f"policy-{ordinal}"
    return RetrievedPolicy(
        policy=PolicyDocument(
            id=policy_id,
            title=f"Policy {ordinal}",
            scope=PolicyScope.GENERAL,
            strength=PolicyStrength.GUIDANCE,
            tags=["test"],
            source=PolicySource(author="ArchCompass"),
            body="Keep the evidence bounded.",
            source_path=f"{policy_id}.md",
            content_hash=f"hash-{ordinal}",
        ),
        chunks=[
            PolicyChunk(
                chunk_id=f"chunk-{ordinal}",
                policy_id=policy_id,
                section="Guidance",
                ordinal=0,
                text="Keep the evidence bounded.",
                content_hash=f"chunk-hash-{ordinal}",
            )
        ],
        distance=float(ordinal),
    )


def test_search_limits_are_clamped_to_the_remaining_turn_node_capacity() -> None:
    search_number = 0

    def handle(query: AtlasQuery) -> AtlasQueryResult:
        nonlocal search_number
        assert isinstance(query, SearchNodesQuery)
        search_number += 1
        node_ids = [
            f"search-{search_number}-{ordinal}" for ordinal in range(query.limit)
        ]
        return AtlasQueryResult(
            query=query,
            node_ids=node_ids,
            summary=f"search {search_number}",
            node_summaries=[_summary(node_id) for node_id in node_ids],
        )

    queries = _QueryService(handle)
    results = _retriever(queries).execute(
        run=_run(),
        plan=_plan(
            SearchAtlasNodesAction(kind="search_atlas_nodes", terms=["first"], limit=20),
            SearchAtlasNodesAction(kind="search_atlas_nodes", terms=["second"], limit=20),
        ),
    )

    executed_limits = [
        query.limit for query in queries.queries if isinstance(query, SearchNodesQuery)
    ]
    supplied_nodes = {
        node_id
        for result in results
        for atlas_result in result.atlas_results
        for node_id in atlas_result.node_ids
    }
    assert executed_limits == [20, 4]
    assert len(supplied_nodes) == 24
    assert results[1].truncated
    assert any("clamped the search" in reason for reason in results[1].truncation_reasons)


def test_excerpt_queries_are_clamped_before_reading_to_180_total_lines() -> None:
    def handle(query: AtlasQuery) -> AtlasQueryResult:
        assert isinstance(query, SourceExcerptQuery)
        excerpt = SourceExcerpt(
            node_id=query.node_id,
            location=SourceLocation(
                path=f"{query.node_id}.py",
                start_line=1,
                end_line=query.max_lines,
            ),
            text="".join(f"line {line}\n" for line in range(1, query.max_lines + 1)),
        )
        return AtlasQueryResult(
            query=query,
            node_ids=[query.node_id],
            summary=f"Source excerpt for {query.node_id}",
            node_summaries=[_summary(query.node_id)],
            excerpts=[excerpt],
        )

    queries = _QueryService(handle)
    results = _retriever(queries).execute(
        run=_run(),
        plan=_plan(
            GetSourceExcerptAction(
                kind="get_source_excerpt",
                node_id="node-one",
                max_lines=120,
            ),
            GetSourceExcerptAction(
                kind="get_source_excerpt",
                node_id="node-two",
                max_lines=120,
            ),
        ),
        previous_node_ids={"node-one", "node-two"},
    )

    executed_limits = [
        query.max_lines
        for query in queries.queries
        if isinstance(query, SourceExcerptQuery)
    ]
    line_counts = [
        excerpt.location.end_line - excerpt.location.start_line + 1
        for result in results
        for atlas_result in result.atlas_results
        for excerpt in atlas_result.excerpts
    ]
    assert executed_limits == [120, 60]
    assert line_counts == [120, 60]
    assert sum(line_counts) == 180
    assert results[1].truncated


def test_dependency_path_projection_preserves_order_edges_tests_and_summary() -> None:
    path = [f"node-{ordinal}" for ordinal in range(5)]
    test_id = "test-node"

    def handle(query: AtlasQuery) -> AtlasQueryResult:
        assert isinstance(query, ShortestPathQuery)
        return AtlasQueryResult(
            query=query,
            node_ids=path,
            summary="Path length 4",
            node_summaries=[_summary(node_id) for node_id in path],
            relationships=[
                AtlasEdge(
                    edge_id=f"edge-{ordinal}",
                    source_id=source,
                    target_id=target,
                    edge_type=EdgeType.IMPORTS,
                    confidence=1.0,
                )
                for ordinal, (source, target) in enumerate(
                    pairwise(path),
                    start=1,
                )
            ],
            test_ids=[test_id],
        )

    results = _retriever(_QueryService(handle)).execute(
        run=_run(),
        plan=_plan(
            GetDependencyPathAction(
                kind="get_dependency_path",
                source_node_id=path[0],
                target_node_id=path[-1],
            )
        ),
        previous_node_ids={path[0], path[-1]},
    )

    atlas_result = results[0].atlas_results[0]
    assert atlas_result.node_ids == path
    assert [
        (edge.source_id, edge.target_id) for edge in atlas_result.relationships
    ] == list(pairwise(path))
    assert atlas_result.test_ids == [test_id]
    assert atlas_result.summary == "Path length 4"


def test_dependency_path_is_prefix_truncated_to_remaining_node_capacity() -> None:
    path = [f"path-node-{ordinal}" for ordinal in range(30)]

    def handle(query: AtlasQuery) -> AtlasQueryResult:
        assert isinstance(query, ShortestPathQuery)
        return AtlasQueryResult(
            query=query,
            node_ids=path,
            summary="Path length 29",
            node_summaries=[_summary(node_id) for node_id in path],
            relationships=[
                AtlasEdge(
                    edge_id=f"path-edge-{ordinal}",
                    source_id=source,
                    target_id=target,
                    edge_type=EdgeType.IMPORTS,
                    confidence=1.0,
                )
                for ordinal, (source, target) in enumerate(pairwise(path), start=1)
            ],
        )

    results = _retriever(_QueryService(handle)).execute(
        run=_run(),
        plan=_plan(
            GetDependencyPathAction(
                kind="get_dependency_path",
                source_node_id=path[0],
                target_node_id=path[-1],
            )
        ),
        previous_node_ids={path[0], path[-1]},
    )

    atlas_result = results[0].atlas_results[0]
    assert atlas_result.node_ids == path[:24]
    assert [
        (edge.source_id, edge.target_id) for edge in atlas_result.relationships
    ] == list(pairwise(path[:24]))
    assert results[0].truncated


def test_serialized_results_are_projected_under_the_cumulative_character_ceiling() -> None:
    query_number = 0

    def handle(query: AtlasQuery) -> AtlasQueryResult:
        nonlocal query_number
        assert isinstance(query, SearchNodesQuery)
        query_number += 1
        return AtlasQueryResult(
            query=query,
            node_ids=[f"large-node-{query_number}"],
            summary="large " * 1200,
            node_summaries=[
                _summary(
                    f"large-node-{query_number}",
                    qualified_name="qualified." + ("x" * 1000),
                )
            ],
        )

    config = ConversationConfig(max_retrieved_text_characters=1000)
    results = _retriever(_QueryService(handle), config=config).execute(
        run=_run(),
        plan=_plan(
            SearchAtlasNodesAction(kind="search_atlas_nodes", terms=["large"], limit=1),
            SearchAtlasNodesAction(kind="search_atlas_nodes", terms=["larger"], limit=1),
        ),
    )

    assert sum(len(result.model_dump_json()) for result in results) <= 1000
    assert all(result.truncated for result in results)
    assert any(
        "Serialized retrieval budget" in reason
        for result in results
        for reason in result.truncation_reasons
    )


def test_finding_and_policy_limits_are_cumulative_across_actions() -> None:
    findings = [_finding(ordinal) for ordinal in range(1, 4)]
    finding_queries = _QueryService(
        lambda query: AtlasQueryResult(query=query, summary="unused")
    )
    finding_results = _retriever(
        finding_queries,
        config=ConversationConfig(max_findings=2),
    ).execute(
        run=_run(findings=findings),
        plan=_plan(
            *[
                GetFindingAction(kind="get_finding", finding_id=finding.finding_id)
                for finding in findings
            ]
        ),
    )
    assert [
        finding.finding_id
        for result in finding_results
        for finding in result.findings
    ] == ["FIND-001", "FIND-002"]
    assert finding_results[2].truncated

    policies = [_policy(ordinal) for ordinal in range(1, 4)]
    policy_queries = _QueryService(
        lambda query: AtlasQueryResult(query=query, summary="unused")
    )
    policy_results = _retriever(
        policy_queries,
        config=ConversationConfig(max_policies=2),
    ).execute(
        run=_run(policies=policies),
        plan=_plan(
            *[
                GetPoliciesAction(kind="get_policies", policy_ids=[item.policy.id])
                for item in policies
            ]
        ),
    )
    assert [
        item.policy.id for result in policy_results for item in result.policies
    ] == ["policy-1", "policy-2"]
    assert policy_results[2].truncated
    assert all(
        reference.scope is ConversationEvidenceScope.ORIGINAL_RUN
        for result in policy_results[:2]
        for reference in result.evidence_references
    )


def test_nodes_embedded_in_detailed_findings_share_the_atlas_node_budget() -> None:
    findings = [
        _finding(
            ordinal,
            node_ids=[f"finding-{ordinal}-node-{node}" for node in range(10)],
        )
        for ordinal in range(1, 4)
    ]
    queries = _QueryService(
        lambda query: AtlasQueryResult(query=query, summary="unused")
    )
    results = _retriever(queries).execute(
        run=_run(findings=findings),
        plan=_plan(
            *[
                GetFindingAction(kind="get_finding", finding_id=finding.finding_id)
                for finding in findings
            ]
        ),
    )

    supplied_findings = [
        finding for result in results for finding in result.findings
    ]
    supplied_node_ids = {
        node_id for finding in supplied_findings for node_id in finding.atlas_node_ids
    }
    assert [finding.finding_id for finding in supplied_findings] == [
        "FIND-001",
        "FIND-002",
    ]
    assert len(supplied_node_ids) == 20
    assert results[2].truncated


def test_exact_artifacts_on_one_old_node_receive_independent_evidence_scopes() -> None:
    original_node = _summary("original-node")
    new_neighbour = _atlas_node("new-neighbour")
    packet = _packet()
    packet.node_evidence = [AtlasNodeEvidence(node=original_node)]
    new_relationship = AtlasEdge(
        edge_id="new-edge",
        source_id=original_node.node_id,
        target_id="new-neighbour",
        edge_type=EdgeType.IMPORTS,
        confidence=1.0,
    )
    new_metric = AtlasMetricValue(
        node_id=original_node.node_id,
        metric="local.physical_lines",
        value=42,
    )

    def handle(query: AtlasQuery) -> AtlasQueryResult:
        return AtlasQueryResult(
            query=query,
            node_ids=[original_node.node_id],
            summary="One old node with newly queried details.",
            node_summaries=[original_node],
            relationships=[new_relationship],
            metric_values=[new_metric],
        )

    results = _retriever(
        _QueryService(handle),
        atlas_nodes=[new_neighbour],
    ).execute(
        run=_run(packets=[packet]),
        plan=_plan(
            GetAtlasNodesAction(
                kind="get_atlas_nodes",
                node_ids=[original_node.node_id],
            )
        ),
    )

    node_scopes = {
        reference.node_id: reference.scope
        for reference in results[0].evidence_references
        if reference.kind.value == "atlas_node"
    }
    artifact_scopes = {
        reference.kind.value: reference.scope
        for reference in results[0].evidence_references
        if reference.kind.value != "atlas_node"
    }
    assert {
        summary.node_id
        for summary in results[0].atlas_results[0].node_summaries
    } == {"original-node", "new-neighbour"}
    assert node_scopes["original-node"] is ConversationEvidenceScope.ORIGINAL_RUN
    assert node_scopes["new-neighbour"] is ConversationEvidenceScope.ADDITIONAL_CONVERSATION
    assert (
        artifact_scopes["atlas_relationship"]
        is ConversationEvidenceScope.ADDITIONAL_CONVERSATION
    )
    assert (
        artifact_scopes["atlas_metric"]
        is ConversationEvidenceScope.ADDITIONAL_CONVERSATION
    )


def test_payload_artifacts_are_projected_with_the_96_reference_turn_ceiling() -> None:
    nodes = ["reference-node-one", "reference-node-two"]

    def handle(query: AtlasQuery) -> AtlasQueryResult:
        return AtlasQueryResult(
            query=query,
            node_ids=nodes,
            summary="Many separately identifiable relationships.",
            node_summaries=[_summary(node_id) for node_id in nodes],
            relationships=[
                AtlasEdge(
                    edge_id=f"reference-edge-{ordinal}",
                    source_id=nodes[0],
                    target_id=nodes[1],
                    edge_type=EdgeType.IMPORTS,
                    confidence=1.0,
                )
                for ordinal in range(100)
            ],
        )

    results = _retriever(_QueryService(handle)).execute(
        run=_run(),
        plan=_plan(
            SearchAtlasNodesAction(
                kind="search_atlas_nodes",
                terms=["reference"],
                limit=2,
            )
        ),
    )

    atlas_result = results[0].atlas_results[0]
    relationship_references = [
        reference
        for reference in results[0].evidence_references
        if reference.kind.value == "atlas_relationship"
    ]
    assert len(results[0].evidence_references) <= 96
    assert len(atlas_result.relationships) == len(relationship_references)
    assert {
        relationship.edge_id for relationship in atlas_result.relationships
    } == {reference.artifact_id for reference in relationship_references}
    assert results[0].truncated
    assert any(
        "Evidence-reference budget" in reason
        for reason in results[0].truncation_reasons
    )


def test_nested_finding_artifacts_receive_independent_exact_references() -> None:
    node = _summary("finding-node")
    metric = AtlasMetricValue(
        node_id=node.node_id,
        metric="dependency.fan_in",
        value=7,
    )
    signal = ObscuritySignal(
        code="finding-signal",
        message="The finding retained this structural signal.",
        node_id=node.node_id,
    )
    finding = _finding(1).model_copy(
        update={
            "atlas_node_ids": [node.node_id],
            "affected_locations": [node],
            "metric_observations": [metric],
            "obscurity_signals": [signal],
        }
    )

    results = _retriever(
        _QueryService(lambda query: AtlasQueryResult(query=query))
    ).execute(
        run=_run(findings=[finding]),
        plan=_plan(
            GetFindingAction(kind="get_finding", finding_id=finding.finding_id)
        ),
    )

    references = results[0].evidence_references
    references_by_kind = {
        reference.kind.value: reference for reference in references
    }
    assert set(references_by_kind) == {
        "finding",
        "atlas_node",
        "atlas_metric",
        "atlas_signal",
    }
    assert references_by_kind["atlas_node"].node_id == node.node_id
    assert references_by_kind["atlas_metric"].node_id == node.node_id
    assert references_by_kind["atlas_signal"].node_id == node.node_id
    assert all(
        reference.scope is ConversationEvidenceScope.ORIGINAL_RUN
        for reference in references
    )


def test_reference_projection_removes_finding_with_uncitable_nested_artifacts() -> None:
    node_id = "overfull-finding-node"
    finding = _finding(1, node_ids=[node_id]).model_copy(
        update={
            "obscurity_signals": [
                ObscuritySignal(
                    code=f"signal-{ordinal}",
                    message=f"Retained signal {ordinal}.",
                    node_id=node_id,
                )
                for ordinal in range(100)
            ]
        }
    )

    results = _retriever(
        _QueryService(lambda query: AtlasQueryResult(query=query))
    ).execute(
        run=_run(findings=[finding]),
        plan=_plan(
            GetFindingAction(kind="get_finding", finding_id=finding.finding_id)
        ),
    )

    assert results[0].findings == []
    assert results[0].evidence_references == []
    assert results[0].truncated
    assert any(
        "Evidence-reference budget" in reason
        for reason in results[0].truncation_reasons
    )


def test_differing_duplicate_report_claim_ids_are_rejected() -> None:
    first = Claim(
        claim_id="claim-duplicate",
        text="First retained meaning.",
        classification=ClaimClassification.CONFIRMED_REQUIREMENT,
    )
    second = Claim(
        claim_id="claim-duplicate",
        text="Conflicting retained meaning.",
        classification=ClaimClassification.ADVISOR_INFERENCE,
    )
    report = _report()
    report.confirmed_context = [first]
    report.repository_observations = [second]
    run = cast(
        ConsultationRun,
        SimpleNamespace(
            report=report,
            focused_packets=[],
            concern_analyses=[],
            alternatives=[],
            scenarios=[],
            atlas_version_id=None,
        ),
    )

    with pytest.raises(
        ConversationRetrievalError,
        match="inconsistent report claims",
    ):
        _retriever(
            _QueryService(lambda query: AtlasQueryResult(query=query))
        ).execute(
            run=run,
            plan=_plan(
                GetReportClaimsAction(
                    kind="get_report_claims",
                    claim_ids=["claim-duplicate"],
                )
            ),
        )


def test_report_claim_retrieval_supplies_exact_original_node_location_reference() -> None:
    location = SourceLocation(path="architecture.py", start_line=12, end_line=18)
    claim = Claim(
        claim_id="claim-with-location",
        text="The application boundary owns the repository interaction.",
        classification=ClaimClassification.REPOSITORY_OBSERVATION,
        atlas_references=[
            AtlasEvidenceReference(
                node_id="application-boundary",
                location=location,
            )
        ],
    )
    report = _report()
    report.repository_observations = [claim]
    run = cast(
        ConsultationRun,
        SimpleNamespace(
            report=report,
            focused_packets=[],
            concern_analyses=[],
            alternatives=[],
            scenarios=[],
            atlas_version_id=None,
        ),
    )

    results = _retriever(
        _QueryService(lambda query: AtlasQueryResult(query=query))
    ).execute(
        run=run,
        plan=_plan(
            GetReportClaimsAction(
                kind="get_report_claims",
                claim_ids=[claim.claim_id],
            )
        ),
    )

    references = {
        reference.kind.value: reference
        for reference in results[0].evidence_references
    }
    assert set(references) == {"report_claim", "atlas_node"}
    assert references["atlas_node"].node_id == "application-boundary"
    assert references["atlas_node"].location == location
    assert references["atlas_node"].scope is ConversationEvidenceScope.ORIGINAL_RUN
