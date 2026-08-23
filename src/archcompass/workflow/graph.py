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

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Literal

from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph
from langgraph.types import Send

from archcompass.domain import (
    ArchitectureCase,
    Finding,
    Question,
    RecordedInvestigation,
    RepositoryAtlas,
    RepositoryRef,
    Review,
    ReviewDelta,
)
from archcompass.ports.capabilities import (
    ArchitectureJudge,
    BatchArchitectureJudge,
    CandidateDetector,
    CaseReviser,
    ContextLoader,
    HingeInvestigator,
    InitialCandidateSelector,
    PolicyCorpus,
    PolicyRetriever,
    QuestionGenerator,
    RepositoryAnalyzer,
    ReviewComposer,
    ReviewRecorder,
    ReviewSynopsis,
    ReviewSynopsisWriter,
    RevisionCalculator,
)
from archcompass.workflow.nodes import (
    analyze_repository_node,
    await_answers_node,
    calculate_delta_node,
    compose_review_node,
    detect_candidates_node,
    generate_questions_node,
    investigate_hinges_node,
    judge_candidate_node,
    load_context_node,
    load_policy_corpus_node,
    record_review_node,
    rejudge_investigated_node,
    retrieve_policy_set_node,
    review_candidates_node,
    revise_case_node,
    seal_case_node,
    select_initial_candidates_node,
    select_rejudgements_node,
    write_synopsis_node,
)
from archcompass.workflow.state import CandidateReviewOutput, ReviewInput, ReviewState


class _NoReviewSynopsis:
    """The seam filled when nothing is going to write a summary.

    A workspace can compose a review without a reasoning model available — a rerun from the
    CLI against cached findings, a test harness, a deployment that has not selected one — and
    a report that fails to compose because its opening paragraph could not be written would
    be the tail wagging the dog. The report simply opens on its counts, as it did before.
    """

    def write(
        self,
        case: ArchitectureCase,
        findings: tuple[Finding, ...],
        *,
        questions: tuple[Question, ...],
        delta: ReviewDelta,
        previous: Review | None,
        waiting: bool,
    ) -> ReviewSynopsis | None:
        return None


class _NoHingeInvestigation:
    """The seam filled when nothing is going to look anything up.

    Not every model can call tools and a workspace may have selected one that cannot, so
    the absence answer here is not a failure — it is the finding, unchanged, and a hinge
    that goes to a person the way every hinge did before this existed. `supports_tools`
    answering False is what keeps the node cheap: it returns before it reads a finding.
    """

    def supports_tools(self) -> bool:
        return False

    def investigate(
        self,
        finding: Finding,
        case: ArchitectureCase,
        *,
        repository: RepositoryRef,
        atlas: RepositoryAtlas,
    ) -> RecordedInvestigation | None:
        del finding, case, repository, atlas
        return None


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
    cases: CaseReviser
    composer: ReviewComposer
    recorder: ReviewRecorder
    # Defaulted, unlike its peers, and therefore last: every other capability is something a
    # review cannot be produced without, and this one writes the paragraph the report opens
    # on. A workspace or a test with no use for it composes the same review with a report
    # that opens on its counts, which is what the report did before this existed.
    synopsist: ReviewSynopsisWriter = field(default_factory=_NoReviewSynopsis)
    # Defaulted for the same reason its neighbour is, and for one more: a review whose
    # hinges were never checked is exactly the review this product produced yesterday.
    # A workspace on a model that cannot call tools asks its questions the way it
    # always asked them.
    investigator: HingeInvestigator = field(default_factory=_NoHingeInvestigation)


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


def _dispatch_candidates(
    capabilities: ReviewWorkflowCapabilities,
) -> Callable[[ReviewState], list[Send] | str]:
    """One candidate per branch, or all of them in one node when a batch is available.

    The choice is made here, at dispatch, rather than when the graph was built: which model
    is selected can change while the workspace is running, and only the batch-capable
    providers can be asked for every verdict at once.
    """

    def dispatch(state: ReviewState) -> list[Send] | str:
        if not state["selected_candidates"]:
            return "generate_questions"
        judge = capabilities.judge
        if isinstance(judge, BatchArchitectureJudge) and judge.supports_batch():
            return "review_candidates"
        # Three keys, not the whole state, and the narrower payload is a correctness fix
        # before it is anything else.
        #
        # `{**state, ...}` handed every branch the accumulated `findings`, and the branch
        # handed them straight back: the subgraph's output schema projects its final merged
        # state, so each branch returned every finding it had been given plus its own.
        # `merge_mappings` applies those writes in task order, so in a clarification round —
        # where the round selects every candidate again and `findings` already holds
        # round one's verdicts for all of them — every branch but the last had its fresh
        # verdict overwritten by a sibling's stale copy. Measured on `boundary-review` with
        # the hinge lookups off: five of six answered candidates came back with their
        # round-one verdict and the review asked again. The model calls were made and paid
        # for and then thrown away.
        #
        # It stayed invisible because the hinge pass that runs next re-judged exactly the
        # findings that reverted, so with the pass on — the default — the round looked right.
        # (That re-judgement is `rejudge_investigated` now; `investigate_hinges` establishes
        # facts and writes no findings at all.) It is also why no test caught it: every graph
        # test judges one candidate, and one candidate is the case this cannot happen in.
        #
        # What the subgraph reads is all that goes: `retrieve_policy_set` needs the
        # candidate, the case and the corpus; `judge_candidate` needs the candidate and the
        # retrieval its neighbour just wrote. Nothing in it reads the atlas or the findings.
        # The size is the second reason and still worth having — a `Send` payload is
        # checkpointed per branch, and one round of six candidates fell from 21 MB of
        # `__pregel_tasks` to 1.3 MB.
        return [
            Send(
                "review_candidate",
                {
                    "candidate": candidate,
                    "case": state["case"],
                    "corpus": state["corpus"],
                },
            )
            for candidate in state["selected_candidates"]
        ]

    return dispatch


