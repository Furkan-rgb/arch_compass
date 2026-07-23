"""Application service for workspace policy sources and immutable policy indexes."""

from __future__ import annotations

from pathlib import Path

from archcompass.domain.policy import (
    PolicyDocument,
    PolicyIndexVersion,
    PolicySourceRegistration,
)
from archcompass.ports.policies import (
    PolicyIndex,
    PolicySourceInspector,
    PolicySourceRepository,
)


class PolicyService:
    def __init__(
        self,
        *,
        index: PolicyIndex,
        source_repository: PolicySourceRepository,
        source_inspector: PolicySourceInspector,
        bundled_sources: tuple[Path, ...],
    ) -> None:
        self._index = index
        self._source_repository = source_repository
        self._source_inspector = source_inspector
        self._bundled_sources = tuple(
            self._source_inspector.canonicalize(source, require_exists=False)
            for source in bundled_sources
        )

    def add_source(self, source: Path) -> PolicySourceRegistration:
        canonical = self._source_inspector.canonicalize(source)
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

    def rebuild(
        self,
        *,
        sources: list[Path] | None = None,
        repository_root: Path | None = None,
    ) -> PolicyIndexVersion:
        for source in sources or []:
            self.add_source(source)
        return self._index.rebuild(self.effective_sources(repository_root=repository_root))

    def ensure_current(
        self, *, repository_root: Path | None = None
    ) -> PolicyIndexVersion:
        return self._index.ensure_current(
            self.effective_sources(repository_root=repository_root)
        )

    def list_policies(self, version_id: str | None = None) -> list[PolicyDocument]:
        return self._index.list_policies(version_id)

    def get_policy(
        self, policy_id: str, version_id: str | None = None
    ) -> PolicyDocument:
        return self._index.get_policy(policy_id, version_id)

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
