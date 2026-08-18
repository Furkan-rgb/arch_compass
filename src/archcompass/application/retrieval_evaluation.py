"""Provider-independent acceptance metrics for PolicyRetriever implementations."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class RetrievalExample:
    pattern: str
    expected_policy_ids: frozenset[str]
    selected_policy_ids: tuple[str, ...]
    required_policy_ids: frozenset[str] = frozenset()
    scoped_policy_ids: frozenset[str] = frozenset()
    reference_material: bool | None = None
    retrieved_material: bool | None = None


@dataclass(frozen=True, slots=True)
class RetrievalEvaluation:
    macro_recall: float
    recall_by_pattern: tuple[tuple[str, float], ...]
    complete_coverage: float
    mandatory_coverage: float
    verdict_regression: float
    passed: bool


def evaluate_retrieval(examples: tuple[RetrievalExample, ...]) -> RetrievalEvaluation:
    if not examples:
        raise ValueError("retrieval evaluation needs examples")
    recalls: list[float] = []
    by_pattern: dict[str, list[float]] = defaultdict(list)
    complete = 0
    mandatory_expected = 0
    mandatory_found = 0
    comparable = 0
    regressions = 0
    for example in examples:
        selected = set(example.selected_policy_ids)
        recall = (
            len(selected & example.expected_policy_ids) / len(example.expected_policy_ids)
            if example.expected_policy_ids
            else 1.0
        )
        recalls.append(recall)
        by_pattern[example.pattern].append(recall)
        complete += example.expected_policy_ids <= selected
        mandatory = example.required_policy_ids | example.scoped_policy_ids
        mandatory_expected += len(mandatory)
        mandatory_found += len(mandatory & selected)
        if example.reference_material is not None and example.retrieved_material is not None:
            comparable += 1
            regressions += example.reference_material != example.retrieved_material

    pattern_recall = tuple(
        sorted((pattern, sum(values) / len(values)) for pattern, values in by_pattern.items())
    )
    macro = sum(recalls) / len(recalls)
    full = complete / len(examples)
    mandatory_coverage = mandatory_found / mandatory_expected if mandatory_expected else 1.0
    regression = regressions / comparable if comparable else 0.0
    return RetrievalEvaluation(
        macro_recall=macro,
        recall_by_pattern=pattern_recall,
        complete_coverage=full,
        mandatory_coverage=mandatory_coverage,
        verdict_regression=regression,
        passed=(
            macro >= 0.95
            and all(value >= 0.90 for _, value in pattern_recall)
            and full >= 0.75
            and mandatory_coverage == 1.0
            and regression <= 0.10
        ),
    )


def choose_smallest_passing_k(
    examples_for: Callable[[int], tuple[RetrievalExample, ...]],
) -> tuple[int, RetrievalEvaluation]:
    """Apply the release gate to 8, 12, 16, then 20 without human tuning."""

    evaluated: list[tuple[int, RetrievalEvaluation]] = []
    for top_k in (8, 12, 16, 20):
        result = evaluate_retrieval(examples_for(top_k))
        evaluated.append((top_k, result))
        if result.passed:
            return top_k, result
    summary = ", ".join(
        f"k={top_k}: recall={result.macro_recall:.3f}, "
        f"coverage={result.complete_coverage:.3f}"
        for top_k, result in evaluated
    )
    raise ValueError(f"No evaluated dense top-K passes the retrieval gate ({summary})")
