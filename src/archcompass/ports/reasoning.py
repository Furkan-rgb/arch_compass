"""The reasoning boundary: the two stages a review needs a model for."""

from __future__ import annotations

from collections.abc import Callable
from enum import StrEnum
from typing import Protocol, runtime_checkable

from archcompass.domain.atlas import FindingCandidate
from archcompass.domain.case import ArchitectureCase
from archcompass.domain.knowledge import MethodKnowledge
from archcompass.domain.policy import PolicyDocument
from archcompass.domain.review import (
    BoundaryExcerpt,
    BoundaryReview,
    CandidateVerdict,
    OpenQuestion,
    ReviewedBoundary,
    ReviewEvidence,
    ReviewOverview,
)
from archcompass.domain.review_conversation import ReviewAnswer, ReviewMessage
from archcompass.ports.investigation import SourceInvestigator


class ReasoningTask(StrEnum):
    """Every reasoning stage that carries its own versioned prompt contract.

    Stage names were previously repeated as bare strings in the prompt registry, the
    workflow call sites, and the conversation service, so a typo surfaced only as a
    runtime KeyError. Naming them once makes the set checkable.
    """

    JUDGE_FINDING_CANDIDATE = "judge_finding_candidate"
    #: The lookups a stage makes before it asks, which is a stage in its own right because
    #: it has its own contract and its own identity: what the model is told while it holds
    #: tools is not what it is told while it composes questions. Both halves are stored: a
    #: review carries the transcript as its `RecordedInvestigation`, and this identity is the
    #: `prompt_identity` on it — a lookup record under a superseded contract is a record of a
    #: different investigation, and could not be compared with a later one without it.
    INVESTIGATE_USAGE = "investigate_usage"
    #: The same two tools held by a stage about to reply to a person rather than to question
    #: one. Its own task and not a second use of the one above, because the restraint differs:
    #: an elicitation looks at the repository before it may ask anything, while most messages
    #: in a conversation are about the review's own words and are answered without a lookup.
    #: Two contracts is also what keeps the identities apart, so a stored transcript says
    #: which of the two kinds of looking produced it.
    INVESTIGATE_FOR_ANSWER = "investigate_for_answer"
    ELICIT_QUESTIONS = "elicit_questions"
    SUMMARISE_REVIEW = "summarise_review"
    ANSWER_REVIEW_QUESTION = "answer_review_question"
    DISCUSS_OPEN_QUESTION = "discuss_open_question"


