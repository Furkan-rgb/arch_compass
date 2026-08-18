"""One-capability graph nodes; all sequencing lives in :mod:`workflow.graph`."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import cast

from langgraph.types import interrupt

from archcompass.application.capabilities import (
    ArchitectureJudge,
    CandidateDetector,
    CaseReviser,
    ContextLoader,
    InitialCandidateSelector,
    PolicyCorpus,
    PolicyRetriever,
    QuestionGenerator,
    RejudgementSelector,
    RepositoryAnalyzer,
    ReviewComposer,
    ReviewDraft,
    ReviewRecorder,
    RevisionCalculator,
)
from archcompass.domain.core import Answer
from archcompass.workflow.state import ReviewState

Node = Callable[[ReviewState], dict[str, object]]


def load_context_node(loader: ContextLoader) -> Node:
    def load_context(state: ReviewState) -> dict[str, object]:
        loaded = loader.load(
            state["repository_id"],
            state["branch_id"],
            state["case_id"],
            state["case_revision"],
        )
        return {
            "repository": loaded.repository,
            "case": loaded.case,
            "previous_review": loaded.previous_review,
            "review_history": loaded.review_history,
            "round": 1,
            "excluded_equivalence_keys": frozenset(
                answer.question.equivalence_key for answer in loaded.case.answers
            ),
            "retrievals": {},
            "findings": {},
            "stop_requested": False,
        }

    return load_context


def analyze_repository_node(analyzer: RepositoryAnalyzer) -> Node:
    def analyze_repository(state: ReviewState) -> dict[str, object]:
        return {"atlas": analyzer.analyze(state["repository"])}

    return analyze_repository


def detect_candidates_node(detector: CandidateDetector) -> Node:
    def detect_candidates(state: ReviewState) -> dict[str, object]:
        return {"candidates": detector.detect(state["atlas"])}

    return detect_candidates


def calculate_delta_node(calculator: RevisionCalculator) -> Node:
    def calculate_delta(state: ReviewState) -> dict[str, object]:
        return {
            "delta": calculator.calculate(
                state["candidates"],
                state["case"],
                state["previous_review"],
                state["repository"],
                state["review_history"],
            )
        }

    return calculate_delta


def select_initial_candidates_node(selector: InitialCandidateSelector) -> Node:
    def select_initial_candidates(state: ReviewState) -> dict[str, object]:
        selection = selector.select(
            state["candidates"], state["delta"], state["previous_review"], state["ci"]
        )
        return {
            "selected_candidates": selection.selected,
            "findings": {
                str(finding.candidate.id): finding
                for finding in selection.carried_findings
            },
        }

    return select_initial_candidates


def load_policy_corpus_node(corpus: PolicyCorpus) -> Node:
    def load_policy_corpus(state: ReviewState) -> dict[str, object]:
        return {"corpus": corpus.policies_for(state["repository"])}

    return load_policy_corpus


def retrieve_policy_set_node(retriever: PolicyRetriever) -> Node:
    def retrieve_policy_set(state: ReviewState) -> dict[str, object]:
        retrieval = retriever.retrieve(state["candidate"], state["case"], state["corpus"])
        return {"retrieval": retrieval}

    return retrieve_policy_set


def judge_candidate_node(judge: ArchitectureJudge) -> Node:
    def judge_candidate(state: ReviewState) -> dict[str, object]:
        candidate_id = str(state["candidate"].id)
        finding = judge.judge(state["candidate"], state["case"], state["retrieval"])
        return {
            "retrievals": {candidate_id: state["retrieval"]},
            "findings": {candidate_id: finding},
        }

    return judge_candidate


def generate_questions_node(generator: QuestionGenerator) -> Node:
    def generate_questions(state: ReviewState) -> dict[str, object]:
        ordered = tuple(
            state["findings"][str(candidate.id)]
            for candidate in state["candidates"]
            if str(candidate.id) in state["findings"]
        )
        return {
            "questions": generator.generate(
                state["case"],
                ordered,
                round=state["round"],
                excluded_equivalence_keys=state["excluded_equivalence_keys"],
            )
        }

    return generate_questions


def compose_review_node(composer: ReviewComposer, *, waiting: bool) -> Node:
    def compose_review(state: ReviewState) -> dict[str, object]:
        ordered_findings = tuple(
            state["findings"][str(candidate.id)]
            for candidate in state["candidates"]
            if str(candidate.id) in state["findings"]
        )
        ordered_retrievals = tuple(
            state["retrievals"][str(candidate.id)]
            for candidate in state["candidates"]
            if str(candidate.id) in state["retrievals"]
        )
        draft = ReviewDraft(
            repository=state["repository"],
            atlas=state["atlas"],
            case=state["case"],
            findings=ordered_findings,
            questions=state["questions"],
            delta=state["delta"],
            previous=state["previous_review"],
            retrievals=ordered_retrievals,
        )
        return {"draft": draft, "review": composer.compose(draft, waiting=waiting)}

    return compose_review


def record_review_node(recorder: ReviewRecorder, *, advance_lineage: bool = False) -> Node:
    def record_review(state: ReviewState) -> dict[str, object]:
        recorded = recorder.record(state["review"])
        update: dict[str, object] = {"review": recorded}
        if advance_lineage:
            update["previous_review"] = recorded
        return update

    return record_review


def await_answers_node() -> Node:
    def await_answers(state: ReviewState) -> dict[str, object]:
        response = cast(
            object,
            interrupt(
                {
                    "review_id": state["review"].id,
                    "questions": state["questions"],
                    "round": state["round"],
                },
            ),
        )
        if not isinstance(response, Mapping):
            raise ValueError("answer resume payload must be a mapping")
        answers = cast(object, response.get("answers", ()))
        if not isinstance(answers, (list, tuple)):
            raise ValueError("answer resume payload must contain domain Answer values")
        untyped_answers = cast("list[object] | tuple[object, ...]", answers)
        if not all(isinstance(answer, Answer) for answer in untyped_answers):
            raise ValueError("answer resume payload must contain domain Answer values")
        typed_answers = cast("list[Answer] | tuple[Answer, ...]", answers)
        stop = cast(object, response.get("stop", False))
        return {
            "pending_answers": tuple(typed_answers),
            "stop_requested": stop is True,
        }

    return await_answers


def revise_case_node(reviser: CaseReviser) -> Node:
    def revise_case(state: ReviewState) -> dict[str, object]:
        revised = reviser.revise(state["case"], state["pending_answers"])
        excluded = state["excluded_equivalence_keys"] | {
            answer.question.equivalence_key for answer in state["pending_answers"]
        }
        return {
            "previous_case": state["case"],
            "case": revised,
            "round": state["round"] + 1,
            "excluded_equivalence_keys": frozenset(excluded),
        }

    return revise_case


def select_rejudgements_node(selector: RejudgementSelector) -> Node:
    def select_rejudgements(state: ReviewState) -> dict[str, object]:
        return {
            "selected_candidates": selector.select(
                state["candidates"], state["previous_case"], state["case"]
            )
        }

    return select_rejudgements
