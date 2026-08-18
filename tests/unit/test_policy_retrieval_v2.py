from __future__ import annotations

import sqlite3
from dataclasses import replace
from pathlib import Path

from langchain_core.embeddings import Embeddings

from archcompass.adapters.retrieval import SQLitePolicyIndex
from archcompass.application.policy_retrieval import DensePolicyRetriever
from archcompass.application.retrieval_evaluation import (
    RetrievalExample,
    choose_smallest_passing_k,
    evaluate_retrieval,
)
from archcompass.domain import (
    ArchitectureCase,
    Candidate,
    Participant,
    Policy,
    PolicyScope,
    PolicyStrength,
    RetrievalProvenance,
)
from archcompass.ports.policy_retrieval import PolicySelection, RetrievedPolicySet


class TinyEmbeddings(Embeddings):
    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [self._vector(text) for text in texts]

    def embed_query(self, text: str) -> list[float]:
        return self._vector(text)

    @staticmethod
    def _vector(text: str) -> list[float]:
        lowered = text.casefold()
        return [
            float(lowered.count("interface")),
            float(lowered.count("duplicate")),
            1.0,
        ]


def _policy(
    policy_id: str,
    body: str,
    *,
    scope: PolicyScope = PolicyScope.GENERAL,
    strength: PolicyStrength = PolicyStrength.GUIDANCE,
    applies_to: str | None = None,
) -> Policy:
    return Policy(
        id=policy_id,
        title=policy_id,
        body=body,
        scope=scope,
        strength=strength,
        content_hash=f"hash-{policy_id}",
        applies_to=applies_to,
    )


def test_sqlite_dense_retriever_records_deterministic_provenance(tmp_path: Path) -> None:
    database = tmp_path / "vectors.sqlite3"
    index = SQLitePolicyIndex(
        lambda: sqlite3.connect(database),
        TinyEmbeddings(),
        embedding_identity="tiny:v1",
        dimensions=3,
    )
    retriever = DensePolicyRetriever(index, top_k=8)
    corpus = (
        _policy("interfaces", "Keep an interface general."),
        _policy("duplication", "Avoid duplicated knowledge."),
        _policy(
            "repository-rule",
            "This repository requires an explicit owner.",
            scope=PolicyScope.REPOSITORY,
            applies_to="repo-1",
        ),
    )
    case = ArchitectureCase.create("Remove needless interfaces")
    case = replace(
        case,
        policy_context=case.policy_context.__class__(repository="repo-1"),
    )
    candidate = Candidate.identified(
        pattern="sole_implementation",
        summary="One interface has one implementation",
        participants=(Participant("Port", "interface"),),
    )

    first = retriever.retrieve(candidate, case, corpus)
    second = retriever.retrieve(candidate, case, corpus)

    assert first == second
    assert first.policies[0].id == "repository-rule"
    assert first.selections[0].provenance[0] == (
        "selection_reason",
        "mandatory_or_scoped",
    )
    assert first.provenance.model_identity == "tiny:v1"
    assert first.provenance.selected_policy_ids == tuple(
        policy.id for policy in first.policies
    )


def test_retrieval_gate_is_provider_independent() -> None:
    result = evaluate_retrieval(
        (
            RetrievalExample("a", frozenset({"p1"}), ("p1",), frozenset({"p1"})),
            RetrievalExample("b", frozenset({"p2"}), ("p2",)),
        )
    )
    assert result.passed


def test_top_k_is_selected_mechanically_from_the_gate() -> None:
    def examples(top_k: int) -> tuple[RetrievalExample, ...]:
        selected = ("p1",) if top_k >= 12 else ()
        return (RetrievalExample("pattern", frozenset({"p1"}), selected),)

    top_k, result = choose_smallest_passing_k(examples)

    assert top_k == 12
    assert result.passed


def test_retrieval_result_accepts_strategy_opaque_metadata() -> None:
    policy = _policy("selected", "Selected by a future non-vector strategy.")
    provenance = RetrievalProvenance(
        candidate_id=Candidate.identified(
            pattern="future",
            summary="Future candidate",
            participants=(Participant("Future", "subject"),),
        ).id,
        retriever="future-symbolic-retriever",
        version="7",
        corpus_fingerprint="corpus-hash",
        selected_policy_ids=(policy.id,),
        metadata=(("opaque-explanation", "chosen by rule R7"),),
    )
    result = RetrievedPolicySet(
        candidate_id=str(provenance.candidate_id),
        selections=(
            PolicySelection(policy, (("uninterpreted", "implementation value"),)),
        ),
        provenance=provenance,
    )

    assert result.policies == (policy,)
    assert result.provenance.retriever == "future-symbolic-retriever"