class FocusedReasoningProvider(Protocol):
    """Judgement and answering, plus the identities a review records for both.

    One protocol rather than two: the identity half was split out for a consultation-era
    caller that no longer exists, leaving an abstraction with a single extender and no
    separate consumer — the shape this advisor exists to report.
    """

    @property
    def model_identity(self) -> str: ...

    #: How many judgements this reasoner will answer at once, which is a property of the
    #: provider behind it rather than of any stage — a hosted API serves several requests in
    #: parallel, a local Ollama serves one model on one GPU. Only `judge_finding_candidate`
    #: is ever called this way, because it is the only stage a review calls more than once.
    #:
    #: On the protocol rather than found by `isinstance`, unlike streaming: every reasoner
    #: has an answer to this and `1` is a real answer, so there is no capability here to be
    #: absent — only a number to be read.
    @property
    def concurrent_requests(self) -> int: ...

    def prompt_identity(self, task: ReasoningTask) -> str: ...

    def judge_finding_candidate(
        self,
        case: ArchitectureCase,
        candidate: FindingCandidate,
        policies: list[PolicyDocument],
        excerpts: list[BoundaryExcerpt] | None = None,
    ) -> CandidateVerdict:
        """Decide whether one detected pattern matters in this case.

        The policies are presented in the order given and the response binds to them by
        position, so the list must not be reordered between the call and the result.

        `excerpts` is the code at this candidate's own recorded spans — every participant,
        definitions widened to take in the comment block written above them — read by the
        application before the call. It is evidence and not a lookup: the spans were chosen
        by a detector, the reading is the application's, and the stage is given no way to ask
        for a line that is not one of them. That is what keeps a verdict checkable, and it is
        why this parameter is not the amendment `elicit_questions` documents.

        `None` is the legacy shape — what every caller passed before candidates carried their
        usage — and means the stage judges from structure alone, as it always did. A provider
        that cannot present source ignores it; nothing about the verdict changes shape either
        way.
        """
        ...

    def elicit_questions(
        self,
        case: ArchitectureCase,
        boundaries: list[ReviewedBoundary],
        investigator: SourceInvestigator | None = None,
    ) -> list[OpenQuestion]:
        """Ask for what would settle the verdicts that could not settle themselves.

        The first pass's last call, and its only job. It sees every verdict together, which
        is the one place hinges can be merged — four boundaries turning on whether a second
        vendor is coming are one question citing four boundaries, and asking it four times
        buries the four verdicts underneath it (6C.2).

        Deliberately not folded into `summarise_review`. A first pass runs against a case
        that usually says nothing, so a conclusion composed there would be drawn from
        silence, and the second pass discards it anyway. Splitting the two also gives this
        stage a prompt that is wholly about asking well rather than half about synthesis.

        An empty list is the good outcome and means the verdicts stand on what the case
        already says, which is what turns a first pass into a finished review.

        Boundaries are presented by position and the reply marks which of them each question
        rests on, so the order must not change between the call and the result. Nothing here
        may revise a verdict — the shape returned has no field for one.

        `investigator` is a bounded set of read-only lookups into the repository these
        verdicts were reached in, which the stage may use before composing anything. `None`
        — the default, and what every caller passed before it existed — means the questions
        are asked from the pinned evidence alone, which is also what happens when the
        provider behind this cannot carry tools at all. Nothing about the questions changes
        shape either way: an investigation improves what is asked, and its absence is a stage
        asking as it always did.

        **`judge_finding_candidate` deliberately has no such parameter.** §12.0's rule that
        the application chooses evidence is amended here for asking and nowhere else: a
        verdict has to rest on spans a detector picked and the application read, because that
        is what makes it checkable. A question binds nothing, and the lookups behind one are
        recorded, which is why this is the stage that may look. Judging is shown code —
        `excerpts` — and that is the opposite of this: a toolbox is the model choosing what
        to read, and a list of excerpts is the application having chosen.
        """
        ...

    def summarise_review(
        self,
        case: ArchitectureCase,
        boundaries: list[ReviewedBoundary],
    ) -> ReviewOverview:
        """Say what the verdicts amount to, once, across all of them.

        The boundaries arrive already composed and numbered, and are presented by position:
        the reply marks which of them each statement rests on, and their references are
        attached from those positions. The order must not change between the call and the
        result. Nothing here may revise a verdict — the shape returned has no field for one.

        This stage cannot ask questions, and that is what terminates the elicitation loop.
        It runs only on a second pass, against a case the reader has just answered, and a
        reply that could open a fresh round would leave the flow with no way to end. A
        verdict that still hinges — because a question was skipped — says so on the boundary
        itself, where it is a caveat on a finding rather than another gate in front of one.
        """
        ...

    def answer_review_question(
        self,
        review: BoundaryReview,
        evidence: ReviewEvidence,
        history: list[ReviewMessage],
        question: str,
        knowledge: MethodKnowledge,
        investigator: SourceInvestigator | None = None,
    ) -> ReviewAnswer:
        """Answer one question about a review the model is shown in full.

        `evidence` is everything about this review the stage may reason from, assembled by
        the application: the pinned case, the code at every recorded span, and the round of
        questions and answers that produced this pass. It is one value rather than three
        arguments because each of the three was, at some point, simply not passed — and each
        time this stage truthfully reported that the review held no such thing.

        The reply marks supporting boundaries by position in `review.report.reviewed`, so
        the order must not change between the call and the result.

        `knowledge` is background about the method — the primer and the whole policy corpus,
        presented entire rather than ranked. It explains the review's vocabulary; it is
        never evidence about the repository, and an answer never cites it as grounding. Only
        boundaries ground an answer, so nothing here binds by position and nothing here is
        read back.

        `investigator` is the toolbox `elicit_questions` holds, offered here for the same
        reason: a question that turns on how the code stands *now* — where else is this
        called, did anyone consolidate it since — is one the pinned evidence cannot settle,
        and answering it from the excerpts alone is answering a question that was not asked.
        `None` means what it means at elicitation: the reply is composed from the pinned
        evidence alone, which is also what happens where the provider cannot carry tools.
        """
        ...

    def discuss_open_question(
        self,
        review: BoundaryReview,
        evidence: ReviewEvidence,
        question: OpenQuestion,
        history: list[ReviewMessage],
        asked: str,
        knowledge: MethodKnowledge,
        investigator: SourceInvestigator | None = None,
    ) -> ReviewAnswer:
        """Talk about one open question with the person who has to answer it.

        `evidence.case` matters more here than anywhere: the reader is being asked to add
        something to this document, so "what does it already say about that" is among the
        first things they will ask.

        It is the revision the review pinned, so it holds what was written before this round
        — including answers from an earlier round — and never the answers being typed right
        now, which batch into one revision only when the reader saves (§6C.4). A stage
        reasoning from a reply they can still delete would be reasoning from something that
        is not yet their answer.

        `evidence.elicitation` is empty here, and that is the same rule. This stage runs
        while the round is being answered, so the round it would describe is the one still
        being typed — the previous pass's questions and answers reach it only through the
        case they were already written into.

        A different stage from `answer_review_question` and not a narrower call of it. That
        one explains a review that has concluded; this one runs while the review is still
        waiting, and it exists because a reader who does not understand what is being asked
        has no way forward at all — the question is the whole of what stands between them
        and a result.

        Shown only the boundaries `question` cites, resolved by the adapter from the
        review's report. That is what makes it safe to run at `awaiting_answers`: the
        verdicts a first pass is deliberately withholding are not in the input, so there is
        nothing here to leak. Grounding is positional over that subset in the order the
        report stores it.

        It may reach for an answer with the reader and may offer a phrasing in
        `suggested_answer`; it may never record one. What comes back fills a box the reader
        edits and submits themselves, through the same preview every other answer walks
        (§6C.4, invariant 25).

        `investigator` is the same toolbox `answer_review_question` is offered, and it is the
        one place a reader most often asks a question of the code: "how would I know whether
        these are the same constant?" is answered by what the repository does with them. The
        toolbox is not scoped the way the boundaries are, and that is deliberate rather than
        an oversight — see where it is built for why the two can differ.
        """
        ...


