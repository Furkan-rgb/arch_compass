"""The canonical, visible review sequence.

There is intentionally no coordinator behind this file.  Every business node delegates to
one named capability.  The candidate subgraph makes retrieval-before-judgement explicit,
while ``Send`` exposes candidate fan-out to LangGraph rather than a private thread pool.
"""

# LangGraph's ``StateNode`` union includes positional-only and keyword-only callable
# variants. Pyright cannot narrow an ordinary one-argument node factory into that union,
# although LangGraph accepts and executes it; runtime graph tests cover this boundary.
# pyright: reportArgumentType=false

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph
from langgraph.types import Send

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
    ReviewRecorder,
    RevisionCalculator,
)
from archcompass.workflow.nodes import (
    analyze_repository_node,
    await_answers_node,
    calculate_delta_node,
    compose_review_node,
    detect_candidates_node,
    generate_questions_node,
    judge_candidate_node,
    load_context_node,
    load_policy_corpus_node,
    record_review_node,
    retrieve_policy_set_node,
    revise_case_node,
    select_initial_candidates_node,
    select_rejudgements_node,
)
from archcompass.workflow.state import CandidateReviewOutput, ReviewInput, ReviewState


@dataclass(frozen=True, slots=True)
class ReviewWorkflowCapabilities:
    context: ContextLoader
    analyzer: RepositoryAnalyzer
    detector: CandidateDetector
    revisions: RevisionCalculator
    initial_candidates: InitialCandidateSelector
    corpus: PolicyCorpus
    retriever: PolicyRetriever
    judge: ArchitectureJudge
    questions: QuestionGenerator
    rejudgements: RejudgementSelector
    cases: CaseReviser
    composer: ReviewComposer
    recorder: ReviewRecorder


def _candidate_graph(
    capabilities: ReviewWorkflowCapabilities,
) -> CompiledStateGraph[ReviewState, None, ReviewState, CandidateReviewOutput]:
    graph = StateGraph(ReviewState, output_schema=CandidateReviewOutput)
    graph.add_node("retrieve_policy_set", retrieve_policy_set_node(capabilities.retriever))
    graph.add_node("judge_candidate", judge_candidate_node(capabilities.judge))
    graph.add_edge(START, "retrieve_policy_set")
    graph.add_edge("retrieve_policy_set", "judge_candidate")
    graph.add_edge("judge_candidate", END)
    return graph.compile()


def _dispatch_candidates(state: ReviewState) -> list[Send] | Literal["generate_questions"]:
    if not state["selected_candidates"]:
        return "generate_questions"
    return [
        Send("review_candidate", {**state, "candidate": candidate})
        for candidate in state["selected_candidates"]
    ]


def _after_questions(
    state: ReviewState,
) -> Literal["compose_final_review", "compose_waiting_review"]:
    if (
        not state["questions"]
        or state["ci"]
        or state["round"] >= 3
        or state["stop_requested"]
    ):
        return "compose_final_review"
    return "compose_waiting_review"


def _after_case_revision(
    state: ReviewState,
) -> Literal["compose_final_review", "select_candidates_for_rejudgement"]:
    return (
        "compose_final_review"
        if state["stop_requested"]
        else "select_candidates_for_rejudgement"
    )


def build_review_graph(
    capabilities: ReviewWorkflowCapabilities,
    *,
    checkpointer: object | None = None,
) -> CompiledStateGraph[ReviewState, None, ReviewInput, ReviewState]:
    graph = StateGraph(ReviewState, input_schema=ReviewInput)
    graph.add_node("load_context", load_context_node(capabilities.context))
    graph.add_node("analyze_repository", analyze_repository_node(capabilities.analyzer))
    graph.add_node("detect_candidates", detect_candidates_node(capabilities.detector))
    graph.add_node("calculate_delta", calculate_delta_node(capabilities.revisions))
    graph.add_node(
        "select_initial_candidates",
        select_initial_candidates_node(capabilities.initial_candidates),
    )
    graph.add_node("load_policy_corpus", load_policy_corpus_node(capabilities.corpus))
    graph.add_node("review_candidate", _candidate_graph(capabilities))
    graph.add_node("generate_questions", generate_questions_node(capabilities.questions))
    graph.add_node(
        "compose_waiting_review",
        compose_review_node(capabilities.composer, waiting=True),
    )
    graph.add_node(
        "record_waiting_review",
        record_review_node(capabilities.recorder, advance_lineage=True),
    )
    graph.add_node("await_answers", await_answers_node())
    graph.add_node("revise_case", revise_case_node(capabilities.cases))
    graph.add_node(
        "select_candidates_for_rejudgement",
        select_rejudgements_node(capabilities.rejudgements),
    )
    graph.add_node(
        "compose_final_review",
        compose_review_node(capabilities.composer, waiting=False),
    )
    graph.add_node("record_review", record_review_node(capabilities.recorder))

    graph.add_edge(START, "load_context")
    graph.add_edge("load_context", "analyze_repository")
    graph.add_edge("analyze_repository", "detect_candidates")
    graph.add_edge("detect_candidates", "calculate_delta")
    graph.add_edge("calculate_delta", "select_initial_candidates")
    graph.add_edge("select_initial_candidates", "load_policy_corpus")
    graph.add_conditional_edges("load_policy_corpus", _dispatch_candidates)
    graph.add_edge("review_candidate", "generate_questions")
    graph.add_conditional_edges("generate_questions", _after_questions)
    graph.add_edge("compose_waiting_review", "record_waiting_review")
    graph.add_edge("record_waiting_review", "await_answers")
    graph.add_edge("await_answers", "revise_case")
    graph.add_conditional_edges("revise_case", _after_case_revision)
    graph.add_conditional_edges("select_candidates_for_rejudgement", _dispatch_candidates)
    graph.add_edge("compose_final_review", "record_review")
    graph.add_edge("record_review", END)
    return graph.compile(checkpointer=checkpointer)  # type: ignore[arg-type]
