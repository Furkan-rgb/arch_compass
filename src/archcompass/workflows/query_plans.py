"""Making one model-proposed query plan executable.

A plan arrives per concern cluster and may be wrong in ways that are recoverable
without a second model call: a cluster missing, duplicated, mislabelled by iteration,
over budget, or naming a node the cluster has not surfaced yet. Each is corrected or
dropped here and recorded in the run's audit, so the executor receives exactly one
bounded, executable plan per cluster.

This is allowlist and budget enforcement, not model-output repair: nothing here invents
a query, and every correction is visible in `execution_metadata`.
"""

from __future__ import annotations

from archcompass.domain.atlas import AtlasQuery, AtlasQueryPlan
from archcompass.domain.consultation import ClusterQueryPlan, ConcernCluster
from archcompass.domain.errors import ModelOutputValidationError


def validate_cluster_plans(
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

def repair_cluster_plans(
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

def clamp_iteration_plans(
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

def drop_unsurfaced_query_references(
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