@runtime_checkable
class StreamingAnswerReasoner(Protocol):
    """A reasoner that can also report an answer's prose while it is being written.

    Its own protocol, tested with `isinstance`, because whether a reply can be streamed is a
    property of the vendor behind the reasoner rather than of the stage. A reasoner that
    cannot omits the method; the application asks, and answers the question without a preview
    when the answer is no. Folding this into `FocusedReasoningProvider` would instead make
    every reasoner declare a capability it might not have.

    That check is by name only. `runtime_checkable` compares which methods exist and nothing
    about their signatures, so a `stream_review_answer` taking different arguments passes
    `isinstance` and then fails on the call — and no type checker sees it either, because a
    reasoner is built and passed around as `FocusedReasoningProvider`, which says nothing
    about streaming. Every implementation therefore states its conformance to this protocol
    where it is defined, so the signature is checked at the one place that knows it.

    What is streamed is a preview and nothing more. `stream_review_answer` returns the same
    validated `ReviewAnswer` the non-streaming call returns, from the same validation, and
    the answer that gets stored is that one — never the accumulated fragments. Grounding is
    still derived from positional flags that only exist once the whole reply has arrived, so
    a preview can never carry a citation.
    """

    def stream_review_answer(
        self,
        review: BoundaryReview,
        evidence: ReviewEvidence,
        history: list[ReviewMessage],
        question: str,
        knowledge: MethodKnowledge,
        investigator: SourceInvestigator | None,
        on_prose: Callable[[str], None],
    ) -> ReviewAnswer:
        """Answer as `answer_review_question` does, calling `on_prose` with each fragment.

        Each call receives only text not yet passed, in order, so a caller may append.
        Fragments may stop arriving before the answer does — a reply needing the one
        sanctioned repair round is rewritten unstreamed — so a caller must treat the returned
        answer as the text, and whatever it showed meanwhile as provisional.

        Any investigation happens before a single fragment is emitted, so what a reader
        watches is exactly what they watched before this parameter existed: the reply, from
        its first word. No part of a lookup is ever previewed — the toolbox turns are a
        separate conversation whose only output is the findings the answer is composed from.
        A turn that looks therefore starts later and reads the same, which is the trade this
        stage is allowed to make and the streaming path is not allowed to expose.
        """
        ...

    def stream_open_question_discussion(
        self,
        review: BoundaryReview,
        evidence: ReviewEvidence,
        question: OpenQuestion,
        history: list[ReviewMessage],
        asked: str,
        knowledge: MethodKnowledge,
        investigator: SourceInvestigator | None,
        on_prose: Callable[[str], None],
    ) -> ReviewAnswer:
        """Discuss as `discuss_open_question` does, calling `on_prose` with each fragment.

        Both streamed methods live on this protocol rather than one, because streaming is a
        property of the transport and a reasoner that can preview one reply can preview the
        other. Splitting them would let a provider claim half a capability that is really
        one thing.

        The suggested phrasing is never part of what streams. It is a separate field of the
        validated reply, so it exists only once the whole reply has arrived — for the same
        reason a preview can never carry a citation.
        """
        ...
