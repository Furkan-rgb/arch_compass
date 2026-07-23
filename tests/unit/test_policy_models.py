from __future__ import annotations

import pytest
from pydantic import ValidationError

from archcompass.domain.policy import (
    PolicyChunk,
    PolicyConflict,
    PolicyDocument,
    PolicyEvidenceSummary,
    PolicyScope,
    PolicySource,
    PolicyStrength,
    RetrievedPolicy,
)


def _retrieved_policy() -> RetrievedPolicy:
    policy = PolicyDocument(
        id="policy-a",
        title="Policy A",
        scope=PolicyScope.ORGANISATION,
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
        retrieved.model_copy(
            update={"chunks": [*retrieved.chunks, duplicate]}
        )
    )

    assert summary.model_dump(mode="json") == {
        "id": "policy-a",
        "title": "Policy A",
        "scope": "organisation",
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
