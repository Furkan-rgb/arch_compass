"""Hand-authored stage-output payloads for deterministic replay tests.

These payloads are deliberately independent of ``DeterministicReasoningProvider``.
A replay fixture describes what a *provider* could plausibly return, so the tests
exercise the validators, canonicalizers, and composers rather than the fake
reasoner's knowledge of the evaluation fixtures.

Every builder returns plain JSON-compatible data. Tests mutate a copy to express
one specific malformed shape, which keeps each failure mode readable in isolation.
"""

from __future__ import annotations

import copy
from typing import Any

from archcompass.domain.atlas import AtlasNode, NodeType

NODE_ID = "node_provider_adapter"
NODE_PATH = "src/app/provider.py"
POLICY_ID = "hide-implementation-details"
SECOND_POLICY_ID = "contain-dependencies"
CLUSTER_ID = "cluster_ownership"
PARSER_VERSION = "python-ast-v1"


def allowed_nodes() -> dict[str, AtlasNode]:
    """The Atlas nodes a replayed report is permitted to reference."""

    return {
        NODE_ID: AtlasNode(
            atlas_id=NODE_ID,
            path=NODE_PATH,
            symbol_name="ProviderAdapter",
            qualified_name="app.provider.ProviderAdapter",
            node_type=NodeType.CLASS,
            start_line=10,
            end_line=80,
            parser_version=PARSER_VERSION,
        )
    }


def allowed_policy_ids() -> set[str]:
    return {POLICY_ID, SECOND_POLICY_ID}


def claim(
    claim_id: str,
    text: str,
    classification: str,
    *,
    node_ids: list[str] | None = None,
    policy_ids: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "claim_id": claim_id,
        "text": text,
        "classification": classification,
        "atlas_references": [
            {
                "node_id": node_id,
                "location": {"path": NODE_PATH, "start_line": 12, "end_line": 40},
            }
            for node_id in (node_ids or [])
        ],
        "policy_ids": list(policy_ids or []),
    }


def statement(text: str, classification: str, claim_ids: list[str]) -> dict[str, Any]:
    return {
        "text": text,
        "classification": classification,
        "supporting_claim_ids": list(claim_ids),
    }


