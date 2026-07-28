"""Architecture case use cases."""

from __future__ import annotations

from pathlib import Path

from archcompass.domain.base import utc_now
from archcompass.domain.case import (
    ArchitectureCase,
    CaseRevision,
    CaseUpdate,
    RepositoryReference,
)
from archcompass.domain.workspace import CaseSummary
from archcompass.ports.repositories import CaseRepository


def _title_for(root: Path) -> str:
    """A name for a case nobody has named, taken from the repository it is about.

    Derived rather than invented, and that distinction is the whole of why this is allowed.
    A repository's own directory name is a fact about what is being reviewed; a problem
    statement written on the user's behalf would be intent they never stated, which the case
    exists to hold and only they can supply (invariant 23).
    """

    name = root.expanduser().resolve().name or str(root)
    return f"Boundaries in {name}"


class CaseService:
    def __init__(self, repository: CaseRepository) -> None:
        self._repository = repository

    def create(self, case: ArchitectureCase, *, actor: str = "user") -> CaseRevision:
        normalized = case.model_copy(update={"revision": 1})
        return self._repository.create(normalized, actor=actor)

    def start_from_repository(
        self,
        root: Path,
        *,
        actor: str = "user",
    ) -> CaseRevision:
        """A case holding nothing but which repository it is about (master plan §6C.1).

        The entry point for someone who has not written a case and should not have to. The
        review runs on the repository alone, and what it could not weigh comes back as the
        questions it asks — so the case is filled in by answering rather than before
        anything has been seen.

        Empty rather than pre-filled. A placeholder problem statement would be read by the
        judging stage as intent the user never expressed, and a verdict resting on it would
        be resting on this function's prose.
        """

        return self.create(
            ArchitectureCase(
                title=_title_for(root),
                repository=RepositoryReference(root_path=str(root.expanduser().resolve())),
            ),
            actor=actor,
        )

    def show(self, case_id: str, revision: int | None = None) -> CaseRevision:
        return self._repository.get(case_id, revision)

    def update(
        self,
        case_id: str,
        update: CaseUpdate,
        *,
        actor: str = "user",
    ) -> CaseRevision:
        current = self._repository.get(case_id)
        case_data = current.snapshot.model_dump()
        changes = update.model_dump(exclude_unset=True)
        changes["updated_at"] = utc_now()
        case_data.update(changes)
        # Pydantic's model_copy(update=...) deliberately skips validation.
        # Case updates contain nested statements, so reconstruct the aggregate
        # to turn their serialized dictionaries back into domain models before
        # the revision validators inspect them.
        next_case = ArchitectureCase.model_validate(case_data)
        return self._repository.append(
            next_case,
            expected_revision=current.revision,
            event_type="user_update",
            actor=actor,
        )

    def history(self, case_id: str) -> list[CaseRevision]:
        return self._repository.history(case_id)

    def list(self, *, limit: int = 100) -> list[CaseSummary]:
        return self._repository.list(limit=limit)
