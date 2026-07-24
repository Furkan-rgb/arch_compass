"""Architecture case use cases."""

from __future__ import annotations

from archcompass.domain.base import utc_now
from archcompass.domain.case import ArchitectureCase, CaseRevision, CaseUpdate
from archcompass.domain.workspace import CaseSummary
from archcompass.ports.repositories import CaseRepository


class CaseService:
    def __init__(self, repository: CaseRepository) -> None:
        self._repository = repository

    def create(self, case: ArchitectureCase, *, actor: str = "user") -> CaseRevision:
        normalized = case.model_copy(update={"revision": 1})
        return self._repository.create(normalized, actor=actor)

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
