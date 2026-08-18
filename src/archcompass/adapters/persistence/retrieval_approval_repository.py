"""Durable release-gate approvals for production retriever identities."""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Callable
from dataclasses import asdict

from archcompass.application.retrieval_evaluation import RetrievalEvaluation
from archcompass.domain.errors import ConfigurationError


class SQLiteRetrievalApprovalRepository:
    def __init__(self, connect: Callable[[], sqlite3.Connection]) -> None:
        self._connect = connect
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS policy_retriever_approvals (
                    embedding_identity TEXT NOT NULL,
                    retriever TEXT NOT NULL,
                    version TEXT NOT NULL,
                    top_k INTEGER NOT NULL,
                    evaluation_json TEXT NOT NULL,
                    PRIMARY KEY(embedding_identity, retriever, version)
                )
                """
            )

    def approve(
        self,
        *,
        embedding_identity: str,
        retriever: str,
        version: str,
        top_k: int,
        evaluation: RetrievalEvaluation,
    ) -> None:
        if not evaluation.passed:
            raise ValueError("a failing retrieval evaluation cannot be approved")
        with self._connect() as connection:
            connection.execute(
                "INSERT INTO policy_retriever_approvals(embedding_identity, retriever, "
                "version, top_k, evaluation_json) VALUES (?, ?, ?, ?, ?) "
                "ON CONFLICT(embedding_identity, retriever, version) DO UPDATE SET "
                "top_k=excluded.top_k, evaluation_json=excluded.evaluation_json",
                (
                    embedding_identity,
                    retriever,
                    version,
                    top_k,
                    json.dumps(asdict(evaluation), separators=(",", ":")),
                ),
            )

    def required_top_k(
        self, embedding_identity: str, *, retriever: str, version: str
    ) -> int:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT top_k FROM policy_retriever_approvals "
                "WHERE embedding_identity = ? AND retriever = ? AND version = ?",
                (embedding_identity, retriever, version),
            ).fetchone()
        if row is None:
            raise ConfigurationError(
                f"Retriever {retriever}:{version} with embeddings {embedding_identity} "
                "has no passing retrieval evaluation. Evaluate K=8,12,16,20 and record "
                "the smallest passing value before reviews can use it."
            )
        return int(row[0])
