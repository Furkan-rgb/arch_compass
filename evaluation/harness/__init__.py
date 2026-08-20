"""Measurement apparatus for the policy retriever, kept out of the notebook.

The notebook is the report: it runs things, shows numbers, and says what they mean. What
it must not also be is the definition of a metric, because a definition that lives in a
cell is one nobody can test and one that quietly changes between runs. Everything with a
right answer lives here instead — how a corpus is loaded, what recall@k is, how a labelled
case becomes a query — and the notebook imports it.
"""

from evaluation.harness import report
from evaluation.harness.corpus import (
    chunk_report,
    evaluation_corpus,
    scoped_policies,
    shipped_corpus,
)
from evaluation.harness.dataset import (
    EvalCase,
    LabelledCase,
    candidate_cases,
    detected_candidates,
    intent_cases,
    label_coverage,
    load_cases,
)
from evaluation.harness.indexes import (
    Bm25PolicyIndex,
    InMemoryDenseIndex,
    RandomPolicyIndex,
    TaskPrefixedEmbeddings,
    heading_chunks,
    ollama_embeddings,
    whole_document_chunks,
)
from evaluation.harness.metrics import (
    CaseScores,
    Summary,
    average_precision,
    ndcg_at_k,
    precision_at_k,
    recall_at_k,
    reciprocal_rank,
    score_case,
    summarize,
)
from evaluation.harness.runner import (
    RunResult,
    gate_examples,
    run_index,
    run_retriever,
)

__all__ = [
    "Bm25PolicyIndex",
    "CaseScores",
    "EvalCase",
    "InMemoryDenseIndex",
    "LabelledCase",
    "RandomPolicyIndex",
    "RunResult",
    "Summary",
    "TaskPrefixedEmbeddings",
    "average_precision",
    "candidate_cases",
    "chunk_report",
    "detected_candidates",
    "evaluation_corpus",
    "gate_examples",
    "heading_chunks",
    "intent_cases",
    "label_coverage",
    "load_cases",
    "ndcg_at_k",
    "ollama_embeddings",
    "precision_at_k",
    "recall_at_k",
    "reciprocal_rank",
    "report",
    "run_index",
    "run_retriever",
    "scoped_policies",
    "score_case",
    "shipped_corpus",
    "summarize",
    "whole_document_chunks",
]
