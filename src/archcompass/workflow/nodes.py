"""One-capability graph nodes; all sequencing lives in :mod:`workflow.graph`."""

from __future__ import annotations

import logging
from collections.abc import Callable, Mapping
from typing import cast

from langgraph.config import get_stream_writer
from langgraph.types import interrupt

from archcompass.domain import Answer, Finding, RecordedInvestigation
from archcompass.ports.capabilities import (
    ArchitectureJudge,
    BatchArchitectureJudge,
    BatchOutcome,
    CandidateDetector,
    CaseReviser,
    ContextLoader,
    HingeInvestigator,
    InitialCandidateSelector,
    JudgementRequest,
    PolicyCorpus,
    PolicyRetriever,
    QuestionGenerator,
    RejudgementSelector,
    RepositoryAnalyzer,
    ReviewComposer,
    ReviewDraft,
    ReviewRecorder,
    ReviewSynopsisWriter,
    RevisionCalculator,
)
from archcompass.workflow.state import ReviewState

_log = logging.getLogger(__name__)

#: How many hinged findings one round will investigate. A sequencing decision, and
#: therefore the graph's rather than an adapter's: investigating is interactive by
#: construction, so a review where everything hinged is a run of unbatched calls in
#: front of a waiting reader. The ones past the ceiling keep their hinges and reach a
#: person exactly as they did before this existed.
MAX_INVESTIGATED_FINDINGS = 8

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
            "case_opened": False,
            "excluded_equivalence_keys": frozenset(
                answer.question.equivalence_key for answer in loaded.case.answers
            ),
            "retrievals": {},
            "findings": {},
            "investigations": {},
            "stop_requested": False,
            "synopsis": None,
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


def review_candidates_node(retriever: PolicyRetriever, judge: ArchitectureJudge) -> Node:
    """Retrieve for every selected candidate, then judge them in one submission.

    The same two steps the per-candidate subgraph performs, done for the whole selection at
    once. It exists because a batch has to be one request: a fan-out cannot submit a batch
    without every branch first waiting for every other, which is a deadlock wearing a
    barrier's clothes. Retrieval stays a loop because it is local — a SQLite index and an
    embedding call, not a metered judgement.
    """

    def review_candidates(state: ReviewState) -> dict[str, object]:
        selected = state["selected_candidates"]
        if not selected:
            return {"retrievals": {}, "findings": {}}
        if not isinstance(judge, BatchArchitectureJudge):
            raise TypeError("this node was routed to without a judge that can batch")

        requests = tuple(
            JudgementRequest(
                candidate=candidate,
                case=state["case"],
                policies=retriever.retrieve(candidate, state["case"], state["corpus"]),
            )
            for candidate in selected
        )
        # What the provider actually did, told to whoever is watching the run the moment it
        # does it. A custom stream event rather than part of this node's return value,
        # because the return value arrives when judging is over and the whole reason anybody
        # wants to know is that a batch takes an hour. The node is the right place for it:
        # the graph's streaming belongs to the workflow layer, and a reasoning adapter that
        # imported it would be a judge that knows what a run is.
        writer = get_stream_writer()

        def observed(outcome: BatchOutcome) -> None:
            writer({"batch": outcome})

        findings = judge.judge_all(requests, observe=observed)
        if len(findings) != len(requests):
            raise ValueError(
                f"the judge answered {len(findings)} of {len(requests)} candidates"
            )
        return {
            "retrievals": {
                str(item.candidate.id): item.policies for item in requests
            },
            "findings": {
                str(item.candidate.id): finding
                for item, finding in zip(requests, findings, strict=True)
            },
        }

    return review_candidates


def investigate_hinges_node(investigator: HingeInvestigator) -> Node:
    """The findings that stopped to ask a person, checked against the repository first.

    Its own node rather than something the judge does, because it is a second and
    differently bounded conversation with a model, and a graph whose nodes are its
    capabilities is how that stays visible. It runs after judgement because a hinge is what
    judgement produces, and before `generate_questions` because a hinge the repository
    settled is not a question worth anybody's interruption.

    It writes back into `findings` under the same keys, so a hinge nothing could settle
    reaches the generator exactly as it did before this existed — which is why the
    unresolved path needed no new code anywhere downstream.
    """

    def investigate_hinges(state: ReviewState) -> dict[str, object]:
        if not investigator.supports_tools():
            return {}
        # Ordered by the candidate list rather than by the findings mapping, like every
        # other node that reads it: two runs over one review must investigate the same
        # findings in the same order, and a dict's order is whichever branch finished first.
        held = [
            (str(candidate.id), state["findings"][str(candidate.id)])
            for candidate in state["candidates"]
            if str(candidate.id) in state["findings"]
            and state["findings"][str(candidate.id)].hinge
        ][:MAX_INVESTIGATED_FINDINGS]
        if not held:
            return {}
        findings: dict[str, Finding] = {}
        investigations: dict[str, RecordedInvestigation] = {}
        for candidate_id, finding in held:
            try:
                investigated = investigator.investigate(
                    finding,
                    state["case"],
                    repository=state["repository"],
                    atlas=state["atlas"],
                )
            except Exception:
                # An investigation is an improvement to a question. Losing one must never
                # cost the review the question belongs to, so the hinge stands and the run
                # goes on to ask it.
                _log.warning(
                    "The hinge on %s was not investigated", candidate_id, exc_info=True
                )
                continue
            findings[candidate_id] = investigated.finding
            if investigated.investigation is not None:
                investigations[candidate_id] = investigated.investigation
        return {"findings": findings, "investigations": investigations}

    return investigate_hinges


