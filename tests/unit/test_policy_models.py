from __future__ import annotations

import pytest
from pydantic import ValidationError

from archcompass.policies.records import (
    PolicyApplicabilityContext,
    PolicyDocument,
    PolicyScope,
    PolicySource,
    PolicyStrength,
)

# Retrieval-specific records are tested at the application/adapter boundary. This module
# checks only policy authoring and applicability DTO behavior.


def _policy(description: str | None = None) -> PolicyDocument:
    return PolicyDocument(
        id="policy-a",
        title="Policy A",
        description=description,
        scope=PolicyScope.ORGANISATION,
        applies_to="example-organisation",
        strength=PolicyStrength.PREFERRED,
        tags=[],
        source=PolicySource(author="Test"),
        body="Body",
        source_path="/policies/a.md",
        content_hash="hash",
    )


def test_scoped_policy_without_a_subject_never_applies_implicitly() -> None:
    policy = PolicyDocument.model_validate_json(
        """{
          "schema_version": 2,
          "id": "unassigned-organisation-policy",
          "title": "Unassigned organisation policy",
          "scope": "organisation",
          "strength": "preferred",
          "tags": [],
          "source": {"author": "Test", "inspiration": []},
          "body": "Body",
          "source_path": "/policies/unassigned.md",
          "content_hash": "unassigned-hash"
        }"""
    )

    assert policy.applies_to is None
    assert not policy.applies_in(PolicyApplicabilityContext(organisation="example-organisation"))


def test_policy_description_is_optional_and_stripped_when_present() -> None:
    assert _policy().description is None
    assert _policy(description="  What the rule asks for.  ").description == (
        "What the rule asks for."
    )


@pytest.mark.parametrize("description", ["", "   \n  "])
def test_blank_policy_description_is_rejected(description: str) -> None:
    with pytest.raises(ValidationError, match="nonempty"):
        _policy(description=description)


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
