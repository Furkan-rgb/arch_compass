"""Replay recorded synthesis payloads through the report contract and validators.

These tests pin the boundary between "a provider returned this" and "ArchCompass
accepted it". They intentionally construct payloads by hand instead of driving the
deterministic provider, so a refactor of either the provider or the workflow cannot
quietly change what the contract accepts.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from archcompass.application.evidence import validate_report_evidence
from archcompass.domain.consultation import RecommendationReport
from tests.replay import payloads


def _validate(payload: dict[str, object]) -> list[str]:
    report = RecommendationReport.model_validate(payload)
    return validate_report_evidence(
        report,
        allowed_nodes=payloads.allowed_nodes(),
        allowed_policy_ids=payloads.allowed_policy_ids(),
    )


def test_baseline_payload_is_accepted_without_errors() -> None:
    assert _validate(payloads.valid_report()) == []


@pytest.mark.xfail(
    reason=(
        "WS1: schema_version is defaulted, so its absence is currently read as a "
        "legacy schema-v1 report and routed into migration heuristics"
    ),
    strict=True,
)
def test_report_without_schema_version_is_rejected() -> None:
    """A provider that omits schema_version must not be read as a legacy report.

    ``schema_version`` is a defaulted field, so the JSON schema handed to the model
    does not require it. Treating its absence as "schema v1" silently routes fresh
    output into migration heuristics that infer a disposition from keywords and
    fabricate findings from claims.
    """

    payload = payloads.without(payloads.valid_report(), "schema_version")
    with pytest.raises(ValidationError):
        RecommendationReport.model_validate(payload)


@pytest.mark.xfail(
    reason=(
        "WS1: SupportedStatement.legacy is part of the model-facing schema and "
        "exempts a statement from citing supporting claims"
    ),
    strict=True,
)
def test_statement_cannot_opt_out_of_evidence_support() -> None:
    """No in-band flag may exempt a statement from citing its supporting claims."""

    payload = payloads.valid_report()
    payload["decision_summary"] = {
        "text": "An unsupported decision.",
        "classification": "advisor_inference",
        "supporting_claim_ids": [],
        "legacy": True,
    }
    with pytest.raises(ValidationError):
        RecommendationReport.model_validate(payload)


def test_unknown_atlas_node_reference_is_reported() -> None:
    payload = payloads.valid_report()
    observation = payloads.claim(
        "claim_observation",
        "An invented module owns provider selection.",
        "repository_observation",
        node_ids=["node_invented"],
    )
    payload["repository_observations"] = [observation]
    payload["evidence_appendix"] = [
        observation if item["claim_id"] == "claim_observation" else item
        for item in payload["evidence_appendix"]
    ]
    payload["findings"][0]["atlas_node_ids"] = ["node_invented"]
    errors = _validate(payload)
    assert any("unknown atlas node" in error.casefold() for error in errors)


def test_unretrieved_policy_reference_is_reported() -> None:
    payload = payloads.valid_report()
    guidance = payloads.claim(
        "claim_policy",
        "An invented policy applies here.",
        "policy_guidance",
        policy_ids=["policy-invented"],
    )
    payload["relevant_policies"] = [guidance]
    payload["evidence_appendix"] = [
        guidance if item["claim_id"] == "claim_policy" else item
        for item in payload["evidence_appendix"]
    ]
    payload["policy_evidence"] = [
        {
            "id": "policy-invented",
            "title": "Invented policy",
            "scope": "general",
            "strength": "guidance",
            "matched_sections": ["Intent"],
        }
    ]
    payload["findings"][0]["policy_ids"] = ["policy-invented"]
    errors = _validate(payload)
    assert any("not retrieved" in error.casefold() for error in errors)


def test_duplicate_claim_id_with_different_content_is_reported() -> None:
    payload = payloads.valid_report()
    conflicting = payloads.claim(
        "claim_requirement",
        "A different statement reusing an existing claim ID.",
        "scenario_assumption",
    )
    payload["assumptions_and_unresolved_questions"] = [conflicting]
    errors = _validate(payload)
    assert any("reused" in error.casefold() for error in errors)


def test_statement_referencing_an_unknown_claim_is_reported() -> None:
    payload = payloads.valid_report()
    payload["decision_summary"]["supporting_claim_ids"] = ["claim_missing"]
    errors = _validate(payload)
    assert any("unknown claim" in error.casefold() for error in errors)


def test_misclassified_section_claim_is_rejected_by_the_contract() -> None:
    payload = payloads.valid_report()
    payload["confirmed_context"] = [
        payloads.claim(
            "claim_requirement",
            "A policy statement filed under confirmed context.",
            "policy_guidance",
            policy_ids=[payloads.POLICY_ID],
        )
    ]
    with pytest.raises(ValidationError):
        RecommendationReport.model_validate(payload)


def test_scenario_missing_an_alternative_is_rejected() -> None:
    payload = payloads.valid_report()
    payload["scenario_analysis"][0]["alternative_results"] = {
        "alt_port": "Only a new adapter is added."
    }
    with pytest.raises(ValidationError):
        RecommendationReport.model_validate(payload)


def test_finding_citing_a_claim_it_does_not_own_is_rejected() -> None:
    payload = payloads.valid_report()
    payload["findings"][0]["claim_ids"] = ["claim_missing"]
    with pytest.raises(ValidationError):
        RecommendationReport.model_validate(payload)


def test_finding_node_without_claim_support_is_rejected() -> None:
    payload = payloads.valid_report()
    payload["findings"][0]["claim_ids"] = ["claim_policy"]
    with pytest.raises(ValidationError):
        RecommendationReport.model_validate(payload)
