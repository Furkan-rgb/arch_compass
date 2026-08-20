"""Build, or check, the policy index this package ships.

The corpus is shipped, so its embeddings can be too. Building them here and committing the
result means a cold workspace embeds nothing at all — which on a metered free tier is the
difference between a review that starts now and one that spends five minutes indexing
vectors identical to everybody else's.

Two modes, because they run in two places. Building needs the embedding provider and an API
key, so it happens on a machine that has one and the result is committed:

    uv run python scripts/build_policy_index.py

Checking needs neither. It hashes the corpus and reads the file, so it runs in CI on every
push and fails the moment a policy is edited without the index being rebuilt:

    uv run python scripts/build_policy_index.py --check

That asymmetry is the point. A check that needed a key would be skipped in exactly the place
the file goes stale, and a stale index is worse than no index: it does not announce itself,
it just quietly stops covering the policy somebody changed.
"""

from __future__ import annotations

import argparse
import os
import sqlite3
import sys
from pathlib import Path

import sqlite_vec

from archcompass.configuration import EmbeddingModelConfig
from archcompass.policies.adapters.bundled import bundled_corpus
from archcompass.policies.adapters.embeddings import embedding_config_from_environment
from archcompass.policies.adapters.prebuilt import (
    MANIFEST_SCHEMA,
    MANIFEST_TABLE,
    PREBUILT_INDEX,
    coverage,
)
from archcompass.policies.adapters.sqlite_index import SQLitePolicyIndex, desired_chunks
from archcompass.reasoning.adapters.factory import build_embeddings, embedding_identity

ROOT = Path(__file__).resolve().parents[1]

#: Read-only once written. Belt to the braces of never writing to the attached schema: an
#: edit that forgot is refused by SQLite rather than quietly mutating a file that is supposed
#: to be a build artefact, and the container's own user could not write it anyway.
_READ_ONLY = 0o444


def build(path: Path, config: EmbeddingModelConfig) -> int:
    """Embed the whole shipped corpus into a fresh file, and say what it is.

    Written by the same `SQLitePolicyIndex` that reads it at run time rather than by SQL
    written here, so there is exactly one account of what a stored chunk looks like. The
    index is pointed at this file as its own workspace database and told there is no shipped
    index to consult — which is true, since this is the one being made.
    """

    corpus = bundled_corpus()
    identity = embedding_identity(config)
    path.parent.mkdir(parents=True, exist_ok=True)
    # From scratch every time. Refreshing in place would leave the chunks of a policy that
    # has since been deleted sitting in the file, and `coverage` would rightly refuse it.
    path.unlink(missing_ok=True)

    def connect() -> sqlite3.Connection:
        connection = sqlite3.connect(path)
        # Rollback journalling rather than WAL, which is what the workspace database uses.
        # A WAL database needs to write beside itself to be opened at all, and this one is
        # opened from an installed package directory that nothing at run time may write to.
        connection.execute("PRAGMA journal_mode = DELETE")
        return connection

    index = SQLitePolicyIndex(
        connect,
        build_embeddings(config),
        embedding_identity=identity,
        dimensions=config.dimensions,
    )
    index.synchronize(corpus)

    chunks = len(desired_chunks(corpus, identity))
    with sqlite3.connect(path) as connection:
        connection.execute(MANIFEST_SCHEMA)
        connection.execute(f"DELETE FROM {MANIFEST_TABLE}")
        connection.execute(
            f"INSERT INTO {MANIFEST_TABLE}(embedding_identity, dimensions, chunk_count) "
            "VALUES (?, ?, ?)",
            (identity, config.dimensions, chunks),
        )
    with sqlite3.connect(path) as connection:
        connection.enable_load_extension(True)
        sqlite_vec.load(connection)
        connection.enable_load_extension(False)
        connection.execute("VACUUM")
    path.chmod(_READ_ONLY)
    return chunks


def check(path: Path, config: EmbeddingModelConfig) -> bool:
    """Whether the committed file still answers for the corpus beside it."""

    corpus = bundled_corpus()
    found = coverage(path, corpus, config)
    if found.complete:
        assert found.manifest is not None
        print(
            f"{path.relative_to(ROOT)} covers {len(corpus)} policies in "
            f"{found.manifest.chunk_count} chunks for {found.manifest.embedding_identity}"
        )
        return True
    print(found.explain(path=path, identity=embedding_identity(config)), file=sys.stderr)
    return False


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="verify the committed index without embedding anything",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=PREBUILT_INDEX,
        help="where the index lives (default: the packaged one)",
    )
    arguments = parser.parse_args()
    config = embedding_config_from_environment()

    if arguments.check:
        return 0 if check(arguments.output, config) else 1

    if not os.environ.get(config.api_key_env or "", "").strip():
        print(
            f"Building the index embeds the whole corpus, which needs {config.api_key_env} "
            "set. Checking an already-built one does not: pass --check.",
            file=sys.stderr,
        )
        return 1
    chunks = build(arguments.output, config)
    print(f"wrote {arguments.output.relative_to(ROOT)} — {chunks} chunks")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
