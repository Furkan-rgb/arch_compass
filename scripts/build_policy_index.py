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
import sys
from pathlib import Path

from archcompass.configuration import EmbeddingModelConfig
from archcompass.policies.adapters.bundled import bundled_corpus
from archcompass.policies.adapters.embeddings import embedding_config_from_environment
from archcompass.policies.adapters.prebuilt import PREBUILT_INDEX, build, coverage
from archcompass.reasoning.adapters.factory import embedding_identity

ROOT = Path(__file__).resolve().parents[1]


def _describe(path: Path) -> str:
    """The output path as a reader would name it: relative here, absolute anywhere else."""

    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


def check(path: Path, config: EmbeddingModelConfig) -> bool:
    """Whether the committed file still answers for the corpus beside it."""

    corpus = bundled_corpus()
    found = coverage(path, corpus, config)
    if found.complete:
        assert found.manifest is not None
        print(
            f"{_describe(path)} covers {len(corpus)} policies in "
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

    # Only a provider that names a credential variable is asked for one. A self-hosted
    # embedder names none, and reading `os.environ[""]` for it refused every local build
    # with the sentence "which needs None set" — which is how the whole Ollama path came to
    # have no way of producing the index the retriever then refuses to run without.
    if config.api_key_env and not os.environ.get(config.api_key_env, "").strip():
        print(
            f"Building the index embeds the whole corpus, which needs {config.api_key_env} "
            "set. Checking an already-built one does not: pass --check.",
            file=sys.stderr,
        )
        return 1
    chunks = build(arguments.output, bundled_corpus(), config)
    print(f"wrote {_describe(arguments.output)} — {chunks} chunks")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
