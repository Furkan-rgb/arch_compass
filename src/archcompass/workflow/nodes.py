"""One-capability graph nodes; all sequencing lives in :mod:`workflow.graph`."""

from __future__ import annotations

import logging
from collections.abc import Callable, Mapping
from dataclasses import replace
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

    It writes investigations and nothing else. Findings are `rejudge_investigated`'s to
    write, which is the whole of why this node is allowed to exist: it establishes facts and
    has no opinion about them.
    """

    def investigate_hinges(state: ReviewState) -> dict[str, object]:
        if not investigator.supports_tools():
            return {}
        # Ordered by the candidate list rather than by the findings mapping, like every
        # other node that reads it: two runs over one review must investigate the same
        # findings in the same order, and a dict's order is whichever branch finished first.
        #
        # Narrowed to what this round judged. `candidates` includes findings carried
        # unchanged from the previous review (`delta.unchanged`), and a carried finding's
        # hinge passes this filter while nothing in this round retrieved policies for it —
        # so it was investigated, could not then be re-judged, and its record reached the
        # reader attached to a verdict it had never been weighed against. Investigating
        # exactly what can be re-judged keeps the two passes over one set.
        judged_here = {str(candidate.id) for candidate in state["selected_candidates"]}
        held = [
            (str(candidate.id), state["findings"][str(candidate.id)])
            for candidate in state["candidates"]
            if str(candidate.id) in judged_here
            and str(candidate.id) in state["findings"]
            and state["findings"][str(candidate.id)].hinge
        ][:MAX_INVESTIGATED_FINDINGS]
        if not held:
            return {}
        investigations: dict[str, RecordedInvestigation] = {}
        for candidate_id, finding in held:
            try:
                record = investigator.investigate(
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
            if record is not None:
                investigations[candidate_id] = record
        # No findings written. This node used to return them changed, because the
        # investigator returned a verdict; it establishes facts now, and `rejudge_investigated`
        # is what turns those facts into a verdict.
        return {"investigations": investigations}

    return investigate_hinges


def rejudge_investigated_node(judge: ArchitectureJudge) -> Node:
    """The second judgement, on the candidates whose hinge was investigated.

    The step that makes `ArchitectureJudge` the only thing in the system that can say what a
    candidate means. Judging produced the hinge; the investigation answered what it could of
    it; this asks the same judge again, with the same candidate, the same case and the same
    retrieved policies, plus what was looked up.

    The policies are reused rather than retrieved again, and that is the point of doing this
    here rather than through the general rejudgement path: nothing about the *question* has
    changed. Answering a clarification is different — it revises the case, which is new
    intent, and that path retrieves afresh.

    A candidate is re-judged only where lookups actually happened. An investigation that was
    withheld before it began, or that failed before its first lookup, leaves the judge with
    exactly the inputs it had the first time, and asking it again would spend a model call to
    be told the same thing. Derived from the record rather than flagged on it.

    And only for candidates this round judged. Both mappings read here outlive a round, so
    reading either one whole reaches back into an earlier one.
    """

    def rejudge_investigated(state: ReviewState) -> dict[str, object]:
        findings: dict[str, Finding] = {}
        # This round's work only. `investigations` accumulates across rounds — it is a merged
        # mapping seeded once and never cleared — so reading all of it re-judged candidates
        # the current round had already settled, against a record from before the answers
        # arrived, and stamped the result with that older record's identity.
        for candidate in state["selected_candidates"]:
            candidate_id = str(candidate.id)
            record = state["investigations"].get(candidate_id)
            retrieval = state["retrievals"].get(candidate_id)
            if record is None or not record.lookups or retrieval is None:
                continue
            try:
                finding = judge.judge(candidate, state["case"], retrieval, record)
            except Exception:
                # Same bargain as the investigation itself: a second judgement that could
                # not be made leaves the first one standing, hinge and all, and the review
                # goes on to ask the person it was always going to ask.
                _log.warning(
                    "The investigated hinge on %s was not re-judged",
                    candidate_id,
                    exc_info=True,
                )
                continue
            findings[candidate_id] = replace(
                finding, investigation_identity=record.identity
            )
        return {"findings": findings}

    return rejudge_investigated


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
            # ERROR rather than WARNING, and naming what was held. Degrading here is right —
            # every candidate has already been judged and letting this propagate throws that
            # away — but "the review settled everything" and "the review could not put its
            # uncertainty into words" both leave with no questions, and only one of them is
            # a review finishing properly.
            # Counted as findings held, not as questions lost. How many of them the
            # generator would have asked about is the generator's own cap and not this
            # node's to know — naming a number here would be this layer guessing at
            # another's, and the fact that matters is the same either way: this review has
            # uncertainty it is about to seal the case over.
            _log.error(
                "This review asked nothing this round, and %d finding(s) are held with an "
                "open hinge",
                sum(1 for finding in ordered if finding.hinge),
                exc_info=True,
            )
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
        # A round that recorded nothing opens nothing.
        #
        # Not reachable through the product's own resume path, and kept anyway. `resume`
        # builds one `Answer` per pending question — filling every omission with an explicit
        # skip — so a submission that answers nothing still arrives as a full set of skips
        # and does open a revision. This is the guard for a caller driving the graph
        # directly, and for a waiting review that somehow asked nothing.
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

    A review that asked nothing opened no revision and writes none: there is no new human
    context to file, and a revision holding none would be a number a later review had to
    read past.

    A review that asked and was skipped through does write one. A skip is an answer — it
    records that a person was shown the question and declined it, which is exactly what a
    later review needs to know in order not to ask it again — so the revision it opens holds
    skips and is worth its number.
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
