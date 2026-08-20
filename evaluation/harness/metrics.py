"""Ranking metrics, defined once so a number means the same thing in every cell.

Two levels of truth are kept apart throughout. The *bearing* set is what a reviewer would
cite in the verdict: missing one of these is a wrong retrieval, and recall over bearings is
the headline. The graded set adds policies that are relevant without being load-bearing,
and only nDCG reads those — it is the metric that can tell "found it at rank 1" from "found
it at rank 18", which recall cannot.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from statistics import mean

__all__ = [
    "CaseScores",
    "Summary",
    "average_precision",
    "ndcg_at_k",
    "precision_at_k",
    "rank_of",
    "recall_at_k",
    "reciprocal_rank",
    "score_case",
    "summarize",
]


def recall_at_k(ranked: Sequence[str], relevant: frozenset[str], k: int) -> float:
    """The share of the relevant set that appears in the first k results."""

    if not relevant:
        return 1.0
    return len(set(ranked[:k]) & relevant) / len(relevant)


def precision_at_k(ranked: Sequence[str], relevant: frozenset[str], k: int) -> float:
    if k < 1:
        return 0.0
    return len(set(ranked[:k]) & relevant) / k


def reciprocal_rank(ranked: Sequence[str], relevant: frozenset[str]) -> float:
    """1/rank of the first relevant result, and 0 when none was retrieved at all."""

    for position, policy_id in enumerate(ranked, start=1):
        if policy_id in relevant:
            return 1.0 / position
    return 0.0


def average_precision(ranked: Sequence[str], relevant: frozenset[str]) -> float:
    """Precision at each hit, averaged over the relevant set — rewards early hits."""

    if not relevant:
        return 1.0
    found = 0
    total = 0.0
    for position, policy_id in enumerate(ranked, start=1):
        if policy_id in relevant:
            found += 1
            total += found / position
    return total / len(relevant)


def ndcg_at_k(ranked: Sequence[str], grades: Mapping[str, int], k: int) -> float:
    """Graded gain discounted by rank, against the best ordering the grades allow."""

    if not grades:
        return 1.0
    gain = sum(
        (2 ** grades.get(policy_id, 0) - 1) / math.log2(position + 1)
        for position, policy_id in enumerate(ranked[:k], start=1)
    )
    best = sum(
        (2**grade - 1) / math.log2(position + 1)
        for position, grade in enumerate(sorted(grades.values(), reverse=True)[:k], start=1)
    )
    return gain / best if best else 1.0


def rank_of(ranked: Sequence[str], policy_id: str) -> int | None:
    """Where a policy landed, one-based, or None when it was not retrieved."""

    for position, found in enumerate(ranked, start=1):
        if found == policy_id:
            return position
    return None


@dataclass(frozen=True, slots=True)
class CaseScores:
    case_id: str
    kind: str
    pattern: str
    bearing_recall_at_k: tuple[tuple[int, float], ...]
    precision_at_k: tuple[tuple[int, float], ...]
    reciprocal_rank: float
    average_precision: float
    ndcg_at_10: float
    ndcg_at_20: float
    complete_at_20: bool
    missed_at_20: tuple[str, ...]
    bearing_ranks: tuple[tuple[str, int | None], ...]

    def recall(self, k: int) -> float:
        return dict(self.bearing_recall_at_k)[k]

    def precision(self, k: int) -> float:
        return dict(self.precision_at_k)[k]


def score_case(
    *,
    case_id: str,
    kind: str,
    pattern: str,
    ranked: Sequence[str],
    bearing: frozenset[str],
    grades: Mapping[str, int],
    ks: Sequence[int],
) -> CaseScores:
    return CaseScores(
        case_id=case_id,
        kind=kind,
        pattern=pattern,
        bearing_recall_at_k=tuple((k, recall_at_k(ranked, bearing, k)) for k in ks),
        precision_at_k=tuple((k, precision_at_k(ranked, bearing, k)) for k in ks),
        reciprocal_rank=reciprocal_rank(ranked, bearing),
        average_precision=average_precision(ranked, bearing),
        ndcg_at_10=ndcg_at_k(ranked, grades, 10),
        ndcg_at_20=ndcg_at_k(ranked, grades, 20),
        complete_at_20=bearing <= set(ranked[:20]),
        missed_at_20=tuple(sorted(bearing - set(ranked[:20]))),
        bearing_ranks=tuple(sorted((item, rank_of(ranked, item)) for item in bearing)),
    )


@dataclass(frozen=True, slots=True)
class Summary:
    """One retriever variant reduced to the numbers a comparison table wants.

    Macro averages throughout — every case counts once, whatever the size of its bearing
    set. A micro average would let the six near-identical boundary-review ports outvote a
    case that appears once, which is the opposite of what a spread test set is for.
    """

    label: str
    cases: int
    recall_at_k: tuple[tuple[int, float], ...]
    precision_at_k: tuple[tuple[int, float], ...]
    mrr: float
    map_score: float
    ndcg_at_10: float
    ndcg_at_20: float
    complete_at_20: float
    recall_by_pattern: tuple[tuple[str, float], ...]
    recall_by_kind: tuple[tuple[str, float], ...]

    def recall(self, k: int) -> float:
        return dict(self.recall_at_k)[k]

    def precision(self, k: int) -> float:
        return dict(self.precision_at_k)[k]


def summarize(label: str, scores: Sequence[CaseScores], ks: Sequence[int]) -> Summary:
    if not scores:
        raise ValueError("a summary needs at least one scored case")
    by_pattern: dict[str, list[float]] = {}
    by_kind: dict[str, list[float]] = {}
    for score in scores:
        by_pattern.setdefault(score.pattern, []).append(score.recall(20))
        by_kind.setdefault(score.kind, []).append(score.recall(20))
    return Summary(
        label=label,
        cases=len(scores),
        recall_at_k=tuple((k, mean(score.recall(k) for score in scores)) for k in ks),
        precision_at_k=tuple((k, mean(score.precision(k) for score in scores)) for k in ks),
        mrr=mean(score.reciprocal_rank for score in scores),
        map_score=mean(score.average_precision for score in scores),
        ndcg_at_10=mean(score.ndcg_at_10 for score in scores),
        ndcg_at_20=mean(score.ndcg_at_20 for score in scores),
        complete_at_20=mean(float(score.complete_at_20) for score in scores),
        recall_by_pattern=tuple(
            sorted((pattern, mean(values)) for pattern, values in by_pattern.items())
        ),
        recall_by_kind=tuple(sorted((kind, mean(values)) for kind, values in by_kind.items())),
    )