def generate_questions_node(generator: QuestionGenerator) -> Node:
    """The round's questions, or none, but never the loss of the review that earned them.

    A clarification round is an improvement to a review. By the time this node runs every
    candidate has been retrieved for, judged and investigated, and letting a failure here
    propagate throws all of that away to save nothing — which is exactly what happened when
    a model named a finding this node had no question for. So it degrades like
    `investigate_hinges` above it: no questions, a warning, and a review that finishes
    instead of one that failed.
    """

    def generate_questions(state: ReviewState) -> dict[str, object]:
        ordered = tuple(
            state["findings"][str(candidate.id)]
            for candidate in state["candidates"]
            if str(candidate.id) in state["findings"]
        )
        try:
            questions = generator.generate(
                state["case"],
                ordered,
                round=state["round"],
                excluded_equivalence_keys=state["excluded_equivalence_keys"],
            )
        except Exception:
            _log.warning("This review asked nothing this round", exc_info=True)
            return {"questions": ()}
        return {"questions": questions}

    return generate_questions


def write_synopsis_node(synopsist: ReviewSynopsisWriter, *, waiting: bool) -> Node:
    """The paragraph the report opens on, written after every verdict is in.

    Its own node rather than something the composer does, because it is the one place in the
    sequence where the model is asked about the review as a whole rather than about a
    candidate, and a graph whose nodes are the capabilities is how that stays visible. It
    runs before both composers: a waiting review is a document somebody may hand over
    part-way through a clarification round, and it deserves the same opening as a final one.
    """

    def write_synopsis(state: ReviewState) -> dict[str, object]:
        ordered = tuple(
            state["findings"][str(candidate.id)]
            for candidate in state["candidates"]
            if str(candidate.id) in state["findings"]
        )
        return {
            "synopsis": synopsist.write(
                state["case"],
                ordered,
                questions=state["questions"],
                delta=state["delta"],
                previous=state["previous_review"],
                waiting=waiting,
            )
        }

    return write_synopsis


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
            round=state["round"],
            repository=state["repository"],
            atlas=state["atlas"],
            case=state["case"],
            findings=ordered_findings,
            questions=state["questions"],
            delta=state["delta"],
            previous=state["previous_review"],
            retrievals=ordered_retrievals,
            investigations=tuple(
                state["investigations"][str(candidate.id)]
                for candidate in state["candidates"]
                if str(candidate.id) in state["investigations"]
            ),
            synopsis=state["synopsis"],
        )
        return {"draft": draft, "review": composer.compose(draft, waiting=waiting)}

    return compose_review


def record_review_node(recorder: ReviewRecorder) -> Node:
    """File a snapshot of this review. It never advances `previous_review`.

    `previous_review` is the review this one is judged against, and a review is not judged
    against itself. It used to be moved on here when a waiting snapshot was filed, which
    gave the next snapshot of the same review a fresh sequence number and put one review on
    the rail as two.
    """

    def record_review(state: ReviewState) -> dict[str, object]:
        return {"review": recorder.record(state["review"])}

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
    """Record a round's answers on this review's case revision.

    The revision is opened once, here, the first time there are answers to put on it — and
    every later round adds to that same revision rather than starting another. Which round
    this is is the graph's to know, so the decision is on this side of the capability.
    """

    def revise_case(state: ReviewState) -> dict[str, object]:
        case = state["case"]
        opened = state["case_opened"]
        # A round that recorded nothing opens nothing. Every question a waiting review asked
        # comes back answered or explicitly skipped, so this is the reader who stopped the
        # review rather than answered it, and stopping is not human context.
        if not state["pending_answers"]:
            return {"previous_case": case, "round": state["round"] + 1}
        if not opened:
            case = reviser.open(case)
            opened = True
        revised = reviser.revise(case, state["pending_answers"])
        excluded = state["excluded_equivalence_keys"] | {
            answer.question.equivalence_key for answer in state["pending_answers"]
        }
        return {
            "previous_case": state["case"],
            "case": revised,
            "case_opened": opened,
            "round": state["round"] + 1,
            "excluded_equivalence_keys": frozenset(excluded),
        }

    return revise_case


def seal_case_node(reviser: CaseReviser) -> Node:
    """Write the revision this review opened, once, on the way out.

    A review that asked nothing, or that nobody answered, opened no revision and writes
    none: there is no new human context to file, and a revision holding none would be a
    number a later review had to read past.
    """

    def seal_case(state: ReviewState) -> dict[str, object]:
        if not state["case_opened"]:
            return {}
        return {"case": reviser.seal(state["case"])}

    return seal_case


def select_rejudgements_node(selector: RejudgementSelector) -> Node:
    def select_rejudgements(state: ReviewState) -> dict[str, object]:
        return {
            "selected_candidates": selector.select(
                state["candidates"], state["previous_case"], state["case"]
            )
        }

    return select_rejudgements
