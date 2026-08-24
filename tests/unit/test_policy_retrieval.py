from __future__ import annotations

import sqlite3
from dataclasses import replace
from pathlib import Path

from langchain_core.embeddings import Embeddings

from archcompass.domain import (
    ArchitectureCase,
    Candidate,
    Participant,
    Policy,
    PolicyScope,
    PolicyStrength,
    RetrievalProvenance,
)
from archcompass.domain._support import utc_now
from archcompass.domain.case import Answer, AnswerStatus, CaseFacet, Question
from archcompass.policies.adapters import SQLitePolicyIndex
from archcompass.policies.evaluation import (
    RetrievalExample,
    choose_smallest_passing_k,
    evaluate_retrieval,
)
from archcompass.policies.retrieval import DensePolicyRetriever
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
    case = ArchitectureCase.create()
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


class TopicEmbeddings(Embeddings):
    """Two topics that a single vector has to choose between, which is the whole problem.

    A policy is about one of them. A query mixing both lands between the two, which is what
    the real failure looked like: a candidate about duplicated constants whose case had
    answered about payment vendors retrieved neither well.
    """

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [self._vector(text) for text in texts]

    def embed_query(self, text: str) -> list[float]:
        return self._vector(text)

    @staticmethod
    def _vector(text: str) -> list[float]:
        lowered = text.casefold()
        return [float(lowered.count("duplicate")), float(lowered.count("payment")), 0.01]


def _topic_index(tmp_path: Path, corpus: tuple[Policy, ...]) -> SQLitePolicyIndex:
    index = SQLitePolicyIndex(
        lambda: sqlite3.connect(tmp_path / "index.sqlite3"),
        TopicEmbeddings(),
        embedding_identity="topic:v1",
        dimensions=3,
    )
    index.synchronize(corpus)
    return index


def _two_topics_and_filler() -> tuple[Policy, ...]:
    """One policy per topic, and enough neighbours that a top-8 is a real choice."""

    return (
        _policy("about-duplication", "duplicate duplicate duplicate knowledge"),
        _policy("about-payments", "payment payment payment providers"),
        *(_policy(f"unrelated-{index}", "neither topic at all") for index in range(10)),
    )


def _duplicated_constant() -> Candidate:
    return Candidate.identified(
        pattern="duplicated_knowledge",
        summary="A duplicate duplicate duplicate constant is stated in two modules.",
        participants=(Participant("billing.settings.PAGE_SIZE", "module"),),
    )


def _case_about_payments() -> ArchitectureCase:
    """A case whose answers are legitimate, about this repository, and off this topic."""

    case = ArchitectureCase.create().open_revision()
    return case.with_answer(
        Answer(
            question=Question.create(
                text="What constrains this architecture?",
                facet=CaseFacet.CONSTRAINT,
                candidate_ids=("candidate-1",),
                round=1,
            ),
            status=AnswerStatus.ANSWERED,
            value="payment payment payment handling stays with the payment provider",
            actor="a person",
            answered_at=utc_now(),
        )
    )


def test_the_structural_concern_survives_a_case_about_something_else(
    tmp_path: Path,
) -> None:
    """The measured defect, reduced to the two topics that produced it.

    With one query the case text moved the vector off the candidate's own concern, and the
    policy the candidate most obviously bears on fell out of the selection. Two queries and
    a rank fusion keep it, because the structural ranking still has an opinion of its own.
    """

    corpus = _two_topics_and_filler()
    retriever = DensePolicyRetriever(_topic_index(tmp_path, corpus), top_k=8)

    selected = retriever.retrieve(
        _duplicated_constant(), _case_about_payments(), corpus
    )

    assert next(item.policy.id for item in selected.selections) == "about-duplication"


def test_the_case_still_reaches_retrieval(tmp_path: Path) -> None:
    """Fusion must not have quietly deleted the case from the contract.

    Half the point of retrieving against a case is that a boundary somebody has spoken
    about is not the same retrieval problem as one nobody has. If the case query were
    dropped rather than fused, this policy would never be selected.
    """

    corpus = _two_topics_and_filler()
    retriever = DensePolicyRetriever(_topic_index(tmp_path, corpus), top_k=8)

    with_case = retriever.retrieve(
        _duplicated_constant(), _case_about_payments(), corpus
    )
    without_case = retriever.retrieve(
        _duplicated_constant(), ArchitectureCase.create(), corpus
    )

    ranked_with = [item.policy.id for item in with_case.selections]
    ranked_without = [item.policy.id for item in without_case.selections]
    assert ranked_with != ranked_without, "the case made no difference to the ranking"
    assert "about-payments" in ranked_with


def test_the_provenance_names_the_fusion_and_not_its_arithmetic(tmp_path: Path) -> None:
    """Enough to reproduce the selection, and not a dump of the scores behind it."""

    corpus = _two_topics_and_filler()
    retriever = DensePolicyRetriever(_topic_index(tmp_path, corpus), top_k=8)

    provenance = retriever.retrieve(
        _duplicated_constant(), _case_about_payments(), corpus
    ).provenance

    assert provenance.version == "2-rrf-equal-1-k8"
    assert ("fusion", "rrf-equal-1") in provenance.metadata
    assert provenance.model_identity == "topic:v1"
    assert not any(key.endswith("_score") for key, _ in provenance.metadata)
