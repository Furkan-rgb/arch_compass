"""The corpus the graph judges against, read from the policy sources this workspace has.

The `PolicyCorpus` capability. `PolicyService` is the authority on what is in the corpus —
Markdown on disk — and this converts each document into the frozen domain `Policy` the
judge and the retriever both take, ordered by id so a fingerprint over the result is stable.
"""

from __future__ import annotations

from archcompass.domain import Policy, PolicyScope, PolicyStrength, RepositoryRef
from archcompass.policies.records import PolicyDocument
from archcompass.policies.service import PolicyService


def as_policy(document: PolicyDocument) -> Policy:
    """One parsed Markdown document as the domain policy the judge and retriever take.

    Public because the shipped index is built outside a workspace, by `adapters/bundled.py`,
    and a second conversion written there could disagree with this one about what a policy
    is — which would put vectors in the index for text no review ever judges against.
    """

    return Policy(
        id=document.id,
        title=document.title,
        body=document.body,
        scope=PolicyScope(document.scope.value),
        strength=PolicyStrength(document.strength.value),
        content_hash=document.content_hash,
        tags=tuple(document.tags),
        applies_to=document.applies_to,
        source=document.source_path,
    )


class DataclassPolicyCorpus:
    def __init__(self, policies: PolicyService) -> None:
        self._policies = policies

    def policies_for(self, repository: RepositoryRef) -> tuple[Policy, ...]:
        return tuple(
            as_policy(item)
            for item in sorted(
                self._policies.catalog(repository_root=repository.path),
                key=lambda policy: policy.id,
            )
        )
