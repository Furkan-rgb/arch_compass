"""Validated names and interpretation metadata for analyzer metrics."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

from archcompass.boundary.atlas import (
    AtlasMetricValue,
    MetricNature,
    MetricProfile,
    MetricScope,
)

#: How soon a signal warrants investigation, lowest first. Signals needing
#: architectural interpretation outrank routine measurements, which are numerous and
#: rarely the reason to look somewhere. Codes absent here take the default rank, so a
#: new analyzer signal is ordinary until someone decides otherwise.
#:
#: This lives beside the other interpretation metadata rather than in the workflow that
#: consumes it: the ranking is a judgement about what an Atlas signal *means*, and the
#: consultation overview, evaluations and any later consumer must all agree on it.
_DEFAULT_SIGNAL_RANK: Final = 2
_SIGNAL_INVESTIGATION_RANK: Final[dict[str, int]] = {
    "broad-input-boundary-preparation": 0,
    "parallel-boundary-preparation": 1,
    "cyclic-dependency": 2,
}


def signal_investigation_rank(code: str) -> int:
    """Rank one obscurity-signal code for overview ordering."""

    return _SIGNAL_INVESTIGATION_RANK.get(code, _DEFAULT_SIGNAL_RANK)


@dataclass(frozen=True)
class _MetricMetadata:
    definition: str
    limitations: str = ""


_METRIC_METADATA = {
    "local.branch_count": _MetricMetadata(
        "Lexical control-flow branch constructs owned by this node.",
        "Static syntax count; it is not a measure of runtime path frequency.",
    ),
    "dependency.fan_in": _MetricMetadata(
        "Direct internal modules that statically depend on the owning module.",
        "Dynamic imports and unresolved calls are not included.",
    ),
    "dependency.fan_out": _MetricMetadata(
        "Direct internal modules on which the owning module statically depends.",
        "Dynamic imports and unresolved calls are not included.",
    ),
    "dependency.forward_dependency_reach": _MetricMetadata(
        "Distinct modules transitively reachable through resolved internal imports.",
        "This is static reachability, not runtime traffic.",
    ),
    "dependency.reverse_dependency_reach": _MetricMetadata(
        "Distinct modules that transitively depend on the owning module.",
        "This is static reachability and may omit dynamic dependencies.",
    ),
    "dependency.cycle_size": _MetricMetadata(
        "Modules in the owning module's resolved import strongly connected component.",
    ),
    "change_amplification.likely_affected_modules": _MetricMetadata(
        "Modules reachable in the reverse resolved import-and-call impact graph.",
        "A reachability proxy does not prove that every module must change.",
    ),
    "change_amplification.public_call_targets_in_affected_modules": _MetricMetadata(
        "Distinct public call targets whose endpoint owners are in the affected module set.",
        "This does not prove that an architectural interface or boundary is crossed.",
    ),
    "cognitive_scope.dependency_neighbourhood_modules": _MetricMetadata(
        "Union of forward- and reverse-reachable internal modules.",
        "A structural neighbourhood is only a proxy for human cognitive effort.",
    ),
    "cognitive_scope.bounded_resolved_call_chain_nodes": _MetricMetadata(
        "Nodes on one deterministic resolved call chain, including the selected node.",
        "The chain is capped at twenty and is not claimed to be a critical runtime path.",
    ),
    "cognitive_scope.abstraction_boundaries": _MetricMetadata(
        "Interface-ownership transitions along the bounded resolved call chain.",
        "Static ownership transitions are a proxy for conceptual boundary crossings.",
    ),
}


def canonical_metric_name(name: str) -> str:
    """Return the emitted schema-v2 name for a simple or qualified metric key."""
    normalized = name.replace("-", "_")
    if "." in normalized:
        group, metric = normalized.split(".", maxsplit=1)
        return f"{group}.{metric}"
    return normalized


def metric_observation(
    profile: MetricProfile,
    name: str,
    *,
    rank: int | None = None,
) -> AtlasMetricValue | None:
    """Create a typed observation with truthfulness metadata."""
    requested = canonical_metric_name(name)
    group_name: str | None = None
    metric_name = requested
    if "." in requested:
        group_name, metric_name = requested.split(".", maxsplit=1)
    groups = (
        (group_name, getattr(profile, group_name))
        if group_name
        in {
            "local",
            "dependency",
            "change_amplification",
            "cognitive_scope",
        }
        else None
    )
    candidates = (
        [groups]
        if groups is not None
        else [
            (name, getattr(profile, name))
            for name in (
                "local",
                "dependency",
                "change_amplification",
                "cognitive_scope",
            )
        ]
    )
    for candidate_group, group in candidates:
        value = getattr(group, metric_name, None)
        if not isinstance(value, (int, float)):
            continue
        qualified = f"{candidate_group}.{metric_name}"
        nature, scope = _nature_and_scope(candidate_group, metric_name)
        metadata = _METRIC_METADATA.get(
            qualified,
            _MetricMetadata(
                f"Static atlas value for {qualified.replace('_', ' ').replace('.', ' / ')}."
            ),
        )
        return AtlasMetricValue(
            node_id=profile.node_id,
            metric=qualified,
            value=value,
            rank=rank,
            nature=nature,
            scope=scope,
            definition=metadata.definition,
            limitations=metadata.limitations,
        )
    return None


def profile_observations(profile: MetricProfile) -> list[AtlasMetricValue]:
    """Return every numeric profile field as a self-describing observation."""
    observations: list[AtlasMetricValue] = []
    for group_name in (
        "local",
        "dependency",
        "change_amplification",
        "cognitive_scope",
    ):
        group = getattr(profile, group_name)
        for metric, value in group.model_dump().items():
            if not isinstance(value, (int, float)):
                continue
            observation = metric_observation(profile, f"{group_name}.{metric}")
            if observation is not None:
                observations.append(observation)
    return observations


def salient_profile_observations(
    profile: MetricProfile,
    *,
    limit: int = 8,
) -> list[AtlasMetricValue]:
    """Return a stable architectural subset rather than an unlabelled metric dump."""
    preferred = (
        "dependency.reverse_dependency_reach",
        "dependency.fan_in",
        "dependency.fan_out",
        "change_amplification.likely_affected_modules",
        "change_amplification.public_call_targets_in_affected_modules",
        "local.branch_count",
        "dependency.cycle_size",
        "cognitive_scope.bounded_resolved_call_chain_nodes",
        "cognitive_scope.abstraction_boundaries",
    )
    result: list[AtlasMetricValue] = []
    for name in preferred:
        observation = metric_observation(profile, name)
        if observation is None:
            continue
        result.append(observation)
        if len(result) == limit:
            break
    return result


def _nature_and_scope(
    group_name: str,
    metric_name: str,
) -> tuple[MetricNature, MetricScope]:
    if group_name == "local":
        return MetricNature.MEASUREMENT, MetricScope.LEXICAL_NODE
    if group_name == "dependency":
        return MetricNature.MEASUREMENT, MetricScope.OWNING_MODULE
    if group_name == "cognitive_scope" and metric_name in {
        "bounded_resolved_call_chain_nodes",
        "abstraction_boundaries",
    }:
        return (
            MetricNature.STRUCTURAL_PROXY,
            MetricScope.BOUNDED_RESOLVED_CALL_CHAIN,
        )
    return (
        MetricNature.STRUCTURAL_PROXY,
        MetricScope.REVERSE_STATIC_IMPACT_NEIGHBOURHOOD,
    )
