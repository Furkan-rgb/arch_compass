"""SQLite persistence for workspace policy-source registrations."""

from __future__ import annotations

from archcompass.adapters.persistence.database import SQLiteDatabase
from archcompass.boundary.policy import PolicySourceRegistration


class SQLitePolicySourceRepository:
    def __init__(self, database: SQLiteDatabase) -> None:
        self._database = database

    def add(self, registration: PolicySourceRegistration) -> PolicySourceRegistration:
        with self._database.connect() as connection:
            connection.execute(
                """
                INSERT INTO policy_source_registrations(canonical_path, registered_at)
                VALUES (?, ?)
                ON CONFLICT(canonical_path) DO NOTHING
                """,
                (
                    registration.canonical_path,
                    registration.registered_at.isoformat(),
                ),
            )
            row = connection.execute(
                """
                SELECT canonical_path, registered_at
                FROM policy_source_registrations
                WHERE canonical_path = ?
                """,
                (registration.canonical_path,),
            ).fetchone()
            connection.commit()
        if row is None:
            raise RuntimeError("Policy-source registration was not persisted")
        return PolicySourceRegistration.model_validate(dict(row))

    def remove(self, canonical_path: str) -> bool:
        with self._database.connect() as connection:
            cursor = connection.execute(
                "DELETE FROM policy_source_registrations WHERE canonical_path = ?",
                (canonical_path,),
            )
            connection.commit()
        return cursor.rowcount > 0

    def list(self) -> list[PolicySourceRegistration]:
        with self._database.connect() as connection:
            rows = connection.execute(
                """
                SELECT canonical_path, registered_at
                FROM policy_source_registrations
                ORDER BY canonical_path
                """
            ).fetchall()
        return [PolicySourceRegistration.model_validate(dict(row)) for row in rows]