def valid_report() -> dict[str, Any]:
    """A schema-v3 report that passes both model validation and evidence validation."""

    requirement = claim(
        "claim_requirement",
        "The team confirmed that provider selection must stay configurable.",
        "confirmed_user_requirement",
    )
    observation = claim(
        "claim_observation",
        "ProviderAdapter exposes transport details to the application layer.",
        "repository_observation",
        node_ids=[NODE_ID],
    )
    guidance = claim(
        "claim_policy",
        "Hide implementation details behind the boundary that owns them.",
        "policy_guidance",
        policy_ids=[POLICY_ID],
    )
    assumption = claim(
        "claim_assumption",
        "No second provider is committed for the next two quarters.",
        "scenario_assumption",
    )
    return {
        "schema_version": 3,
        "report_id": "report_replay_baseline",
        "disposition": "move_responsibility",
        "decision_summary": statement(
            "Move transport concerns behind the provider port.",
            "advisor_inference",
            ["claim_observation"],
        ),
        "problem_and_desired_outcome": (
            "Provider transport details leak into application code; the team wants "
            "the application layer to depend only on a stable port."
        ),
        "confirmed_context": [requirement],
        "assumptions_and_unresolved_questions": [assumption],
        "important_design_forces": [
            {
                "force_id": "force_provider_variation",
                "title": "Provider variation",
                "description": "A second provider is plausible but uncommitted.",
                "importance": "medium",
            }
        ],
        "findings": [
            {
                "finding_id": "FIND-001",
                "title": "Transport details cross the application boundary",
                "summary": "The adapter's transport vocabulary reaches application code.",
                "concern_cluster_id": CLUSTER_ID,
                "importance": "high",
                "importance_rationale": (
                    "Every application change must currently reason about transport."
                ),
                "confidence": {
                    "level": "medium",
                    "rationale": "Based on one surfaced node and one policy.",
                },
                "consequence": "Application changes require transport knowledge.",
                "claim_ids": ["claim_observation", "claim_policy"],
                "atlas_node_ids": [NODE_ID],
                "policy_ids": [POLICY_ID],
                "affected_locations": [],
                "metric_observations": [],
                "obscurity_signals": [],
                "recommended_response": "Introduce a narrow provider port.",
                "uncertainty": ["The second provider is not committed."],
            }
        ],
        "repository_observations": [observation],
        "relevant_policies": [guidance],
        "policy_evidence": [
            {
                "id": POLICY_ID,
                "title": "Hide implementation details",
                "scope": "general",
                "strength": "guidance",
                "matched_sections": ["Intent"],
            }
        ],
        "policy_conflicts": [],
        "recommended_architecture": statement(
            "Define a provider port owned by the application layer.",
            "advisor_inference",
            ["claim_observation"],
        ),
        "responsibility_allocation": [
            statement(
                "The adapter owns transport; the application owns orchestration.",
                "advisor_inference",
                ["claim_observation"],
            )
        ],
        "conceptual_interfaces": [
            statement(
                "A provider port exposing one domain operation.",
                "advisor_inference",
                ["claim_policy"],
            )
        ],
        "alternatives_considered": [
            {
                "id": "alt_keep_local",
                "title": "Keep the current design",
                "summary": "Leave transport handling where it is.",
            },
            {
                "id": "alt_port",
                "title": "Introduce a provider port",
                "summary": "Move transport behind a narrow port.",
            },
        ],
        "scenario_analysis": [
            {
                "scenario": "A second provider is adopted.",
                "assumptions": ["The second provider uses a different transport."],
                "alternative_results": {
                    "alt_keep_local": "Application code changes in several places.",
                    "alt_port": "Only a new adapter is added.",
                },
                "conclusion": "The port contains the change.",
            }
        ],
        "change_amplification_analysis": statement(
            "Transport changes currently reach application modules.",
            "repository_observation",
            ["claim_observation"],
        ),
        "trade_offs": [
            statement(
                "One additional indirection in exchange for contained change.",
                "advisor_inference",
                ["claim_assumption"],
            )
        ],
        "implementation_sequence": [
            statement(
                "Define the port, then move the adapter behind it.",
                "advisor_inference",
                ["claim_observation"],
            )
        ],
        "confidence": {
            "level": "medium",
            "rationale": "One surfaced node supports the observation.",
        },
        "reversal_conditions": [
            statement(
                "Reverse if the second provider is formally cancelled.",
                "scenario_assumption",
                ["claim_assumption"],
            )
        ],
        "revisit_triggers": [
            statement(
                "Revisit when a second provider is committed.",
                "scenario_assumption",
                ["claim_assumption"],
            )
        ],
        "adr": {
            "title": "Introduce a provider port",
            "status": "proposed",
            "context": "Transport details leak into application code.",
            "decision": statement(
                "Adopt a provider port.",
                "advisor_inference",
                ["claim_observation"],
            ),
            "consequences": [
                statement(
                    "Application code no longer references transport types.",
                    "advisor_inference",
                    ["claim_observation"],
                )
            ],
        },
        "evidence_appendix": [requirement, observation, guidance, assumption],
    }


def without(payload: dict[str, Any], key: str) -> dict[str, Any]:
    """Return a copy of ``payload`` with ``key`` removed."""

    mutated = copy.deepcopy(payload)
    mutated.pop(key, None)
    return mutated


def mutated(payload: dict[str, Any], **updates: Any) -> dict[str, Any]:
    """Return a deep copy of ``payload`` with top-level ``updates`` applied."""

    copied = copy.deepcopy(payload)
    copied.update(copy.deepcopy(updates))
    return copied
