"""Deterministic model substitutes for tests and reproducible evaluations."""

from __future__ import annotations

import re
from collections.abc import Callable
from typing import ClassVar, Final

from archcompass.configuration import ReasoningModelConfig
from archcompass.domain.atlas import (
    FindingCandidate,
    FindingPattern,
)
from archcompass.domain.case import (
    ArchitectureCase,
    CaseField,
)
from archcompass.domain.knowledge import MethodKnowledge
from archcompass.domain.model_catalog import AvailableModel, ProbeResult
from archcompass.domain.policy import PolicyDocument
from archcompass.domain.review import (
    BoundaryReview,
    CandidateVerdict,
    OpenQuestion,
    OverviewStatement,
    PolicyBearing,
    ReviewedBoundary,
    ReviewEvidence,
    ReviewOverview,
    ReviewStatus,
    VerdictHinge,
)
from archcompass.domain.review_conversation import ReviewAnswer, ReviewMessage
from archcompass.ports.model_catalog import ProviderDefaults, ProviderDescriptor
from archcompass.ports.reasoning import ReasoningTask, StreamingAnswerReasoner

PROVIDER_NAME: Final = "fake"

#: What this substitute answers to. It matches `model_identity` rather than whatever a
#: fixture happens to name, because reporting a model it is not would be the one lie a
#: chooser cannot afford.
DETERMINISTIC_MODEL = "deterministic-architecture-v4"


def probe_deterministic(defaults: ProviderDefaults) -> ProbeResult:
    """Always reachable, with exactly one model — its own.

    One thinking mode, and it is `None`: this substitute reaches no model at all, so
    claiming it reasons on request would be the same lie as reporting a model it is not.
    """

    del defaults
    return ProbeResult(
        available=True,
        models=[AvailableModel(name=DETERMINISTIC_MODEL, label="deterministic substitute")],
    )


def _atlas_map_marker(evidence: ReviewEvidence) -> str:
    """The map counted, never rendered — the same treatment background gets.

    A test can prove the pinned structure reached a stage, and which of its three states
    it arrived in, without this substitute pretending to read a repository's shape.
    """

    if evidence.atlas_map is None:
        return ""
    if evidence.atlas_map.unavailable:
        return " Atlas map unavailable."
    return f" Atlas map: {len(evidence.atlas_map.modules)} modules."