def _after_questions(
    state: ReviewState,
) -> Literal["seal_case", "write_waiting_synopsis"]:
    if (
        not state["questions"]
        or state["ci"]
        or state["round"] >= 3
        or state["stop_requested"]
    ):
        return "seal_case"
    return "write_waiting_synopsis"


def _after_case_revision(
    state: ReviewState,
) -> Literal["seal_case", "select_candidates_for_rejudgement"]:
    return "seal_case" if state["stop_requested"] else "select_candidates_for_rejudgement"


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
    graph.add_node(
        "review_candidates",
        review_candidates_node(capabilities.retriever, capabilities.judge),
    )
    graph.add_node(
        "investigate_hinges", investigate_hinges_node(capabilities.investigator)
    )
    graph.add_node(
        "rejudge_investigated", rejudge_investigated_node(capabilities.judge)
    )
    graph.add_node("generate_questions", generate_questions_node(capabilities.questions))
    graph.add_node(
        "write_waiting_synopsis",
        write_synopsis_node(capabilities.synopsist, waiting=True),
    )
    graph.add_node(
        "compose_waiting_review",
        compose_review_node(capabilities.composer, waiting=True),
    )
    # `advance_lineage` stays off. A waiting snapshot is this revision mid-question, not
    # the revision before the next one — treating it as lineage is what made a review that
    # asked once occupy two numbers on the rail.
    graph.add_node(
        "record_waiting_review",
        record_review_node(capabilities.recorder),
    )
    graph.add_node("await_answers", await_answers_node())
    graph.add_node("revise_case", revise_case_node(capabilities.cases))
    graph.add_node("seal_case", seal_case_node(capabilities.cases))
    graph.add_node(
        "select_candidates_for_rejudgement",
        select_rejudgements_node(),
    )
    graph.add_node(
        "write_final_synopsis",
        write_synopsis_node(capabilities.synopsist, waiting=False),
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
    dispatch = _dispatch_candidates(capabilities)
    graph.add_conditional_edges(
        "load_policy_corpus",
        dispatch,
        ["review_candidate", "review_candidates", "generate_questions"],
    )
    # Unconditional on purpose, and the node guards itself. `review_candidate` is fanned
    # out with `Send`, and a conditional edge leaving it evaluates its predicate once
    # per branch against that branch's state — so a routing decision about the whole
    # set of findings does not belong on this edge. Both destinations reached
    # `generate_questions` anyway, so the two-way routing bought nothing.
    graph.add_edge("review_candidate", "investigate_hinges")
    graph.add_edge("review_candidates", "investigate_hinges")
    # The second judgement, and the reason it is here rather than through
    # `select_candidates_for_rejudgement`: that path re-enters `review_candidate`, whose own
    # edge leads back to `investigate_hinges`, so a review would investigate what it had just
    # investigated. A dedicated edge needs no loop guard and puts "judged, looked, judged
    # again" in the graph where it can be read.
    graph.add_edge("investigate_hinges", "rejudge_investigated")
    graph.add_edge("rejudge_investigated", "generate_questions")
    graph.add_conditional_edges("generate_questions", _after_questions)
    # Every way out of the loop passes through here, which is why the revision this review
    # opened is written in one place rather than at each exit.
    graph.add_edge("seal_case", "write_final_synopsis")
    graph.add_edge("write_waiting_synopsis", "compose_waiting_review")
    graph.add_edge("write_final_synopsis", "compose_final_review")
    graph.add_edge("compose_waiting_review", "record_waiting_review")
    graph.add_edge("record_waiting_review", "await_answers")
    graph.add_edge("await_answers", "revise_case")
    graph.add_conditional_edges("revise_case", _after_case_revision)
    graph.add_conditional_edges(
        "select_candidates_for_rejudgement",
        dispatch,
        ["review_candidate", "review_candidates", "generate_questions"],
    )
    graph.add_edge("compose_final_review", "record_review")
    graph.add_edge("record_review", END)
    return graph.compile(checkpointer=checkpointer)  # type: ignore[arg-type]
