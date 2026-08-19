"""The corpus the graph judges against, read from the policy sources this workspace has.

The `PolicyCorpus` capability. `PolicyService` is the authority on what is in the corpus —
Markdown on disk — and this converts each document into the frozen domain `Policy` the
judge and the retriever both take, ordered by id so a fingerprint over the result is stable.
"""

from __future__ import annotations

from archcompass.domain import Policy, PolicyScope, PolicyStrength, RepositoryRef
from archcompass.policies.service import PolicyService


class DataclassPolicyCorpus:
    def __init__(self, policies: PolicyService) -> None:
        self._policies = policies

    def policies_for(self, repository: RepositoryRef) -> tuple[Policy, ...]:
        return tuple(
            Policy(
                id=item.id,
                title=item.title,
                body=item.body,
                scope=PolicyScope(item.scope.value),
                strength=PolicyStrength(item.strength.value),
                content_hash=item.content_hash,
                tags=tuple(item.tags),
                applies_to=item.applies_to,
                source=item.source_path,
            )
            for item in sorted(
                self._policies.catalog(repository_root=repository.path),
                key=lambda policy: policy.id,
            )
        )
