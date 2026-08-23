"""Where the policy corpus comes from, and what is in it.

Markdown sources are the authority for corpus content. Retrieval indexing is a derived,
content-hashed concern behind `PolicyRetriever`; it never becomes a second policy catalog.
A policy edited on disk is therefore visible to the next corpus read, while the retriever
incrementally refreshes only the affected chunks.
"""

from __future__ import annotations

from pathlib import Path

from archcompass.domain.errors import (
    PolicyConflictError,
    PolicyFormatError,
    PolicyNotFoundError,
)
from archcompass.policies.ports import (
    PolicySourceInspector,
    PolicySourceRepository,
    PolicyStore,
)
from archcompass.policies.records import (
    PolicyDocument,
    PolicyDraft,
    PolicyOrigin,
    PolicyScope,
    PolicySourceRegistration,
    policy_slug,
)


class PolicyService:
    def __init__(
        self,
        *,
        source_repository: PolicySourceRepository,
        source_inspector: PolicySourceInspector,
        bundled_sources: tuple[Path, ...],
        authored_source: Path,
        policy_store: PolicyStore,
    ) -> None:
        self._source_repository = source_repository
        self._source_inspector = source_inspector
        self._policy_store = policy_store
        self._bundled_sources = tuple(
            self._source_inspector.canonicalize(source, require_exists=False)
            for source in bundled_sources
        )
        #: The workspace's own policies, a standing source like the bundled corpus rather
        #: than a registered one. It is where writing goes, so it is read whether or not it
        #: exists yet: a workspace nobody has authored in has an empty one, not a missing
        #: source the first write would have to remember to register.
        self._authored_source = self._source_inspector.canonicalize(
            authored_source, require_exists=False
        )

    def add_source(self, source: Path) -> PolicySourceRegistration:
        canonical = self._source_inspector.canonicalize(source)
        documents = self._source_inspector.load_documents([canonical])
        local_policy_ids = sorted(
            document.id
            for document in documents
            if document.scope in {PolicyScope.REPOSITORY, PolicyScope.ACCEPTED_ADR}
        )
        if local_policy_ids:
            raise PolicyFormatError(
                "Repository and accepted-ADR policies cannot be registered globally; "
                "place them in <repository>/.archcompass/policies instead "
                f"(found: {', '.join(local_policy_ids)})"
            )
        return self._source_repository.add(
            PolicySourceRegistration(canonical_path=str(canonical))
        )

    def remove_source(self, source: Path) -> bool:
        canonical = self._source_inspector.canonicalize(
            source, require_exists=False
        )
        return self._source_repository.remove(str(canonical))

    def list_sources(self) -> list[PolicySourceRegistration]:
        return self._source_repository.list()

    def catalog(
        self, *, repository_root: Path | None = None
    ) -> list[PolicyDocument]:
        """Every policy in reach, read from its source.

        `repository_root` adds that repository's own `.archcompass/policies` to the
        sources, which is how a project's local policies reach a review of it and nothing
        else.
        """

        return [
            self._attributed(document)
            for document in self._source_inspector.load_documents(
                self.effective_sources(repository_root=repository_root)
            )
        ]

    def get(
        self, policy_id: str, *, repository_root: Path | None = None
    ) -> PolicyDocument:
        """One policy by id, resolved through the same catalog every stage is shown.

        Looked up here rather than in a route or a command, so "which policies exist" has
        one answer and "show me this one" cannot disagree with it.
        """

        for policy in self.catalog(repository_root=repository_root):
            if policy.id == policy_id:
                return policy
        raise PolicyNotFoundError(f"Policy {policy_id} was not found")

    def create(self, draft: PolicyDraft) -> PolicyDocument:
        """Write a policy of this workspace's own, filed under a slug of its title.

        The id is checked against the whole effective catalog rather than against the
        authored directory alone: two policies with one id is a corpus that cannot be
        loaded at all, so a title that collides with a bundled rule is refused before
        anything is written rather than after.
        """

        policy_id = policy_slug(draft.title)
        if any(policy.id == policy_id for policy in self.catalog()):
            raise PolicyConflictError(
                f"A policy called {policy_id} already exists; give this one another title"
            )
        return self._write(policy_id, draft)

    def update(self, policy_id: str, draft: PolicyDraft) -> PolicyDocument:
        """Rewrite one of this workspace's policies, keeping the id it is cited by.

        The title may change and the id does not follow it. An id is what a review's
        bearings name and what a `## Related policies` section points at, so renaming the
        file on a reworded title would silently break every reference to it — the same
        reason bundled ids do not restate their titles.
        """

        self._authored(policy_id)
        return self._write(policy_id, draft)

    def delete(self, policy_id: str) -> None:
        self._authored(policy_id)
        self._policy_store.remove(self._authored_source, policy_id)

    def _authored(self, policy_id: str) -> PolicyDocument:
        """The policy under this id, provided this workspace is the one that wrote it."""

        policy = self.get(policy_id)
        if policy.origin is not PolicyOrigin.WORKSPACE:
            raise PolicyConflictError(
                f"Policy {policy_id} is read here, not authored here: it lives in "
                f"{policy.source_path}, which Arch Compass does not own"
            )
        return policy

    def _write(self, policy_id: str, draft: PolicyDraft) -> PolicyDocument:
        staged = self._policy_store.stage(self._authored_source, policy_id, draft)
        try:
            self._source_inspector.load_documents([staged])
        except PolicyFormatError:
            self._policy_store.discard(staged)
            raise
        published = self._policy_store.publish(staged)
        return self._attributed(self._source_inspector.load_documents([published])[0])

    def _attributed(self, document: PolicyDocument) -> PolicyDocument:
        if Path(document.source_path).is_relative_to(self._authored_source):
            return document.model_copy(update={"origin": PolicyOrigin.WORKSPACE})
        return document

    def effective_sources(self, *, repository_root: Path | None = None) -> list[Path]:
        registered = [
            self._source_inspector.canonicalize(Path(item.canonical_path))
            for item in self._source_repository.list()
        ]
        sources = [*self._bundled_sources, self._authored_source, *registered]
        if repository_root is not None:
            repository = repository_root.expanduser().resolve()
            sources.append(repository / ".archcompass" / "policies")
        return list(dict.fromkeys(sources))
