"""The policy corpus this evaluation measures against, read the way a review reads it.

Deliberately the shipped Markdown rather than a copy: a retrieval score against a corpus
written for the evaluation would say nothing about the product. `load_policy_sources` is
the same parser the workspace uses, so a policy that has drifted out of format fails here
before it reaches a number.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from archcompass.domain import Policy, PolicyScope, PolicyStrength
from archcompass.policies.adapters.markdown import load_policy_sources

#: The bundled general corpus — what every workspace gets before it registers a source.
SHIPPED_POLICIES = Path("src/archcompass/policies/general")

#: Scoped and required policies authored for this evaluation alone. The shipped corpus is
#: general guidance from end to end, so the retriever's other arm — the mandatory merge
#: that must include an applicable organisation, repository or required policy whatever the
#: embeddings say — has nothing in it to exercise. These four are that fixture, written in
#: the real format and read by the real parser.
SCOPED_POLICIES = Path("evaluation/dataset/scoped-policies")


def _as_domain(root: Path, sources: list[Path]) -> tuple[Policy, ...]:
    documents = load_policy_sources([root / source for source in sources])
    return tuple(
        Policy(
            id=item.id,
            title=item.title,
            body=item.body,
            scope=PolicyScope(item.scope.value),
            strength=PolicyStrength(item.strength.value),
            content_hash=item.content_hash,
            tags=tuple(item.tags),
            applies_to=item.applies_to,
            source=item.source_path,
        )
        for item in sorted(documents, key=lambda item: item.id)
    )


def shipped_corpus(root: Path) -> tuple[Policy, ...]:
    """The general policies a review is judged against, ordered by id."""

    return _as_domain(root, [SHIPPED_POLICIES])


def scoped_policies(root: Path) -> tuple[Policy, ...]:
    """The scope fixture on its own, for reporting what the mandatory arm is being shown."""

    return _as_domain(root, [SCOPED_POLICIES])


def evaluation_corpus(root: Path) -> tuple[Policy, ...]:
    """The shipped corpus plus the scope fixture, which is what the gate section indexes."""

    return _as_domain(root, [SHIPPED_POLICIES, SCOPED_POLICIES])


@dataclass(frozen=True, slots=True)
class ChunkReport:
    """What the index will actually hold, before anything is embedded.

    `longest_estimated_tokens` is a word count scaled by 1.3, not a tokenizer. It is here
    to answer one question — whether any chunk is near the 2,048-token context the local
    runner gives EmbeddingGemma — and a rough answer to that is enough, because a chunk at
    a third of the limit is safe under any tokenizer and one over it would be obvious.
    """

    policies: int
    chunks: int
    chunks_per_policy: float
    longest_characters: int
    longest_estimated_tokens: int
    longest_chunk_policy: str


def chunk_report(corpus: tuple[Policy, ...], chunker: object) -> ChunkReport:
    from collections.abc import Callable
    from typing import cast

    split = cast("Callable[[Policy], tuple[str, ...]]", chunker)
    everything = [(policy.id, text) for policy in corpus for text in split(policy)]
    if not everything:
        raise ValueError("the corpus produced no chunks")
    policy_id, longest = max(everything, key=lambda item: len(item[1]))
    return ChunkReport(
        policies=len(corpus),
        chunks=len(everything),
        chunks_per_policy=len(everything) / len(corpus),
        longest_characters=len(longest),
        longest_estimated_tokens=int(len(longest.split()) * 1.3),
        longest_chunk_policy=policy_id,
    )