class DeterministicReasoningProvider:
    _PROMPTS: ClassVar[dict[ReasoningTask, str]] = {
        ReasoningTask.JUDGE_FINDING_CANDIDATE: "judge-finding-candidate:v4",
        ReasoningTask.ELICIT_QUESTIONS: "elicit-questions:v1",
        ReasoningTask.SUMMARISE_REVIEW: "summarise-review:v3",
        ReasoningTask.ANSWER_REVIEW_QUESTION: "answer-review-question:v1",
        ReasoningTask.DISCUSS_OPEN_QUESTION: "discuss-open-question:v1",
    }

    @property
    def model_identity(self) -> str:
        return "fake:deterministic-architecture-v4"

    def prompt_identity(self, task: ReasoningTask) -> str:
        return self._PROMPTS[task]

    def judge_finding_candidate(
        self,
        case: ArchitectureCase,
        candidate: FindingCandidate,
        policies: list[PolicyDocument],
    ) -> CandidateVerdict:
        # The one call a substitute can make from the measurements alone: indirection
        # that nothing depends on is in front of nothing. Every other candidate is
        # reported as fine, which is both the honest default here and the answer a real
        # model should give most of the time.
        dependants = next(
            (
                item.value
                for item in candidate.measurements
                if item.name == "dependants_of_abstraction"
            ),
            None,
        )
        material = dependants == 0
        # Bearing is derived from the candidate's own pattern words against each policy's
        # title and tags. Recognising particular policy IDs would make the substitute a
        # function of the bundled corpus rather than of its inputs.
        words = {word for word in candidate.pattern.value.split("_") if len(word) > 3}
        bearings = [
            PolicyBearing(
                policy_id=policy.id,
                policy_title=policy.title,
                how=(
                    f"{policy.title} names the same shape this candidate reports: "
                    f"{candidate.summary}"
                ),
            )
            for policy in policies
            if any(word in " ".join([policy.title, *policy.tags]).lower() for word in words)
        ]
        # Derived from the case, which is what a hinge is about: a verdict reached without
        # being told what is coming rests on the assumption that nothing is. A fixture that
        # always produced a hinge — or never did — would make every assertion about
        # elicitation vacuous, so this turns on a field the test can set either way.
        #
        # An answer already recorded counts, exactly as the real contract requires: a
        # clarification bearing on expected_future_changes carries the force of an entry in
        # that list, so a reader who has been asked about the future and replied is not asked
        # again. That is what closes the loop, and reading only the list would leave the
        # substitute hinging for ever on questions it had already had answered — which is the
        # failure a fixture is least likely to be caught doing.
        #
        # Restricted to indirection, because that is the only one of the three shapes where
        # a coming change is the question. Whether two modules state one fact or two is
        # settled by what the copies mean, and no amount of future variation changes it. The
        # substitute obeys the rule its own contract states here — a hinge on every boundary
        # is a hinge on none — so an offline run does not read as an advisor hedging
        # everything it says.
        told_about_the_future = bool(case.expected_future_changes) or any(
            item.bears_on is CaseField.EXPECTED_FUTURE_CHANGES for item in case.clarifications
        )
        hinge = (
            VerdictHinge(
                unknown=(
                    "The case names no expected future change, so nothing states whether "
                    "the variation this boundary would absorb is coming."
                ),
                if_confirmed=(
                    "The boundary stands in front of a change that is actually coming and "
                    "should stay as it is."
                ),
                if_denied=(
                    "Nothing arrives for the boundary to absorb, and it should be removed."
                ),
            )
            if candidate.pattern is FindingPattern.SOLE_IMPLEMENTATION
            and not told_about_the_future
            else None
        )
        return CandidateVerdict(
            candidate_id=candidate.candidate_id,
            material=material,
            hinge=hinge,
            rationale=(
                (
                    "Nothing in this snapshot depends on the abstraction, so the boundary "
                    "currently sits in front of a single concrete implementation with no "
                    "caller reading the contract."
                )
                if material
                else (
                    f"{dependants if dependants is not None else 'Several'} references reach "
                    "the abstraction, so the boundary is load-bearing here and the "
                    "implementation count alone does not establish a problem."
                )
            ),
            policy_bearings=bearings,
            recommended_response=(
                "Name the concrete implementation directly until a second one exists."
                if material
                else ""
            ),
        )

    def elicit_questions(
        self,
        case: ArchitectureCase,
        boundaries: list[ReviewedBoundary],
    ) -> list[OpenQuestion]:
        # Consolidated the way the real stage is asked to consolidate: boundaries naming the
        # same unknown become one question citing all of them. Grouping by the unknown's own
        # text is cruder than a model reading them for sense, but it is the same operation,
        # so a test that asserts one question over four boundaries is asserting the
        # behaviour rather than a fixture's shape.
        by_unknown: dict[str, list[ReviewedBoundary]] = {}
        for item in boundaries:
            if item.hinge is not None:
                by_unknown.setdefault(item.hinge.unknown, []).append(item)
        return [
            OpenQuestion(
                reference=f"Q-{position}",
                # Composed from the boundaries themselves rather than from a fixed sentence,
                # so a test that asserts the observation names what was examined is asserting
                # that the field carries evidence at all.
                what_the_review_saw=(
                    "Examined "
                    + ", ".join(item.candidate.summary for item in sharing)
                    + ". The case does not settle this either way."
                ),
                unknown=unknown,
                # One sentence per distinct consequence, not one per boundary. Boundaries
                # that move the same way say so once: repeating an identical clause six
                # times is how a consolidated question reads as though nothing was merged.
                why_it_matters=(
                    f"{len(sharing)} of {len(boundaries)} verdicts move on this. "
                    + " ".join(
                        dict.fromkeys(item.hinge.if_denied for item in sharing if item.hinge)
                    )
                ),
                question=(
                    "Is any of that variation actually coming, or is the current shape "
                    "what this repository will keep?"
                ),
                # Offered on the first question and on no other. In a whole run through
                # this substitute the guard never fires: the hinge's `unknown` is one
                # constant, so consolidation yields exactly one question, and it carries
                # options. The empty set — the shape most questions really have — is met
                # by the unit tests that build questions directly, not by driving a page
                # through this provider.
                answer_options=(
                    [
                        "That variation is coming.",
                        "The current shape is what this repository will keep.",
                    ]
                    if position == 1
                    else []
                ),
                answer_belongs_in=CaseField.EXPECTED_FUTURE_CHANGES,
                supporting_references=[item.reference for item in sharing],
            )
            for position, (unknown, sharing) in enumerate(by_unknown.items(), start=1)
        ]

    def summarise_review(
        self,
        case: ArchitectureCase,
        boundaries: list[ReviewedBoundary],
    ) -> ReviewOverview:
        # Composed from the verdicts themselves, so the substitute cites boundaries that
        # genuinely carry what each statement says. A fixture that always cited everything
        # would make the grounding assertions in tests vacuous.
        material = [item for item in boundaries if item.material]
        cleared = [item for item in boundaries if not item.material]
        themes: list[OverviewStatement] = []
        if material:
            themes.append(
                OverviewStatement(
                    text=(
                        f"{len(material)} of {len(boundaries)} were found not to be "
                        "earning their place."
                    ),
                    supporting_references=[item.reference for item in material],
                )
            )
        if cleared:
            themes.append(
                OverviewStatement(
                    text=(
                        f"{len(cleared)} of {len(boundaries)} were found to be earning "
                        "their place."
                    ),
                    supporting_references=[item.reference for item in cleared],
                )
            )
        # Relayed from the candidates rather than described here: the detector states what
        # it could not see, and a double that restated it in its own words would be
        # asserting the detector's vocabulary instead of passing it through.
        stated: list[str] = []
        for item in boundaries:
            if item.candidate.limitations and item.candidate.limitations not in stated:
                stated.append(item.candidate.limitations)
        # No questions. The real stage's schema has no field for one — asking belongs to the
        # first pass, and this runs only on the second — so a substitute that produced them
        # here would let a test pass against a shape the provider cannot return.
        return ReviewOverview(
            situation=(
                f"{case.title}. {case.problem_statement}"
                if case.problem_statement
                else case.title
            ),
            themes=themes,
            recommended_sequence=[
                OverviewStatement(
                    text=material[0].recommended_response,
                    supporting_references=[item.reference for item in material],
                )
            ]
            if material and material[0].recommended_response
            else [],
            limits=" ".join(stated) or "The detector stated no limitation.",
        )

    def stream_review_answer(
        self,
        review: BoundaryReview,
        evidence: ReviewEvidence,
        history: list[ReviewMessage],
        question: str,
        knowledge: MethodKnowledge,
        on_prose: Callable[[str], None],
    ) -> ReviewAnswer:
        """The same answer, handed over a word at a time.

        Implemented here so the streaming path has something to run against without a live
        model: the route, the application service and the browser all behave as they do
        against a real provider, and the assertion that a preview never becomes the stored
        record is checkable offline.

        Split on whitespace rather than by characters or tokens. A fragment boundary is
        arbitrary in every real transport too, and words make a test's expectations readable
        without pretending to imitate how any particular provider chunks its output.
        """

        answer = self.answer_review_question(review, evidence, history, question, knowledge)
        for index, word in enumerate(answer.answer.split(" ")):
            on_prose(word if index == 0 else f" {word}")
        return answer

    def answer_review_question(
        self,
        review: BoundaryReview,
        evidence: ReviewEvidence,
        history: list[ReviewMessage],
        question: str,
        knowledge: MethodKnowledge,
    ) -> ReviewAnswer:
        report = review.report
        if report is None:
            raise ValueError("A review without a report cannot be questioned")
        # Grounded on whichever boundaries share a word with the question, which is a
        # function of the inputs rather than of a fixture. A substitute that always cited
        # everything would make the grounding assertions in tests vacuous.
        words = {word for word in re.findall(r"[a-z0-9]+", question.casefold()) if len(word) > 3}
        supporting = [
            item
            for item in report.reviewed
            if words & set(re.findall(r"[a-z0-9]+", item.candidate.summary.casefold()))
        ]
        # The background is counted but never cited. Counting it makes the wiring
        # observable — a test can prove the whole corpus reached this stage — while leaving
        # `supporting_references` boundaries-only, which is the rule the real stage obeys.
        consulted = (
            f" Background consulted: the method primer; policy corpus unavailable: "
            f"{knowledge.policy_corpus_unavailable}"
            if knowledge.method and knowledge.policy_corpus_unavailable
            else (
                f" Background consulted: the method primer and {len(knowledge.policies)} "
                "policies, whole."
                if knowledge.method
                else ""
            )
        )
        # Counted rather than quoted, as the background already is: a test can then prove
        # the recorded spans reached this stage without the substitute pretending to reason
        # about the code at them.
        shown = (
            f" Source shown for "
            f"{len({x.reference for x in evidence.excerpts if x.text})} boundaries."
        )
        # Same treatment for the detector's structure: counting the boundaries that carry
        # recorded relationships proves the wiring without pretending to read edges.
        structured = (
            f" Structure shown for "
            f"{len([x for x in report.reviewed if x.candidate.relationships])} boundaries "
            "with recorded relationships."
        )
        atlas_map = _atlas_map_marker(evidence)
        return ReviewAnswer(
            answer=(
                f"{report.headline}{shown}{structured}{atlas_map} "
                + (
                    "The boundaries this question touches are: "
                    + "; ".join(item.candidate.summary for item in supporting)
                    if supporting
                    else "This review does not cover what the question asks about."
                )
                + consulted
                + f" (turn {len(history) + 1})"
            ),
            supporting_references=[item.reference for item in supporting],
        )

    def stream_open_question_discussion(
        self,
        review: BoundaryReview,
        evidence: ReviewEvidence,
        question: OpenQuestion,
        history: list[ReviewMessage],
        asked: str,
        knowledge: MethodKnowledge,
        on_prose: Callable[[str], None],
    ) -> ReviewAnswer:
        answer = self.discuss_open_question(
            review, evidence, question, history, asked, knowledge
        )
        for index, word in enumerate(answer.answer.split(" ")):
            on_prose(word if index == 0 else f" {word}")
        return answer

    def discuss_open_question(
        self,
        review: BoundaryReview,
        evidence: ReviewEvidence,
        question: OpenQuestion,
        history: list[ReviewMessage],
        asked: str,
        knowledge: MethodKnowledge,
    ) -> ReviewAnswer:
        report = review.report
        if report is None:
            raise ValueError("A review without a report cannot be discussed")
        # The cited boundaries and no others, which is the property worth substituting for.
        # A test asserting that an uncited verdict never reaches this stage is asserting the
        # rule that lets the stage run at all while a first pass withholds its verdicts.
        cited = set(question.supporting_references)
        supporting = [item for item in report.reviewed if item.reference in cited]
        consulted = (
            f" Background consulted: the method primer; policy corpus unavailable: "
            f"{knowledge.policy_corpus_unavailable}"
            if knowledge.method and knowledge.policy_corpus_unavailable
            else (
                f" Background consulted: the method primer and {len(knowledge.policies)} "
                "policies, whole."
                if knowledge.method
                else ""
            )
        )
        # Suggested only once the reader has said something, and derived from what they
        # said rather than from a fixture. Before the first turn there is nothing they have
        # told anyone, so there is nothing honest to propose — which is the behaviour the
        # real contract is asked for and the one a test should be able to pin.
        settled = "sure" in asked.casefold() or "yes" in asked.casefold()
        # Counted rather than quoted, the way background already is: a test can then prove
        # the pinned revision reached this stage without the substitute pretending to reason
        # about what it says.
        stated = len(evidence.case.expected_future_changes) + len(evidence.case.assumptions)
        structured = len([x for x in supporting if x.candidate.relationships])
        atlas_map = _atlas_map_marker(evidence)
        # Stated only where the real payload's gate would show one: the review's own when
        # it concluded, the concluding successor's when the loop moved on without this row,
        # and a stated withholding otherwise — so a test can pin all three.
        if review.status is ReviewStatus.SUCCEEDED:
            conclusion = " Conclusion in scope."
        elif evidence.concluded_by is not None:
            conclusion = " Conclusion in scope from the concluding pass."
        else:
            conclusion = " Conclusion withheld."
        return ReviewAnswer(
            answer=(
                f"About {question.unknown} "
                f"({len([x for x in evidence.excerpts if x.text])} excerpts) "
                f"(structure shown for {structured} boundaries) "
                f"(case states {stated}): "
                + "; ".join(item.candidate.summary for item in supporting)
                + consulted
                + conclusion
                + atlas_map
                + f" (turn {len(history) + 1})"
            ),
            supporting_references=[item.reference for item in supporting],
            suggested_answer=asked.strip() if settled else "",
        )


def _build_deterministic(config: ReasoningModelConfig) -> DeterministicReasoningProvider:
    """Ignores the configuration, deliberately: there is no transport to configure."""

    del config
    return DeterministicReasoningProvider()


#: The substitute as a provider like any other, so an offline workspace chooses it the same
#: way it chooses a real one rather than through a separate path nothing else exercises.
DESCRIPTOR: Final = ProviderDescriptor(
    name=PROVIDER_NAME,
    build=_build_deterministic,
    probe=probe_deterministic,
    defaults=ProviderDefaults(),
)


#: As in `structured`: the streaming capability is found by `isinstance`, which compares
#: method names alone, so the signature is stated here to be checked. It matters more for a
#: substitute than for a real provider — this is what the streaming route runs against
#: offline, so a drift here would make those tests pass against the wrong shape.
_conforms: type[StreamingAnswerReasoner] = DeterministicReasoningProvider
