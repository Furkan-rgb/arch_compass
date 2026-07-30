"""Where the policy corpus comes from, and what is in it.

One truth about what policies exist, and it is the Markdown on disk. There used to be two:
this service could answer from a built SQLite index or from the sources themselves, and the
web read one while the CLI read the other — so the same workspace could report a different
corpus depending on which you asked. The index existed for retrieval, retrieval is gone
(ADR 0013), and what it left behind was a second answer to a question with one.

Reading the sources on every call is affordable and is the point: the corpus is about 45,000
characters, and a policy edited on disk is in the next review without a rebuild step
standing between the two.
"""

from __future__ import annotations

from pathlib import Path

from archcompass.domain.errors import PolicyFormatError, PolicyNotFoundError
from archcompass.domain.policy import (
    PolicyDocument,
    PolicyScope,
    PolicySourceRegistration,
)
from archcompass.ports.policies import PolicySourceInspector, PolicySourceRepository


class PolicyService:
    def __init__(
        self,
        *,
        source_repository: PolicySourceRepository,
        source_inspector: PolicySourceInspector,
        bundled_sources: tuple[Path, ...],
    ) -> None:
        self._source_repository = source_repository
        self._source_inspector = source_inspector
        self._bundled_sources = tuple(
            self._source_inspector.canonicalize(source, require_exists=False)
            for source in bundled_sources
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

        return self._source_inspector.load_documents(
            self.effective_sources(repository_root=repository_root)
        )

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

    def effective_sources(self, *, repository_root: Path | None = None) -> list[Path]:
        registered = [
            self._source_inspector.canonicalize(Path(item.canonical_path))
            for item in self._source_repository.list()
        ]
        sources = [*self._bundled_sources, *registered]
        if repository_root is not None:
            repository = repository_root.expanduser().resolve()
            sources.append(repository / ".archcompass" / "policies")
        return list(dict.fromkeys(sources))
