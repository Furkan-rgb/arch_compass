from __future__ import annotations

from dataclasses import replace

import pytest
from pydantic import ValidationError

from archcompass.domain.policy import Policy, PolicyScope, PolicyStrength
from archcompass.policies.records import PolicyDocument, PolicySource

# Retrieval-specific records are tested at the application/adapter boundary. This module
# checks policy authoring on the transport record, and applicability on the domain record
# that production actually asks. The two used to be one file's worth of near-identical code
# — `PolicyDocument` carried its own `applies_in` and its own copies of both enums — and
# the applicability tests were written against the copy nothing called.


def _domain(document: PolicyDocument) -> Policy:
    """The same policy as the domain holds it, which is what retrieval asks."""

    return Policy(
        id=document.id,
        title=document.title,
        body=document.body,
        scope=document.scope,
        strength=document.strength,
        content_hash=document.content_hash,
        applies_to=document.applies_to,
    )


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
    assert not _domain(policy).applies_in(
        user=None, organisation="example-organisation", repository=None
    )


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
    organisation = _domain(_policy())

    assert organisation.applies_in(
        user=None, organisation="example-organisation", repository=None
    )
    assert not organisation.applies_in(
        user=None, organisation="another-organisation", repository=None
    )
    assert not organisation.applies_in(user=None, organisation=None, repository=None)

    general = replace(organisation, scope=PolicyScope.GENERAL, applies_to=None)
    assert general.applies_in(user=None, organisation=None, repository=None)
