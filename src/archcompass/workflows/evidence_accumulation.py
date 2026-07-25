"""Turning executed Atlas queries into one bounded packet per concern cluster.

Query results arrive incrementally across zoom iterations. This accumulates them under
the cumulative node, relationship, test and excerpt budgets, records why each node was
selected so the packet is self-describing, and assembles the focused packet a cluster's
analysis receives.

Every drop is recorded as a truncation in the run's audit rather than passing silently:
a bounded packet is only honest if what fell outside the bound is visible.
"""

from __future__ import annotations

from collections import Counter

from archcompass.configuration import ConsultationConfig
from archcompass.domain.atlas import (
    Atlas,
    AtlasEdge,
    AtlasNode,
    AtlasNodeEvidence,
    AtlasNodeSummary,
    AtlasOverview,
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
    signal_investigation_rank,
)
from archcompass.domain.case import ArchitectureCase
from archcompass.domain.consultation import (
    ConcernCluster,
    FocusedAnalysisPacket,
    FocusedNodeSummary,
)
from archcompass.domain.policy import RetrievedPolicy


def accumulate_query_result(
    config: ConsultationConfig,
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
    reasons = selection_reasons(result)
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
        if len(selected_ids) >= config.max_query_results:
            record_truncation(
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

    relationship_limit = config.max_query_results * 4
    cluster_relationships = relationships[cluster_id]
    for edge in result.relationships:
        if edge.edge_id in cluster_relationships:
            continue
        if len(cluster_relationships) >= relationship_limit:
            record_truncation(
                execution_metadata,
                kind="relationship_budget",
                cluster_id=cluster_id,
                dropped=1,
            )
            continue
        cluster_relationships[edge.edge_id] = edge
    remaining_tests = config.max_query_results - len(test_ids[cluster_id])
    if remaining_tests > 0:
        test_ids[cluster_id].update(result.test_ids[:remaining_tests])
    if len(result.test_ids) > max(remaining_tests, 0):
        record_truncation(
            execution_metadata,
            kind="test_evidence_budget",
            cluster_id=cluster_id,
            dropped=len(result.test_ids) - max(remaining_tests, 0),
        )

    for excerpt in result.excerpts:
        if excerpt.node_id not in selected_ids:
            continue
        remaining = (
            config.max_excerpt_lines - excerpt_line_counts[cluster_id]
        )
        if remaining <= 0:
            record_truncation(
                execution_metadata,
                kind="excerpt_budget",
                cluster_id=cluster_id,
                dropped=len(excerpt.text.splitlines()),
            )
            continue
        lines = excerpt.text.splitlines()
        kept_lines = lines[:remaining]
        if len(kept_lines) < len(lines):
            record_truncation(
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

def selection_reasons(
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

def record_truncation(
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

def build_packet(
    config: ConsultationConfig,
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
                node=atlas_node_summary(node),
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
        record_truncation(
            execution_metadata,
            kind="relationship_endpoint_not_surfaced",
            cluster_id=cluster.cluster_id,
            dropped=dropped_relationships,
        )
    relationship_evidence = [
        AtlasRelationshipEvidence(
            edge_id=edge.edge_id,
            edge_type=edge.edge_type,
            source=atlas_node_summary(nodes[edge.source_id]),
            target=atlas_node_summary(nodes[edge.target_id]),
            confidence=edge.confidence,
            location=edge.location,
        )
        for edge in surfaced_relationships
    ]
    test_evidence = [
        atlas_node_summary(nodes[node_id])
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

def atlas_node_summary(node: AtlasNode) -> AtlasNodeSummary:
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

def atlas_overview(atlas: Atlas) -> AtlasOverview:
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
    representative_signals: list[ObscuritySignal] = []
    signals_by_code: dict[str, list[ObscuritySignal]] = {}
    for signal in atlas.signals:
        signals_by_code.setdefault(signal.code, []).append(signal)
    for code in sorted(
        signals_by_code,
        key=lambda value: (signal_investigation_rank(value), value),
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
                node=atlas_node_summary(node),
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
        top_level_nodes=[atlas_node_summary(node) for node in top_level],
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
