"""The policy index this package ships, and the two questions worth asking of it.

Indexing the corpus is the one part of a review that costs hundreds of provider requests,
and it produces the same vectors every time: the policies are shipped, so their embeddings
could have been. Building them once and putting the result in the package turns a cold
workspace's first review from minutes of metered waiting into no requests at all.

The saving is only real if the file is right, and it is wrong in exactly two ways. It can
hold vectors from a different embedding model, which are not comparable with the ones a
search will produce. And it can be missing chunks, because a policy was edited after the
index was built. Both are silent by nature — a mismatched namespace simply finds nothing,
and a missing chunk simply gets embedded — so both are asked about here, out loud, by the
CI check that guards the file and by the hosted deployment that depends on it.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from archcompass.configuration import EmbeddingModelConfig
from archcompass.domain import Policy
from archcompass.domain.errors import ConfigurationError
from archcompass.policies.adapters.sqlite_index import desired_chunks, namespace_for
from archcompass.reasoning.adapters.factory import embedding_identity

#: Where the built index lives once `scripts/build_policy_index.py` has written it. Inside
#: the package rather than beside it, so that it is installed with the code and found at the
#: same path in a container, a wheel and a checkout. Absent is a supported state: without it
#: every workspace indexes for itself, which is what happened before this existed.
PREBUILT_INDEX: Final = Path(__file__).resolve().parents[1] / "prebuilt" / "policy-index.sqlite3"

#: One row, saying what the file is. The chunk rows carry their own `embedding_identity`
#: too, but only per row and only for rows that are there — which cannot answer "is this the
#: right model" for a file whose rows are all under some other namespace. The manifest can,
#: and it is the difference between a startup error naming the mismatch and a deployment
#: that quietly re-embeds everything.
MANIFEST_TABLE: Final = "policy_index_manifest"

MANIFEST_SCHEMA: Final = f"""
CREATE TABLE IF NOT EXISTS {MANIFEST_TABLE} (
    embedding_identity TEXT NOT NULL,
    dimensions INTEGER NOT NULL,
    chunk_count INTEGER NOT NULL
)
"""


@dataclass(frozen=True, slots=True)
class PrebuiltManifest:
    """What a built index says it is."""

    embedding_identity: str
    dimensions: int
    chunk_count: int


@dataclass(frozen=True, slots=True)
class PrebuiltCoverage:
    """Whether a built index can answer for this corpus, and if not, what is wrong.

    Both lists rather than a boolean, because the two failures have different cures and a
    caller that could only say "no" would leave whoever reads the message guessing which.
    Missing chunks mean the index is behind the corpus: rebuild it. Extra chunks mean it was
    built from a different corpus altogether, which is not a rebuild but a question about
    which policies this workspace is meant to be using.
    """

    manifest: PrebuiltManifest | None
    missing: tuple[str, ...]
    extra: tuple[str, ...]

    @property
    def complete(self) -> bool:
        return self.manifest is not None and not self.missing and not self.extra

    def explain(self, *, path: Path, identity: str) -> str:
        """Why this index cannot be used, phrased for whoever has to fix it."""

        if not path.is_file():
            return f"There is no prebuilt policy index at {path}."
        if self.manifest is None:
            return f"{path} holds no index manifest, so there is nothing to trust in it."
        if self.manifest.embedding_identity != identity:
            return (
                f"{path} was built for {self.manifest.embedding_identity}, but this "
                f"workspace embeds with {identity}. Vectors from two models are not "
                "comparable, so the shipped index cannot answer for this one."
            )
        parts: list[str] = []
        if self.missing:
            parts.append(
                f"{len(self.missing)} chunk(s) the corpus needs are not in it, starting "
                f"with {', '.join(self.missing[:3])}"
            )
        if self.extra:
            parts.append(
                f"{len(self.extra)} chunk(s) in it are not in the corpus, starting with "
                f"{', '.join(self.extra[:3])}"
            )
        return f"{path} does not match the policy corpus: {'; '.join(parts)}."


def read_manifest(path: Path) -> PrebuiltManifest | None:
    """What the file says about itself, or nothing if it is not one of ours."""

    if not path.is_file():
        return None
    connection = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    try:
        row = connection.execute(
            f"SELECT embedding_identity, dimensions, chunk_count FROM {MANIFEST_TABLE}"
        ).fetchone()
    except sqlite3.DatabaseError:
        return None
    finally:
        connection.close()
    if row is None:
        return None
    return PrebuiltManifest(str(row[0]), int(row[1]), int(row[2]))


def coverage(
    path: Path, corpus: tuple[Policy, ...], config: EmbeddingModelConfig
) -> PrebuiltCoverage:
    """Compare what the file holds against what this corpus and model would need.

    Offline, and deliberately so: it hashes policy text and reads a SQLite file, and asks
    nothing of a provider. That is what lets the check run in CI on a machine with no API
    key, which is the only place it is any use — a check that needed a key would be skipped
    exactly where the file goes stale.
    """

    manifest = read_manifest(path)
    identity = embedding_identity(config)
    if manifest is None or manifest.embedding_identity != identity:
        return PrebuiltCoverage(manifest, (), ())
    desired = desired_chunks(corpus, identity)
    stored = _stored_digests(path, namespace_for(identity))
    missing = tuple(
        sorted(chunk_id for chunk_id, entry in desired.items() if stored.get(chunk_id) != entry[1])
    )
    extra = tuple(sorted(set(stored) - set(desired)))
    return PrebuiltCoverage(manifest, missing, extra)


def verify(path: Path, corpus: tuple[Policy, ...], config: EmbeddingModelConfig) -> None:
    """Refuse anything but a complete, matching index, naming what is wrong.

    For the caller that has decided it needs one — the hosted deployment, whose whole reason
    for shipping the file is that it cannot afford to index per visitor. A deployment that
    silently fell back would look fine until somebody timed a review.
    """

    found = coverage(path, corpus, config)
    if not found.complete:
        raise ConfigurationError(
            found.explain(path=path, identity=embedding_identity(config))
            + " Rebuild it with `make policy-index`."
        )


def usable(corpus: tuple[Policy, ...], config: EmbeddingModelConfig) -> Path | None:
    """The shipped index if it can answer for this corpus, otherwise nothing.

    The quiet counterpart to `verify`, for a local run: someone reviewing against their own
    policies has no use for the shipped vectors and no reason to be told about them, so the
    answer is simply that there is no index to attach and the workspace builds its own.
    """

    if not PREBUILT_INDEX.is_file():
        return None
    return PREBUILT_INDEX if coverage(PREBUILT_INDEX, corpus, config).complete else None


def _stored_digests(path: Path, namespace: str) -> dict[str, str]:
    connection = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    try:
        return {
            str(row[0]): str(row[1])
            for row in connection.execute(
                "SELECT chunk_id, content_hash FROM policy_embedding_chunks WHERE namespace = ?",
                (namespace,),
            )
        }
    except sqlite3.DatabaseError:
        return {}
    finally:
        connection.close()
