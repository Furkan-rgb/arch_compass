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

from typing import ClassVar

from archcompass.domain import (
    ArchitectureCase,
    Candidate,
    CaseFacet,
    Finding,
    Question,
    RecordedInvestigation,
    Review,
    ReviewDelta,
    Termination,
    Verdict,
)
from archcompass.ports.capabilities import ReviewedSubject, ReviewSynopsis
from archcompass.ports.policy_retrieval import (
    RetrievedPolicySet,
)
from archcompass.reasoning.adapters.providers import (
    DETERMINISTIC_DESCRIPTOR,
    DETERMINISTIC_MODEL,
)
from archcompass.reasoning.adapters.review_tools import ReviewToolbox
from archcompass.reasoning.adapters.tool_loop import recorded_investigation
from archcompass.reasoning.ports import ConversationAnswer, ConversationMessage
from archcompass.reasoning.records import DETERMINISTIC_JUDGE_PROMPT_IDENTITY

#: The model name this chain reports itself as. One string, because it reaches a `Finding`,
#: a `ReviewSynopsis`, a `ConversationAnswer` and an investigation record, and those four
#: are compared against each other by the delta calculator.
#:
#: Derived rather than written out, in both halves. The branches this replaced each said
#: `f"fake:{config.model}"`, and spelling either half here instead would agree with what the
#: provider registers only for as long as nobody edits it — after which every stamp says the
#: old name and the delta calculator reports a moved model for every candidate of every
#: review. The provider half was written out until the pass that removed the last copy of
#: `provider == "fake"` from the tree; it is the descriptor's own name now, and the descriptor
#: is the one place in `src/` where that name is a value rather than prose. Prose about it is
#: everywhere — this comment is prose about it — and
#: `test_the_stand_in_provider_is_written_out_in_exactly_one_place` draws the line in the same
#: place. Where exactly it falls is that test's to say, not this comment's.
DETERMINISTIC_MODEL_IDENTITY = f"{DETERMINISTIC_DESCRIPTOR.name}:{DETERMINISTIC_MODEL}"


class DeterministicJudge:
    """Holds while nobody has answered anything, clears once the case says something.

    The rule is the whole point: it exercises the clarification round rather than skipping
    it, which is what makes the interrupt, the resume and the rejudgement reachable without
    a model. Answers are the only thing left to hold on — the goal went first, then the
    hand-authored constraints and decisions, and what remains is the channel a review fills.

    The two identities below are class attributes because the thing that has to read them —
    `SelectedLangChainJudge.in_force` — is choosing between judges and has no instance yet.
    Reading them off the judge is the point: `bootstrap` used to carry its own
    `provider == "fake" -> DETERMINISTIC_MODEL_IDENTITY` rule, so the composition root and
    this class each held half of one decision and either could be edited alone.
    """

    #: The prompt this sends, which is none: it reaches no provider.
    identity: ClassVar[str] = DETERMINISTIC_JUDGE_PROMPT_IDENTITY
    #: The model this reports itself as, on every finding it stamps below.
    model_identity: ClassVar[str] = DETERMINISTIC_MODEL_IDENTITY

    def judge(
        self,
        candidate: Candidate,
        case: ArchitectureCase,
        policies: RetrievedPolicySet,
        investigation: RecordedInvestigation | None = None,
        *,
        subject: ReviewedSubject | None = None,
    ) -> Finding:
        # A deterministic verdict reads nothing, so there is nothing to look at and nothing
        # to record. The subject is taken so this satisfies the same port and dropped here.
        del subject
        # Taken and ignored, deliberately. This chain's rule is about what a person has
        # answered, and lookups are not answers — so the second judgement of an investigated
        # candidate reaches the same verdict as the first, the hinge survives, and the
        # clarification round every offline suite depends on still runs.
        del investigation
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
            model_identity=self.model_identity,
            prompt_identity=self.identity,
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

    def __init__(self, toolbox: ReviewToolbox | None = None) -> None:
        self._toolbox = toolbox

    def answer(
        self,
        review: Review,
        history: tuple[ConversationMessage, ...],
        question: str,
        *,
        about: Question | None = None,
    ) -> ConversationAnswer:
        del history, question
        supporting = tuple(str(item.candidate.id) for item in review.findings[:1])
        offered = (
            None
            if self._toolbox is None
            else self._toolbox.for_review(review.repository, review.atlas)
        )
        investigator = None if offered is None else offered.investigator
        if investigator is not None:
            investigator.call("flagged_signals", {})
            investigator.conclude(
                "The stored review already answers this.", Termination.NATURAL_END
            )
        return ConversationAnswer(
            (
                f"This deterministic answer stands in for one about “{about.text}”. "
                "A real model reads the question, the findings it is holding up and the "
                "repository itself."
                if about is not None
                else "The stored review is the source of this deterministic answer."
            ),
            supporting,
            recorded_investigation(
                investigator,
                candidate_id="",
                withheld="" if offered is None else offered.withheld,
                atlas_fingerprint=review.repository.content_id,
                model_identity=DETERMINISTIC_MODEL_IDENTITY,
            ),
            # Deliberately never a draft. A stand-in that proposed words for somebody's own
            # answer would be putting a fixture's sentence into the case as their intent,
            # and the browser suite answers rounds through exactly this path.
            suggested_answer="",
            model_identity=DETERMINISTIC_MODEL_IDENTITY,
        )
