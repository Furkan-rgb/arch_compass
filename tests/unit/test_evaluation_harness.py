"""A tripwire under the evaluation harness, so it cannot rot without saying so.

Nothing here needs Ollama, a key or a vector. It exists because the harness lives outside
every net `make check` casts — pyright reads `src`, pytest reads `tests` — and has twice
been broken by a change somewhere else without anything failing:

  62a9652  the notebook could not be imported at all, for two days
  and again when that same commit changed how the dataset's authored intent reaches a
  case, which altered the text being embedded and quietly invalidated the committed
  baseline. Nothing said so; the numbers simply stopped describing the code.

So this asserts the joins, not the numbers: that the harness imports, that the labelled
cases still load, that a query can still be built from one, and that the baseline records
which embedding function produced it.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


def test_the_harness_still_imports() -> None:
    """The failure that went unnoticed for two days, reduced to one line."""

    pytest.importorskip("yaml")
    from evaluation.harness import corpus, dataset, indexes, metrics, runner  # noqa: F401


def test_the_labelled_cases_still_load_and_still_join_to_the_corpus() -> None:
    """A dataset that stops matching the corpus is a baseline measuring nothing."""

    pytest.importorskip("yaml")
    from evaluation.harness.corpus import shipped_corpus
    from evaluation.harness.dataset import load_cases

    cases = load_cases(ROOT)
    policies = {policy.id for policy in shipped_corpus(ROOT)}

    assert len(cases) >= 40, f"only {len(cases)} labelled cases"
    unknown = {
        bearing
        for case in cases
        for bearing in case.bearing
        if bearing not in policies
    }
    assert not unknown, f"labelled policies the corpus no longer has: {sorted(unknown)}"


def test_a_query_can_still_be_built_from_a_labelled_case() -> None:
    """The join that broke the baseline without breaking anything else.

    `retrieval_query` is what actually gets embedded. When the dataset changed how it puts
    authored intent onto a case, the text changed with it and the committed numbers stopped
    describing the code — silently, because nothing exercised this path outside the
    notebook.
    """

    pytest.importorskip("yaml")
    from evaluation.harness.dataset import load_cases

    from archcompass.policies.retrieval import retrieval_query

    case = next(item for item in load_cases(ROOT) if item.candidate is not None)
    query = retrieval_query(case.candidate, case.case)

    assert query.strip()
    assert "Pattern:" in query


def test_the_baseline_names_the_embedding_function_it_was_measured_against() -> None:
    """`embeddinggemma:latest` is a moving tag, and a baseline against a moving tag is a
    number nobody can attribute afterwards.

    Ollama can report a digest and cannot be asked to serve one, so the pin is an assertion
    rather than a constraint. What this checks is only that the assertion exists and is a
    sha256 — the comparison itself needs a running Ollama and lives in the notebook's
    preflight.
    """

    from evaluation.harness.indexes import EXPECTED_EMBEDDER_DIGEST

    assert re.fullmatch(r"[0-9a-f]{64}", EXPECTED_EMBEDDER_DIGEST)
