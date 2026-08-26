"""The execution database stays bounded without becoming product history."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import cast

from langgraph.checkpoint.sqlite import SqliteSaver

from archcompass.bootstrap import (
    _CHECKPOINT_MAX_BYTES,
    _CHECKPOINT_WAL_RETAIN_BYTES,
    WORKSPACE_STATE_DIRECTORY,
    Runtime,
    build_runtime,
)


def _checkpoint_connection(runtime: Runtime) -> sqlite3.Connection:
    saver = cast(SqliteSaver, runtime.review_workflow_service._graph.checkpointer)
    return saver.conn


def _replace_with_legacy_checkpoints(workspace: Path, rows: tuple[tuple[str, int], ...]) -> Path:
    checkpoint_path = workspace / WORKSPACE_STATE_DIRECTORY / "review-checkpoints.db"
    for suffix in ("", "-wal", "-shm"):
        Path(f"{checkpoint_path}{suffix}").unlink(missing_ok=True)

    connection = sqlite3.connect(checkpoint_path)
    saver = SqliteSaver(connection)
    saver.setup()
    for thread_id, size in rows:
        connection.execute(
            "INSERT INTO checkpoints(thread_id, checkpoint_ns, checkpoint_id, type, "
            "checkpoint, metadata) VALUES (?, '', ?, 'bytes', zeroblob(?), x'')",
            (thread_id, f"checkpoint-{thread_id}", size),
        )
    connection.commit()
    connection.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchall()
    assert connection.execute("PRAGMA auto_vacuum").fetchone()[0] == 0
    connection.close()
    return checkpoint_path


def test_startup_discards_stale_threads_before_compacting(tmp_path: Path) -> None:
    """A leaked database is reduced before VACUUM copies it into a second huge WAL."""

    first = build_runtime(tmp_path)
    running = first.review_workflow_service._begin("repo", "branch", "running-case")
    waiting = first.review_workflow_service._begin("repo", "branch", "waiting-case")
    with first.database.transaction() as connection:
        connection.execute(
            "UPDATE review_executions SET status = 'awaiting_answers' WHERE thread_id = ?",
            (waiting,),
        )
    _checkpoint_connection(first).close()

    checkpoint_path = _replace_with_legacy_checkpoints(
        tmp_path,
        (
            (running, 16 * 1024 * 1024),
            (waiting, 1024 * 1024),
            ("orphaned-thread", 16 * 1024 * 1024),
        ),
    )

    rebuilt = build_runtime(tmp_path)

    with sqlite3.connect(checkpoint_path) as connection:
        threads = {
            str(row[0]) for row in connection.execute("SELECT DISTINCT thread_id FROM checkpoints")
        }
        assert threads == {waiting}
        assert connection.execute("PRAGMA auto_vacuum").fetchone()[0] == 2
    assert checkpoint_path.stat().st_size < 4 * 1024 * 1024
    assert rebuilt.review_workflow_service.run_state(running).status == "failed"


def test_checkpoint_database_has_a_hard_page_ceiling(tmp_path: Path) -> None:
    runtime = build_runtime(tmp_path)
    connection = _checkpoint_connection(runtime)
    page_size = int(connection.execute("PRAGMA page_size").fetchone()[0])

    assert (
        int(connection.execute("PRAGMA max_page_count").fetchone()[0]) * page_size
        <= _CHECKPOINT_MAX_BYTES
    )
    assert (
        connection.execute("PRAGMA journal_size_limit").fetchone()[0]
        == _CHECKPOINT_WAL_RETAIN_BYTES
    )
