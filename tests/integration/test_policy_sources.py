from __future__ import annotations

from pathlib import Path

from archcompass.adapters.models.deterministic import DeterministicEmbeddingProvider
from archcompass.adapters.persistence.database import SQLiteDatabase
from archcompass.adapters.persistence.policy_source_repository import (
    SQLitePolicySourceRepository,
)
from archcompass.adapters.retrieval.policy_markdown import (
    MarkdownPolicySourceInspector,
)
from archcompass.adapters.retrieval.policy_store import SQLitePolicyStore
from archcompass.application.policies import PolicyService
from archcompass.bootstrap import BUNDLED_POLICY_SOURCE
from archcompass.domain.policy import PolicyScope


def _write_policy(path: Path, *, policy_id: str, scope: str) -> None:
    template = (BUNDLED_POLICY_SOURCE / "contain-dependencies.md").read_text(
        encoding="utf-8"
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        template.replace(
            "id: contain-dependencies",
            f"id: {policy_id}",
            1,
        ).replace("scope: general", f"scope: {scope}", 1),
        encoding="utf-8",
    )


def _service(database: SQLiteDatabase) -> PolicyService:
    return PolicyService(
        index=SQLitePolicyStore(
            database,
            DeterministicEmbeddingProvider(32),
        ),
        source_repository=SQLitePolicySourceRepository(database),
        source_inspector=MarkdownPolicySourceInspector(),
        bundled_sources=(BUNDLED_POLICY_SOURCE,),
    )


def test_policy_sources_are_persistent_and_repository_sources_are_local(
    tmp_path: Path,
) -> None:
    database = SQLiteDatabase(tmp_path / "workspace" / "archcompass.db")
    database.initialize()
    workspace_source = tmp_path / "workspace-policies"
    _write_policy(
        workspace_source / "organisation.md",
        policy_id="organisation-policy",
        scope="organisation",
    )
    service = _service(database)

    first = service.rebuild(sources=[workspace_source])

    registrations = SQLitePolicySourceRepository(database).list()
    assert [item.canonical_path for item in registrations] == [
        str(workspace_source.resolve())
    ]
    organisation_policy = service.get_policy(
        "organisation-policy", first.version_id
    )
    assert organisation_policy.scope == PolicyScope.ORGANISATION

    repository = tmp_path / "repository"
    _write_policy(
        repository / ".archcompass" / "policies" / "repository.md",
        policy_id="repository-policy",
        scope="repository",
    )
    second_service = _service(SQLiteDatabase(database.path))
    second = second_service.rebuild(repository_root=repository)

    assert second_service.get_policy(
        "repository-policy", second.version_id
    ).scope == PolicyScope.REPOSITORY
    assert [item.canonical_path for item in second_service.list_sources()] == [
        str(workspace_source.resolve())
    ]
    assert second_service.remove_source(workspace_source)
    assert _service(SQLiteDatabase(database.path)).list_sources() == []
