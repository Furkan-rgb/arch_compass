"""Tables and charts, so a notebook cell can be one line and still say something.

Nothing here decides anything. It runs a variant, scores it with `metrics`, and shapes the
result for reading. The reason it is a module rather than notebook cells is that formatting
is the bulk of the code and none of it is the point — a reader looking for what was measured
should not have to scroll past how it was tabulated.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

import matplotlib.pyplot as plt
import pandas as pd

from archcompass.domain import Policy
from archcompass.policies.evaluation import RetrievalEvaluation
from archcompass.policies.ports import DensePolicyIndex
from evaluation.harness.dataset import EvalCase
from evaluation.harness.metrics import CaseScores, Summary, score_case, summarize
from evaluation.harness.runner import run_index

__all__ = [
    "Scored",
    "evaluate",
    "gate_table",
    "miss_table",
    "rank_charts",
    "recall_charts",
    "table",
]

PALETTE = ("#4c72b0", "#dd8452", "#55a868", "#c44e52", "#8172b3")


@dataclass(frozen=True, slots=True)
class Scored:
    """One retriever variant, run and scored over the whole test set."""

    label: str
    summary: Summary
    scores: tuple[CaseScores, ...]
    #: The complete ranking per case, not the top-K window. A missed policy needs a real
    #: rank to be actionable: rank 22 means the window is too narrow, rank 45 means the
    #: query and the document do not meet and no window reaches it.
    ranking: dict[str, tuple[str, ...]]
    seconds: tuple[float, ...]


def evaluate(
    index: DensePolicyIndex,
    corpus: tuple[Policy, ...],
    cases: Sequence[EvalCase],
    *,
    label: str,
    ks: Sequence[int],
) -> Scored:
    """Rank the whole corpus for every case, then score it."""

    by_id = {case.id: case for case in cases}
    runs = run_index(index, corpus, cases, limit=len(corpus))
    scores = tuple(
        score_case(
            case_id=run.case_id,
            kind=run.kind,
            pattern=run.pattern,
            ranked=run.ranked,
            bearing=by_id[run.case_id].bearing,
            grades=by_id[run.case_id].grades,
            ks=ks,
        )
        for run in runs
    )
    return Scored(
        label=label,
        summary=summarize(label, scores, ks),
        scores=scores,
        ranking={run.case_id: run.ranked for run in runs},
        seconds=tuple(run.seconds for run in runs),
    )


def table(*scored: Scored, ks: Sequence[int] | None = None) -> pd.DataFrame:
    """One row per variant: recall at each k, then the rank-sensitive metrics."""

    rows = []
    for item in scored:
        summary = item.summary
        wanted = ks if ks is not None else [k for k, _ in summary.recall_at_k]
        rows.append(
            {"variant": summary.label, "cases": summary.cases}
            | {f"R@{k}": summary.recall(k) for k in wanted}
            | {
                "MRR": summary.mrr,
                "MAP": summary.map_score,
                "nDCG@10": summary.ndcg_at_10,
                "complete@20": summary.complete_at_20,
            }
        )
    return pd.DataFrame(rows).set_index("variant").round(3)


def recall_charts(*scored: Scored, ks: Sequence[int], shipped_k: int = 20) -> None:
    """Recall against k for each variant, and recall@20 per pattern for the first."""

    figure, (left, right) = plt.subplots(1, 2, figsize=(11, 3.5))
    for colour, item in zip(PALETTE, scored, strict=False):
        left.plot(ks, [item.summary.recall(k) for k in ks], marker="o", color=colour,
                  label=item.label)
    left.axvline(shipped_k, color="grey", linestyle=":", linewidth=1)
    left.set(xlabel="k", ylabel="recall@k (bearing policies)", ylim=(0, 1.02),
             title=f"Recall against k  (dotted line: shipped K={shipped_k})")
    left.legend(fontsize=8)

    patterns = dict(scored[0].summary.recall_by_pattern)
    order = sorted(patterns, key=lambda name: patterns[name])
    bars = right.barh(order, [patterns[name] for name in order], color=PALETTE[0])
    right.axvline(0.90, color="crimson", linestyle="--", linewidth=1)
    right.set(xlim=(0, 1.05), xlabel="recall@20", title="Recall@20 by pattern")
    right.bar_label(bars, fmt="%.2f", fontsize=8, padding=3)
    right.annotate("gate floor", (0.90, -0.44), fontsize=8, color="crimson", ha="center")
    _finish(figure)


def _finish(figure: plt.Figure) -> None:
    figure.tight_layout()
    plt.show()


def miss_table(
    scored: Scored, cases: Sequence[EvalCase], *, window: int = 20
) -> pd.DataFrame:
    """Every bearing policy that fell outside the window, with where it actually landed."""

    by_id = {case.id: case for case in cases}
    rows = [
        {
            "case": score.case_id,
            "pattern": score.pattern,
            "missed policy": policy,
            "true rank": scored.ranking[score.case_id].index(policy) + 1,
        }
        for score in scored.scores
        for policy in sorted(by_id[score.case_id].bearing)
        if policy not in scored.ranking[score.case_id][:window]
    ]
    return pd.DataFrame(rows).sort_values("true rank").set_index("case")


def rank_charts(
    scored: Scored, cases: Sequence[EvalCase], *, corpus_size: int, window: int = 20
) -> None:
    """Where bearing policies land, and what a wider window would recover."""

    by_id = {case.id: case for case in cases}
    positions = pd.Series(
        [
            scored.ranking[score.case_id].index(policy) + 1
            for score in scored.scores
            for policy in by_id[score.case_id].bearing
        ]
    )
    figure, (left, right) = plt.subplots(1, 2, figsize=(11, 3.4))
    left.hist(positions, bins=range(1, corpus_size + 2, 2), color=PALETTE[0])
    left.axvline(window + 0.5, color="crimson", linestyle="--", linewidth=1)
    left.annotate(f"K={window}", (window + 1.5, left.get_ylim()[1] * 0.88), fontsize=8,
                  color="crimson")
    left.set(xlabel=f"rank of a bearing policy (of {corpus_size})",
             ylabel="bearing policies", title="Where the right answers land")

    reached = [(positions <= k).mean() for k in range(1, corpus_size + 1)]
    right.plot(range(1, corpus_size + 1), reached, color=PALETTE[0])
    right.axvline(window, color="crimson", linestyle="--", linewidth=1)
    right.axhline(reached[window - 1], color="grey", linestyle=":", linewidth=1)
    right.annotate(f"{reached[window - 1]:.0%} inside K={window}",
                   (window + 1.5, reached[window - 1] - 0.09), fontsize=8)
    right.set(xlabel="k", ylabel="share of bearing policies within k", ylim=(0, 1.02),
              title="What a wider window would buy")
    _finish(figure)


def gate_table(results: dict[int, RetrievalEvaluation]) -> pd.DataFrame:
    """The four covered release-gate conditions at each K, with the floors beside them.

    `verdict_regression` is left out. It compares the verdict a judge reaches on the
    retrieved policies against the verdict it reaches on the whole corpus, which needs a
    reasoning model; nothing offline can fill that column, and a zero in it would read as
    a pass rather than as the absence of a measurement.
    """

    frame = pd.DataFrame(
        [
            {
                "K": top_k,
                "macro recall": result.macro_recall,
                "worst pattern": min(value for _, value in result.recall_by_pattern),
                "complete coverage": result.complete_coverage,
                "mandatory coverage": result.mandatory_coverage,
                "passes": result.passed,
            }
            for top_k, result in results.items()
        ]
    ).set_index("K")
    floors = pd.DataFrame(
        [{"macro recall": 0.95, "worst pattern": 0.90, "complete coverage": 0.75,
          "mandatory coverage": 1.00, "passes": True}],
        index=pd.Index(["floor"], name="K"),
    )
    return pd.concat([frame.round(3), floors])

