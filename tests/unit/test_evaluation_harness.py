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
    pytest.importorskip("numpy")
    # Not `report`: it draws the charts and needs the `evaluation` dependency group, which
    # `uv sync --locked` does not install. What has to import without one is the part that
    # decides anything.
    from evaluation.harness import corpus, dataset, indexes, metrics, runner  # noqa: F401


def test_the_labelled_cases_still_load_and_still_join_to_the_corpus() -> None:
    """A dataset that stops matching the corpus is a baseline measuring nothing."""

    pytest.importorskip("yaml")
    pytest.importorskip("numpy")
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
    pytest.importorskip("numpy")
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


def test_an_index_built_by_a_different_embedder_cannot_be_reused(tmp_path: Path) -> None:
    """The reproducibility hole, at the seam that actually has one.

    `synchronize` is incremental and keys on chunk content. A changed *corpus* it handles —
    stale chunks are removed in the same transaction. What it cannot see is the same corpus
    embedded by a different function under an unchanged identity, which is precisely what a
    moved `:latest` tag produces: the content hashes match, nothing is re-embedded, and the
    run reports last month's vectors as this month's measurement.

    Verified before this test existed: two orthogonal embedders over one file both scored
    1.0, because the second never ran. Fresh construction is what makes the second run
    measure the second embedder.
    """

    pytest.importorskip("numpy")
    from evaluation.harness.indexes import fresh_sqlite_index

    from archcompass.domain import Policy, PolicyScope, PolicyStrength

    corpus = (
        Policy(
            id="unchanged",
            title="unchanged",
            body="the same text both times",
            scope=PolicyScope.GENERAL,
            strength=PolicyStrength.GUIDANCE,
            content_hash="hash-unchanged",
        ),
    )

    class _Fixed:
        """An embedder whose answer is a constructor argument, not a function of the text."""

        def __init__(self, vector: list[float]) -> None:
            self._vector = vector

        def embed_documents(self, texts: list[str]) -> list[list[float]]:
            return [self._vector for _ in texts]

        def embed_query(self, text: str) -> list[float]:
            return [1.0, 0.0]

    path = tmp_path / "policy-index.sqlite3"
    before = fresh_sqlite_index(
        path, _Fixed([1.0, 0.0]), embedding_identity="unchanged:v1", dimensions=2
    )
    before.synchronize(corpus)
    assert before.search("q", limit=1)[0].score > 0.9

    # The same identity, the same corpus, an embedder that now answers orthogonally.
    after = fresh_sqlite_index(
        path, _Fixed([0.0, 1.0]), embedding_identity="unchanged:v1", dimensions=2
    )
    after.synchronize(corpus)

    assert after.search("q", limit=1)[0].score < 0.1, (
        "the second run measured the first run's vectors"
    )


def test_building_fresh_does_not_need_the_directory_to_exist(tmp_path: Path) -> None:
    """`make evaluation` runs on a machine that has never run it before."""

    pytest.importorskip("numpy")
    from evaluation.harness.indexes import fresh_sqlite_index

    class _Fixed:
        def embed_documents(self, texts: list[str]) -> list[list[float]]:
            return [[1.0, 0.0] for _ in texts]

        def embed_query(self, text: str) -> list[float]:
            return [1.0, 0.0]

    built = fresh_sqlite_index(
        tmp_path / "never" / "existed" / "index.sqlite3",
        _Fixed(),
        embedding_identity="test:v1",
        dimensions=2,
    )

    assert built is not None
