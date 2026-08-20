"""Running the test set: over an index for ranking quality, over the retriever for the gate.

Two levels, kept separate on purpose. `run_index` asks the ranking question — given this
query, in what order does the corpus come back — and is what the metrics read. `run_retriever`
runs the whole shipped `DensePolicyRetriever`, mandatory merge and provenance included, and
is what the release gate reads. A ranking can be excellent while the retriever is wrong,
because the merge is where scope and required strength enter, and the ranking cannot see them.
"""

from __future__ import annotations

import time
from collections.abc import Sequence
from dataclasses import dataclass

from archcompass.domain import ArchitectureCase, Policy, PolicyScope, PolicyStrength
from archcompass.policies.evaluation import RetrievalExample
from archcompass.policies.retrieval import DensePolicyRetriever
from archcompass.ports.dense_policy_index import DensePolicyIndex
from archcompass.ports.policy_retrieval import RetrievedPolicySet
from evaluation.harness.dataset import EvalCase

__all__ = ["RunResult", "gate_examples", "mandatory_ids", "run_index", "run_retriever"]


@dataclass(frozen=True, slots=True)
class RunResult:
    case_id: str
    kind: str
    pattern: str
    ranked: tuple[str, ...]
    scores: tuple[float, ...]
    seconds: float


def run_index(
    index: DensePolicyIndex,
    corpus: tuple[Policy, ...],
    cases: Sequence[EvalCase],
    *,
    limit: int = 20,
) -> tuple[RunResult, ...]:
    """Rank the corpus for every case. Synchronizes once, then times each query alone."""

    index.synchronize(corpus)
    results: list[RunResult] = []
    for case in cases:
        started = time.perf_counter()
        matches = index.search(case.query, limit=limit)
        elapsed = time.perf_counter() - started
        results.append(
            RunResult(
                case_id=case.id,
                kind=case.kind,
                pattern=case.pattern,
                ranked=tuple(match.policy_id for match in matches),
                scores=tuple(match.score for match in matches),
                seconds=elapsed,
            )
        )
    return tuple(results)


def mandatory_ids(case: ArchitectureCase, corpus: tuple[Policy, ...]) -> frozenset[str]:
    """What the retriever must include for this case whatever the embeddings rank.

    The rule the shipped retriever applies, restated here so the gate's `required` and
    `scoped` columns are derived from the corpus and the case rather than typed into YAML.
    """

    context = case.policy_context
    return frozenset(
        policy.id
        for policy in corpus
        if policy.applies_in(
            user=context.user,
            organisation=context.organisation,
            repository=context.repository,
        )
        and (policy.scope is not PolicyScope.GENERAL or policy.strength is PolicyStrength.REQUIRED)
    )


def run_retriever(
    index: DensePolicyIndex,
    corpus: tuple[Policy, ...],
    cases: Sequence[EvalCase],
    *,
    top_k: int,
) -> tuple[tuple[EvalCase, RetrievedPolicySet], ...]:
    """The shipped retriever end to end, at one of the four K values the gate evaluates."""

    retriever = DensePolicyRetriever(index, top_k=top_k)
    return tuple(
        (case, retriever.retrieve(case.candidate, case.case, corpus))
        for case in cases
        if case.candidate is not None and case.case is not None
    )


def gate_examples(
    runs: Sequence[tuple[EvalCase, RetrievedPolicySet]],
    corpus: tuple[Policy, ...],
) -> tuple[RetrievalExample, ...]:
    """Retriever output in the shape `archcompass.policies.evaluation` scores.

    `reference_material` and `retrieved_material` are left unset. They compare the verdict a
    judge reaches on the retrieved policies against the verdict it reaches on the whole
    corpus, which costs a reasoning model per candidate per K — out of scope for an offline
    notebook, and reported as an uncovered gate rather than assumed to pass.
    """

    examples: list[RetrievalExample] = []
    for case, retrieved in runs:
        assert case.case is not None
        mandatory = mandatory_ids(case.case, corpus)
        required = frozenset(
            policy.id
            for policy in corpus
            if policy.id in mandatory and policy.scope is PolicyScope.GENERAL
        )
        examples.append(
            RetrievalExample(
                pattern=case.pattern,
                expected_policy_ids=case.bearing,
                selected_policy_ids=tuple(policy.id for policy in retrieved.policies),
                required_policy_ids=required,
                scoped_policy_ids=mandatory - required,
            )
        )
    return tuple(examples)
