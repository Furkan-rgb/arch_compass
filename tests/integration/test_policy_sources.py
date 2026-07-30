from __future__ import annotations

from pathlib import Path

import pytest

from archcompass.adapters.persistence.database import SQLiteDatabase
from archcompass.adapters.persistence.policy_source_repository import (
    SQLitePolicySourceRepository,
)
from archcompass.adapters.retrieval.policy_markdown import (
    MarkdownPolicySourceInspector,
)
from archcompass.application.policies import PolicyService
from archcompass.bootstrap import BUNDLED_POLICY_SOURCE
from archcompass.domain.base import stable_id
from archcompass.domain.errors import PolicyFormatError
from archcompass.domain.policy import PolicyScope


def _write_policy(
    path: Path,
    *,
    policy_id: str,
    scope: str,
    applies_to: str | None = None,
) -> None:
    template = (BUNDLED_POLICY_SOURCE / "contain-dependencies.md").read_text(
        encoding="utf-8"
    )
    scope_metadata = f"scope: {scope}"
    if applies_to is not None:
        scope_metadata += f"\napplies_to: {applies_to}"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        template.replace(
            "id: contain-dependencies",
            f"id: {policy_id}",
            1,
        ).replace("scope: general", scope_metadata, 1),
        encoding="utf-8",
    )


def _service(database: SQLiteDatabase) -> PolicyService:
    return PolicyService(
        source_repository=SQLitePolicySourceRepository(database),
        source_inspector=MarkdownPolicySourceInspector(),
        bundled_sources=(BUNDLED_POLICY_SOURCE,),
    )


def test_policy_sources_are_persistent_and_repository_sources_are_local(
    tmp_path: Path,
) -> None:
    """Registration is what persists; the documents are read from disk each time.

    There is no index to build and no version to pin a lookup to. What the workspace
    remembers is which directories to read, so a policy edited after registration is the
    policy the next review sees.
    """

    database = SQLiteDatabase(tmp_path / "workspace" / "archcompass.db")
    database.initialize()
    workspace_source = tmp_path / "workspace-policies"
    _write_policy(
        workspace_source / "organisation.md",
        policy_id="organisation-policy",
        scope="organisation",
        applies_to="example-organisation",
    )
    service = _service(database)

    service.add_source(workspace_source)

    registrations = SQLitePolicySourceRepository(database).list()
    assert [item.canonical_path for item in registrations] == [
        str(workspace_source.resolve())
    ]
    organisation_policy = service.get("organisation-policy")
    assert organisation_policy.scope == PolicyScope.ORGANISATION
    assert organisation_policy.applies_to == "example-organisation"

    repository = tmp_path / "repository"
    _write_policy(
        repository / ".archcompass" / "policies" / "repository.md",
        policy_id="repository-policy",
        scope="repository",
    )
    second_service = _service(SQLiteDatabase(database.path))

    # A repository's own policies are in reach only for a caller that names the repository,
    # which is how they stay local to the review that is about it.
    repository_policy = second_service.get(
        "repository-policy", repository_root=repository
    )
    assert repository_policy.scope == PolicyScope.REPOSITORY
    assert repository_policy.applies_to == stable_id(
        "repo",
        str(repository.resolve()),
    )
    assert {policy.id for policy in second_service.catalog()}.isdisjoint(
        {"repository-policy"}
    )
    assert [item.canonical_path for item in second_service.list_sources()] == [
        str(workspace_source.resolve())
    ]
    assert second_service.remove_source(workspace_source)
    assert _service(SQLiteDatabase(database.path)).list_sources() == []


@pytest.mark.parametrize("scope", ["repository", "accepted_adr"])
def test_repository_scoped_documents_cannot_be_registered_globally(
    tmp_path: Path,
    scope: str,
) -> None:
    database = SQLiteDatabase(tmp_path / "workspace" / "archcompass.db")
    database.initialize()
    source = tmp_path / "global-policies"
    _write_policy(
        source / f"{scope}.md",
        policy_id=f"{scope}-policy",
        scope=scope,
        applies_to="repo_explicit",
    )
    service = _service(database)

    with pytest.raises(PolicyFormatError, match="cannot be registered globally"):
        service.add_source(source)

    assert service.list_sources() == []
