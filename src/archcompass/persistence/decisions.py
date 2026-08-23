"""Append-only human dispositions over findings, keyed by branch and candidate."""

from __future__ import annotations

from archcompass.domain import CandidateId, StandingDecision
from archcompass.persistence.sqlite.codecs import DataclassRecordCodec
from archcompass.persistence.sqlite.database import Transaction


class SQLiteCoreStandingDecisionRepository:
    """Append-only human decisions keyed by branch and stable candidate identity."""

    def __init__(self, transaction: Transaction) -> None:
        self._transaction = transaction
        self._codec = DataclassRecordCodec(StandingDecision)
        with self._transaction() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS core_standing_decisions (
                    decision_id TEXT PRIMARY KEY,
                    branch_id TEXT NOT NULL,
                    candidate_id TEXT NOT NULL,
                    decided_at TEXT NOT NULL,
                    review_id TEXT NOT NULL REFERENCES core_review_snapshots(review_id)
                        ON DELETE CASCADE,
                    decision_json TEXT NOT NULL
                )
                """
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS core_decisions_branch_candidate "
                "ON core_standing_decisions(branch_id, candidate_id, decided_at)"
            )

    def record(self, decision: StandingDecision) -> StandingDecision:
        return self.record_many((decision,))[0]

    def record_many(
        self, decisions: tuple[StandingDecision, ...]
    ) -> tuple[StandingDecision, ...]:
        with self._transaction() as connection:
            connection.executemany(
                "INSERT INTO core_standing_decisions(decision_id, branch_id, "
                "candidate_id, decided_at, review_id, decision_json) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                tuple(
                    (
                        decision.id,
                        decision.branch_id,
                        str(decision.candidate_id),
                        decision.decided_at.isoformat(),
                        decision.review_id,
                        self._codec.encode(decision),
                    )
                    for decision in decisions
                ),
            )
        return decisions

    def latest_for_branch(self, branch_id: str) -> tuple[StandingDecision, ...]:
        with self._transaction() as connection:
            rows = connection.execute(
                "SELECT decision_json FROM core_standing_decisions AS decisions "
                "WHERE branch_id = ? AND decided_at = ("
                "SELECT MAX(decided_at) FROM core_standing_decisions "
                "WHERE branch_id = decisions.branch_id "
                "AND candidate_id = decisions.candidate_id) "
                "ORDER BY candidate_id",
                (branch_id,),
            ).fetchall()
        return tuple(
            self._codec.decode(str(row[0]), description="Standing decision")
            for row in rows
        )

    def history(
        self, branch_id: str, candidate_id: CandidateId
    ) -> tuple[StandingDecision, ...]:
        with self._transaction() as connection:
            rows = connection.execute(
                "SELECT decision_json FROM core_standing_decisions "
                "WHERE branch_id = ? AND candidate_id = ? "
                "ORDER BY decided_at, decision_id",
                (branch_id, str(candidate_id)),
            ).fetchall()
        return tuple(
            self._codec.decode(str(row[0]), description="Standing decision history")
            for row in rows
        )
