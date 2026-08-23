"""The stand-in every offline run reasons with, in one place instead of eight branches.

This is not a provider. It is what ArchCompass does when there is no model: `make check`
runs on it, the browser suite drives the whole workbench on it, `make docker-build` smokes
the container on it, and a developer with no key sees it in the picker. So it has to behave
like a review rather than like a mock — hold a finding while the case says nothing, ask a
question with answers to click, write a paragraph, and make *real* lookups against the real
atlas, because a transcript nothing renders is a transcript nothing checks.

It used to live as `if config.provider == "fake"` inside five production adapters — a
hundred and seventy lines of `selected.py`, which is a module about which model is selected
right now and had a third of its length spent on the case where none is. Every one of those
branches asked the same question and answered it in a different place, and the next
provider with a special case had a template to follow.

Here instead, implementing the capability protocols directly, and chosen once in
`bootstrap.py` where every other adapter choice is already made. What each of these does is
the same as what the branch did; what changed is that a reader can see all of it at once,
and that `selected.py` is now about one thing.
"""

from __future__ import annotations

from dataclasses import replace

from archcompass.domain import (
    ArchitectureCase,
    Candidate,
    CaseFacet,
    Finding,
    Question,
    RepositoryAtlas,
    RepositoryRef,
    Review,
    ReviewDelta,
    Verdict,
)
from archcompass.ports.capabilities import InvestigatedFinding, ReviewSynopsis
from archcompass.ports.policy_retrieval import (
    RetrievedPolicySet,
)
from archcompass.reasoning.adapters.providers import DETERMINISTIC_MODEL
from archcompass.reasoning.adapters.tool_loop import recorded_investigation
from archcompass.reasoning.ports import ConversationAnswer, ConversationMessage, InvestigatorSource
from archcompass.reasoning.records import DETERMINISTIC_JUDGE_PROMPT_IDENTITY

#: The model name this chain reports itself as. One string, because it reaches a `Finding`,
#: a `ReviewSynopsis`, a `ConversationAnswer` and an investigation record, and those four
#: are compared against each other by the delta calculator.
#:
#: Derived rather than written out. The branches this replaced each said `f"fake:{config.model}"`,
#: and spelling the model here instead would agree with `DETERMINISTIC_MODEL` only for as long
#: as nobody bumps it — after which every stamp says the old name and the delta calculator
#: reports a moved model for every candidate of every review.
DETERMINISTIC_MODEL_IDENTITY = f"fake:{DETERMINISTIC_MODEL}"


class DeterministicJudge:
    """Holds while nobody has answered anything, clears once the case says something.

    The rule is the whole point: it exercises the clarification round rather than skipping
    it, which is what makes the interrupt, the resume and the rejudgement reachable without
    a model. Answers are the only thing left to hold on — the goal went first, then the
    hand-authored constraints and decisions, and what remains is the channel a review fills.
    """

    def judge(
        self,
        candidate: Candidate,
        case: ArchitectureCase,
        policies: RetrievedPolicySet,
    ) -> Finding:
        hinge = (
            None
            if case.answers
            else "whether these boundaries are deliberate or speculative"
        )
        return Finding(
            candidate,
            Verdict.HELD if hinge else Verdict.CLEARED,
            (
                "The deterministic provider holds this finding until the case says "
                "something about intent."
                if hinge
                else "The deterministic provider found no material conflict in the case."
            ),
            (),
            candidate.evidence,
            hinge=hinge,
            model_identity=DETERMINISTIC_MODEL_IDENTITY,
            prompt_identity=DETERMINISTIC_JUDGE_PROMPT_IDENTITY,
            retrieval_identity=policies.provenance.identity,
        )


class DeterministicQuestionGenerator:
    """One question, with answers to click rather than a blank box.

    A question with no options is a textarea, and the product shows a menu — so a stand-in
    that offered a blank box would be teaching the wrong shape to the browser suite and to
    every developer running without a key. Asked about the boundaries in front of it rather
    than about a "goal", which is the facet the case retired.
    """

    def generate(
        self,
        case: ArchitectureCase,
        findings: tuple[Finding, ...],
        *,
        round: int,
        excluded_equivalence_keys: frozenset[str],
    ) -> tuple[Question, ...]:
        del case
        held = tuple(item for item in findings if item.hinge)
        if not held:
            return ()
        question = Question.create(
            text=(
                "These boundaries each have exactly one implementation today. Is that "
                "deliberate?"
            ),
            facet=CaseFacet.DECISION,
            candidate_ids=tuple(str(item.candidate.id) for item in held),
            round=round,
            options=(
                "The boundaries are deliberate: a second implementation is expected "
                "and the seam is being held open for it.",
                "The boundaries are there to keep the domain testable, and a second "
                "implementation is not expected.",
                "The boundaries were speculative and we would collapse them if a "
                "review said so.",
            ),
        )
        return (
            () if question.equivalence_key in excluded_equivalence_keys else (question,)
        )


