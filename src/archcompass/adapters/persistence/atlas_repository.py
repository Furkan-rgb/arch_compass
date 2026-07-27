"""SQLite repository for immutable atlas versions."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from archcompass.adapters.persistence.database import SQLiteDatabase
from archcompass.domain.atlas import (
    Atlas,
    AtlasEdge,
    AtlasNode,
    AtlasVersion,
    MetricProfile,
    ModuleFacts,
    ObscuritySignal,
)
from archcompass.domain.errors import AtlasNotFoundError
from archcompass.domain.workspace import RepositorySummary


class SQLiteAtlasRepository:
    def __init__(self, database: SQLiteDatabase) -> None:
        self._database = database

    def save(self, atlas: Atlas) -> None:
        version = atlas.version
        with self._database.connect() as connection:
            connection.execute(
                """
                INSERT INTO atlas_versions(
                    version_id, repository_identity, root_path, git_commit_sha,
                    content_fingerprint, parser_version, analysis_config_hash, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    version.version_id,
                    version.repository_identity,
                    version.root_path,
                    version.git_commit_sha,
                    version.content_fingerprint,
                    version.parser_version,
                    version.analysis_config_hash,
                    version.created_at.isoformat(),
                ),
            )
            connection.executemany(
                "INSERT INTO atlas_nodes(version_id, atlas_id, node_json) VALUES (?, ?, ?)",
                [
                    (version.version_id, node.atlas_id, node.model_dump_json())
                    for node in atlas.nodes
                ],
            )
            connection.executemany(
                "INSERT INTO atlas_edges(version_id, edge_id, edge_json) VALUES (?, ?, ?)",
                [
                    (version.version_id, edge.edge_id, edge.model_dump_json())
                    for edge in atlas.edges
                ],
            )
            connection.executemany(
                "INSERT INTO atlas_metrics(version_id, node_id, metrics_json) VALUES (?, ?, ?)",
                [
                    (version.version_id, profile.node_id, profile.model_dump_json())
                    for profile in atlas.metrics
                ],
            )
            connection.executemany(
                "INSERT INTO atlas_signals(version_id, ordinal, signal_json) VALUES (?, ?, ?)",
                [
                    (version.version_id, ordinal, signal.model_dump_json())
                    for ordinal, signal in enumerate(atlas.signals)
                ],
            )
            connection.executemany(
                """
                INSERT INTO atlas_module_facts(version_id, node_id, facts_json)
                VALUES (?, ?, ?)
                """,
                [
                    (version.version_id, facts.node_id, facts.model_dump_json())
                    for facts in atlas.module_facts
                ],
            )
            connection.commit()

    def get(self, version_id: str) -> Atlas:
        with self._database.connect() as connection:
            version_row = connection.execute(
                "SELECT * FROM atlas_versions WHERE version_id = ?", (version_id,)
            ).fetchone()
            if version_row is None:
                raise AtlasNotFoundError(f"Atlas version {version_id} was not found")
            node_rows = connection.execute(
                "SELECT node_json FROM atlas_nodes WHERE version_id = ? ORDER BY atlas_id",
                (version_id,),
            ).fetchall()
            edge_rows = connection.execute(
                "SELECT edge_json FROM atlas_edges WHERE version_id = ? ORDER BY edge_id",
                (version_id,),
            ).fetchall()
            metric_rows = connection.execute(
                "SELECT metrics_json FROM atlas_metrics WHERE version_id = ? ORDER BY node_id",
                (version_id,),
            ).fetchall()
            signal_rows = connection.execute(
                "SELECT signal_json FROM atlas_signals WHERE version_id = ? ORDER BY ordinal",
                (version_id,),
            ).fetchall()
            facts_rows = connection.execute(
                """
                SELECT facts_json FROM atlas_module_facts
                WHERE version_id = ? ORDER BY node_id
                """,
                (version_id,),
            ).fetchall()
        version = AtlasVersion.model_validate(dict(version_row))
        return Atlas(
            version=version,
            nodes=[AtlasNode.model_validate_json(row["node_json"]) for row in node_rows],
            edges=[AtlasEdge.model_validate_json(row["edge_json"]) for row in edge_rows],
            metrics=[
                MetricProfile.model_validate_json(row["metrics_json"]) for row in metric_rows
            ],
            signals=[
                ObscuritySignal.model_validate_json(row["signal_json"]) for row in signal_rows
            ],
            module_facts=[
                ModuleFacts.model_validate_json(row["facts_json"]) for row in facts_rows
            ],
        )

    def latest_for_path(self, root: Path) -> Atlas | None:
        canonical = str(root.resolve())
        with self._database.connect() as connection:
            row = connection.execute(
                """
                SELECT version_id FROM atlas_versions
                WHERE root_path = ? ORDER BY created_at DESC, rowid DESC LIMIT 1
                """,
                (canonical,),
            ).fetchone()
        return None if row is None else self.get(str(row["version_id"]))

    def list_versions(self, *, limit: int = 100) -> list[RepositorySummary]:
        with self._database.connect() as connection:
            rows = connection.execute(
                """
                SELECT
                    v.*,
                    (SELECT COUNT(*) FROM atlas_nodes n
                     WHERE n.version_id = v.version_id) AS node_count,
                    (SELECT COUNT(*) FROM atlas_edges e
                     WHERE e.version_id = v.version_id) AS edge_count,
                    (SELECT COUNT(*) FROM atlas_signals s
                     WHERE s.version_id = v.version_id) AS signal_count
                FROM atlas_versions v
                ORDER BY v.created_at DESC, v.rowid DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [
            RepositorySummary(
                version_id=str(row["version_id"]),
                repository_identity=str(row["repository_identity"]),
                root_path=str(row["root_path"]),
                git_commit_sha=(
                    str(row["git_commit_sha"])
                    if row["git_commit_sha"] is not None
                    else None
                ),
                created_at=datetime.fromisoformat(str(row["created_at"])),
                node_count=int(row["node_count"]),
                edge_count=int(row["edge_count"]),
                signal_count=int(row["signal_count"]),
            )
            for row in rows
        ]
