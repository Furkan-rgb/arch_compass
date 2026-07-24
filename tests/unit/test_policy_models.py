from __future__ import annotations

import pytest
from pydantic import ValidationError

from archcompass.domain.policy import (
    PolicyApplicabilityContext,
    PolicyChunk,
    PolicyConflict,
    PolicyDocument,
    PolicyEvidenceSummary,
    PolicyScope,
    PolicySource,
    PolicyStrength,
    RetrievedPolicy,
    canonical_policy_evidence,
)


def _retrieved_policy() -> RetrievedPolicy:
    policy = PolicyDocument(
        id="policy-a",
        title="Policy A",
        scope=PolicyScope.ORGANISATION,
        applies_to="example-organisation",
        strength=PolicyStrength.PREFERRED,
        tags=[],
        source=PolicySource(author="Test"),
        body="Body",
        source_path="/policies/a.md",
        content_hash="hash",
    )
    return RetrievedPolicy(
        policy=policy,
        chunks=[
            PolicyChunk(
                chunk_id="chunk-a",
                policy_id=policy.id,
                section="Guidance",
                ordinal=0,
                text="Guidance text",
                content_hash="chunk-hash",
            )
        ],
        distance=0.25,
    )


def test_policy_evidence_summary_preserves_canonical_metadata() -> None:
    retrieved = _retrieved_policy()
    duplicate = retrieved.chunks[0].model_copy(
        update={
            "chunk_id": "chunk-duplicate",
            "section": "  guidance  ",
        }
    )
    summary = PolicyEvidenceSummary.from_retrieved(
        retrieved.model_copy(update={"chunks": [*retrieved.chunks, duplicate]})
    )

    assert summary.model_dump(mode="json") == {
        "id": "policy-a",
        "title": "Policy A",
        "scope": "organisation",
        "applies_to": "example-organisation",
        "strength": "preferred",
        "matched_sections": ["Guidance"],
    }


def test_policy_evidence_summary_rejects_more_than_three_sections() -> None:
    with pytest.raises(ValidationError, match="At most three"):
        PolicyEvidenceSummary(
            id="policy-a",
            title="Policy A",
            scope=PolicyScope.GENERAL,
            strength=PolicyStrength.GUIDANCE,
            matched_sections=["Intent", "Guidance", "Signals", "Exceptions"],
        )


def test_cross_cluster_policy_evidence_merges_sections_stably() -> None:
    first = _retrieved_policy()
    second = first.model_copy(
        update={
            "chunks": [
                first.chunks[0].model_copy(
                    update={
                        "chunk_id": "chunk-exceptions",
                        "section": "Exceptions",
                    }
                ),
                first.chunks[0].model_copy(
                    update={
                        "chunk_id": "chunk-guidance-again",
                        "section": " guidance ",
                    }
                ),
            ]
        }
    )

    summaries = canonical_policy_evidence([first, second])

    assert len(summaries) == 1
    assert summaries[0].matched_sections == ["Guidance", "Exceptions"]
    assert summaries[0].applies_to == "example-organisation"


def test_policy_conflict_requires_two_distinct_policy_ids() -> None:
    with pytest.raises(ValidationError, match="at least two distinct"):
        PolicyConflict(
            policy_ids=["policy-a", "policy-a"],
            explanation="The policies pull in different directions.",
            reconciliation="Apply the stronger policy.",
        )

    conflict = PolicyConflict(
        policy_ids=["policy-a", "policy-b"],
        explanation="The policies pull in different directions.",
        reconciliation="Apply each within its documented scope.",
    )
    assert conflict.policy_ids == ["policy-a", "policy-b"]


def test_legacy_scoped_policy_json_without_applies_to_still_loads_safely() -> None:
    policy = PolicyDocument.model_validate_json(
        """{
          "schema_version": 2,
          "id": "legacy-organisation-policy",
          "title": "Legacy organisation policy",
          "scope": "organisation",
          "strength": "preferred",
          "tags": [],
          "source": {"author": "Test", "inspiration": []},
          "body": "Body",
          "source_path": "/policies/legacy.md",
          "content_hash": "legacy-hash"
        }"""
    )

    assert policy.applies_to is None
    assert not policy.applies_in(PolicyApplicabilityContext(organisation="example-organisation"))


def test_policy_applicability_matches_only_its_scoped_subject() -> None:
    organisation_policy = _retrieved_policy().policy.model_copy(
        update={"applies_to": "example-organisation"}
    )

    assert organisation_policy.applies_in(
        PolicyApplicabilityContext(organisation="example-organisation")
    )
    assert not organisation_policy.applies_in(
        PolicyApplicabilityContext(organisation="another-organisation")
    )
    assert not organisation_policy.applies_in()

    general_policy = organisation_policy.model_copy(
        update={"scope": PolicyScope.GENERAL, "applies_to": None}
    )
    assert general_policy.applies_in()