class DeterministicSynopsist:
    """A paragraph that says what it is, so the document keeps its shape.

    A report whose opening paragraph exists only against a hosted model is a paragraph
    nothing checks — and the browser suite reads this one.
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
        del case, questions, delta, previous, waiting
        if not findings:
            return None
        material = tuple(item for item in findings if item.verdict is Verdict.MATERIAL)
        held = tuple(item for item in findings if item.hinge)
        said = (
            "none are material"
            if not material
            else "the material ones are "
            + ", ".join(
                f"`{item.candidate.participants[0].qualified_name}`" for item in material
            )
        )
        waits = (
            ""
            if not held
            else f" {len(held)} of them "
            + ("is" if len(held) == 1 else "are")
            + " waiting on an answer from a person."
        )
        return ReviewSynopsis(
            f"This summary was composed deterministically rather than written by a "
            f"model. Of {len(findings)} candidates judged, {said}.{waits}",
            DETERMINISTIC_MODEL_IDENTITY,
        )


class DeterministicAnswerer:
    """A stood-in answer over real lookups, for the reason the hinge pass does the same."""

    def __init__(self, investigators: InvestigatorSource | None = None) -> None:
        self._investigators = investigators

    def answer(
        self,
        review: Review,
        history: tuple[ConversationMessage, ...],
        question: str,
    ) -> ConversationAnswer:
        del history, question
        supporting = tuple(str(item.candidate.id) for item in review.findings[:1])
        offered = (
            None
            if self._investigators is None
            else self._investigators.for_review(review.repository, review.atlas)
        )
        investigator = None if offered is None else offered.investigator
        if investigator is not None:
            investigator.call("flagged_signals", {})
            investigator.conclude("The stored review already answers this.", "")
        return ConversationAnswer(
            "The stored review is the source of this deterministic answer.",
            supporting,
            recorded_investigation(
                investigator,
                candidate_id="",
                withheld="" if offered is None else offered.withheld,
                atlas_fingerprint=review.repository.content_id,
                model_identity=DETERMINISTIC_MODEL_IDENTITY,
            ),
        )


class DeterministicHingeInvestigator:
    """Real lookups, a fixed conclusion.

    The lookups are genuine — the same toolbox over the same atlas — because a transcript
    nothing renders is a transcript nothing checks, and this is the chain every offline
    test, browser run and local `make web` uses. What is stood in for is only the judgement
    about them, which follows the deterministic judge's own rule: held while the case says
    nothing, settled once somebody has answered.
    """

    def __init__(self, investigators: InvestigatorSource) -> None:
        self._investigators = investigators

    def supports_tools(self) -> bool:
        return True

    def investigate(
        self,
        finding: Finding,
        case: ArchitectureCase,
        *,
        repository: RepositoryRef,
        atlas: RepositoryAtlas,
    ) -> InvestigatedFinding:
        offered = self._investigators.for_review(repository, atlas)
        investigator = offered.investigator
        if investigator is not None:
            names = [item.qualified_name for item in finding.candidate.participants]
            if names:
                investigator.call("describe_code", {"qualified_name": names[0]})
            investigator.conclude(
                "The deterministic provider looked, and reports what it was shown.", ""
            )
        resolved = bool(case.answers)
        record = recorded_investigation(
            investigator,
            candidate_id=str(finding.candidate.id),
            withheld=offered.withheld,
            resolved=resolved,
            atlas_fingerprint=repository.content_id,
            model_identity=DETERMINISTIC_MODEL_IDENTITY,
        )
        identity = "" if record is None else record.identity
        if not resolved:
            return InvestigatedFinding(
                replace(finding, investigation_identity=identity), record
            )
        return InvestigatedFinding(
            replace(
                finding,
                verdict=Verdict.CLEARED,
                reasoning=(
                    "The deterministic provider checked the repository and found nothing "
                    "the case does not already settle."
                ),
                hinge=None,
                investigation_identity=identity,
            ),
            record,
        )
