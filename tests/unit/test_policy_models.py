from __future__ import annotations

from archcompass.domain.policy import (
    PolicyApplicabilityContext,
    PolicyDocument,
    PolicyScope,
    PolicySource,
    PolicyStrength,
)

# No evidence-summary or conflict tests. `PolicyEvidenceSummary`, `RetrievedPolicy`,
# `PolicyChunk` and `PolicyConflict` described the shape of a retrieval result — which
# policy sections were matched, how far away they were, how two of them were reconciled —
# and nothing retrieves. A policy reaches every stage whole (ADR 0013), so what is left to
# test about the corpus is which policies apply to whom.


def _policy() -> PolicyDocument:
    return PolicyDocument(
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
    organisation_policy = _policy()

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
