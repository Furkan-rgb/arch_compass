"""Every reasoning stage, and the two calls all of them go through.

`StructuredReasoningProvider` is the whole of what a vendor is asked to do: judge one
candidate, elicit the questions a review still needs answered, summarise a set of verdicts,
answer a question about a review, discuss one open question. Each stage assembles its own
payload from domain objects the application already chose, names the shape the reply must
take, and hands both to `_complete`.

`_complete` and `_chat` beneath it are where every stage meets the transport: one budget
guard, one schema, one validation, and one repair round for the reply that failed it.
Nothing here retrieves evidence or decides what a stage may reason from — that is the
application's, and the import ban in `tests/unit/test_boundaries.py` is what keeps it so.
"""

from __future__ import annotations

import math
from collections.abc import Callable, Mapping
from typing import ClassVar, TypeVar

from pydantic import BaseModel, ValidationError

from archcompass.adapters.models.prompt_contracts import STAGE_PROMPTS
from archcompass.adapters.models.structured.chat_transports import (
    ChatMessage,
    ChatTransport,
    ProsePreview,
    StreamingChatTransport,
    ThinkLevel,
    accumulate_reply,
)
from archcompass.adapters.models.structured.investigation_loop import investigate
from archcompass.adapters.models.structured.reply_schemas import (
    ProposedCandidateVerdict,
    ProposedElicitation,
    ProposedQuestionDiscussion,
    ProposedReviewAnswer,
    ProposedReviewOverview,
    grounded_questions,
    grounded_schema,
    grounded_statements,
    prose_defects,
    review_answer_schema,
    verdict_hinge,
    verdict_schema,
)
from archcompass.configuration import ReasoningModelConfig
from archcompass.domain.atlas import FindingCandidate
from archcompass.domain.atlas_map import AtlasMap
from archcompass.domain.base import canonical_json
from archcompass.domain.case import ArchitectureCase
from archcompass.domain.errors import (
    ModelOutputValidationError,
    PromptBudgetExceededError,
    ProviderError,
)
from archcompass.domain.knowledge import MethodKnowledge
from archcompass.domain.policy import PolicyDocument
from archcompass.domain.review import (
    AnsweredQuestion,
    BoundaryExcerpt,
    BoundaryReview,
    CandidateVerdict,
    OpenQuestion,
    OverviewStatement,
    PolicyBearing,
    ReviewedBoundary,
    ReviewEvidence,
    ReviewOverview,
    ReviewStatus,
)
from archcompass.domain.review_conversation import ReviewAnswer, ReviewMessage
from archcompass.ports.investigation import SourceInvestigator
from archcompass.ports.reasoning import ReasoningTask, StreamingAnswerReasoner

Item = TypeVar("Item", bound=BaseModel)

class StructuredReasoningProvider:
    """Every reasoning stage, resolved against whichever transport is supplied."""

    _PROMPTS: ClassVar[dict[ReasoningTask, str]] = {
        task: contract.identity for task, contract in STAGE_PROMPTS.items()
    }

    def __init__(self, config: ReasoningModelConfig, transport: ChatTransport) -> None:
        self._config = config
        self._transport = transport

    @property
    def model_identity(self) -> str:
        return f"{self._config.provider}:{self._config.model}"

    @property
    def concurrent_requests(self) -> int:
        """Read off the configuration, because that is where the provider's answer lands.

        The number came from the provider's descriptor and may have been overridden by the
        environment on its way here, and neither is this class's business — it reasons with
        whatever configuration it was handed, and this is one more field of it.
        """

        return self._config.concurrent_requests

    def prompt_identity(self, task: ReasoningTask) -> str:
        return self._PROMPTS[task]

    def _think_for(self, requested: ThinkLevel) -> ThinkLevel:
        """The configured setting, unless a stage asked for a specific level.

        `None` means "no opinion" at both levels, and passing it on is what leaves the
        model to its own default — which is a third behaviour, not a synonym for off. A
        stage that names a level keeps it, because a stage asking for less reasoning than
        the model is capable of has a reason to.
        """

        return self._config.thinking if requested is None else requested

    def judge_finding_candidate(
        self,
        case: ArchitectureCase,
        candidate: FindingCandidate,
        policies: list[PolicyDocument],
        excerpts: list[BoundaryExcerpt] | None = None,
    ) -> CandidateVerdict:
        expected = len(policies)
        proposed = self._complete(
            ReasoningTask.JUDGE_FINDING_CANDIDATE,
            {
                "case": case.model_dump(mode="json"),
                "candidate": candidate.model_dump(mode="json"),
                # The code at the candidate's own spans, when the application read it. The
                # key is absent rather than empty where it did not: an empty list is a
                # statement — "these lines were looked for and are not there" — and the
                # contract says what a missing key means, which is that structure is the
                # whole of the evidence here.
                **(
                    {"source_evidence": self._source_entries(excerpts)}
                    if excerpts
                    else {}
                ),
                # Presented without IDs on purpose. An identifier in the input is an
                # identifier the model can quote back, and position is already a complete
                # and unforgeable binding.
                "policies": [
                    {
                        "position": index,
                        "title": policy.title,
                        "scope": policy.scope.value,
                        "strength": policy.strength.value,
                        "applies_to": policy.applies_to,
                        "body": policy.body,
                    }
                    for index, policy in enumerate(policies, start=1)
                ],
            },
            ProposedCandidateVerdict,
            runtime_instruction=(
                f"Return exactly {expected} policy_bearings entries, one for each supplied "
                "policy, in the order the policies appear above."
            ),
            schema_override=verdict_schema(policy_count=expected),
            # The schema fixes the arity and the repair round exists for the model that
            # ignores it. Position is the only thing tying a bearing to a policy, so a
            # short list would silently re-map every entry after the gap.
            candidate_validator=lambda item: (
                []
                if len(item.policy_bearings) == expected
                else [
                    f"policy_bearings must contain exactly {expected} entries, one per "
                    f"supplied policy in order, but contains {len(item.policy_bearings)}"
                ]
            ),
        )
        bearings = [
            PolicyBearing(policy_id=policy.id, policy_title=policy.title, how=item.how.strip())
            for policy, item in zip(policies, proposed.policy_bearings, strict=True)
            # A bearing asserted without saying how is not a bearing. Recording it as a
            # bare flag would put an unexplained policy name in a report, so it is dropped
            # rather than kept as something a reader cannot check.
            if item.bears_on and item.how.strip()
        ]
        # The word becomes the domain's flag here and nowhere else. `material` keeps its
        # name in the domain, where it is read by code rather than written by a model, and
        # this single line is the whole of the translation.
        material = proposed.verdict == "should_change"
        return CandidateVerdict(
            candidate_id=candidate.candidate_id,
            material=material,
            rationale=proposed.rationale,
            policy_bearings=bearings,
            hinge=verdict_hinge(proposed.hinge),
            recommended_response=(proposed.recommended_response.strip() if material else ""),
        )

    def _investigate(
        self,
        task: ReasoningTask,
        payload_json: str,
        investigator: SourceInvestigator | None,
        *,
        force_first: bool = True,
        think: ThinkLevel = None,
    ) -> str:
        """Let the model look things up, through this provider's transport and settings.

        The loop itself is `investigation_loop.investigate`; what this adds is the two things
        only a configured provider knows — which transport to run it over, and what thinking
        level a stage that named none should get.
        """

        return investigate(
            self._transport,
            task,
            payload_json,
            investigator,
            force_first=force_first,
            think=self._think_for(think),
        )

    def elicit_questions(
        self,
        case: ArchitectureCase,
        boundaries: list[ReviewedBoundary],
        investigator: SourceInvestigator | None = None,
    ) -> list[OpenQuestion]:
        expected = len(boundaries)
        payload: dict[str, object] = {
            "case": case.model_dump(mode="json"),
            "boundaries": self._boundaries_for_reading(boundaries),
        }
        # Before the questions and from the same input, so the stage investigates the
        # verdicts it is about to ask about rather than a summary of them. The findings then
        # enter that input as one more key: everything below — the grounded schema, the arity
        # validator, the repair round — is untouched by whether anything was looked up.
        findings = self._investigate(
            ReasoningTask.INVESTIGATE_USAGE,
            canonical_json(payload),
            investigator,
        )
        if findings:
            payload["investigation"] = findings
        proposed = self._complete(
            ReasoningTask.ELICIT_QUESTIONS,
            payload,
            ProposedElicitation,
            runtime_instruction=(
                f"Every entry in open_questions must carry exactly {expected} supported_by "
                "flags, one for each boundary, in the order the boundaries appear above."
            ),
            schema_override=grounded_schema(
                ProposedElicitation, boundary_count=expected
            ),
            candidate_validator=lambda item: [
                f"every supported_by must contain exactly {expected} flags, one per "
                f"boundary in order, but one entry contains {len(question.supported_by)}"
                for question in item.open_questions
                if len(question.supported_by) != expected
            ],
        )
        return grounded_questions(proposed.open_questions, boundaries)
    @staticmethod
    def _elicitation_round(
        elicitation: list[AnsweredQuestion],
        *,
        answers_were_recorded: bool,
    ) -> list[dict[str, object]] | str:
        """The round of questions and answers behind this pass, as the stage is shown it.

        Both halves in one place and in the order they were asked, because the reader who
        asks about them is asking about a round they walked, not about two records.

        The three outcomes are spelled out rather than left to an absent key. An unanswered
        question read as "not mentioned" is exactly the misreading this presentation exists
        to prevent: a verdict that still hinges usually hinges on the question its reader
        chose to skip, and that is a finding about the review rather than a gap in it.
        """

        if not elicitation:
            return (
                "This review asked nothing — it is a first pass, or the pass that asked has "
                "since been deleted."
            )
        return [
            {
                "what_the_review_saw": item.question.what_the_review_saw,
                "question": item.question.question,
                "why_it_matters": item.question.why_it_matters,
                "answer": (
                    item.answer
                    if item.answer
                    else (
                        "skipped — the reader chose not to answer this one"
                        if answers_were_recorded
                        else "not recorded — this case revision was edited by hand, so no "
                        "line in it is attributable to any one question"
                    )
                ),
            }
            for item in elicitation
        ]

    @staticmethod
    def _structure_for(candidate: FindingCandidate) -> dict[str, object]:
        """The detector's own record of what makes up this boundary, for both talking stages.

        The judging stage always had this — which elements participate and which edges run
        among them — and the stages a person actually talks to did not, so "what implements
        this?" was answerable only from whatever the prose happened to restate. Participants
        are named by qualified name and never by node id, for the reason nothing else
        carries an id (12.0); edges are joined back through the participants so they read
        as names too, and an endpoint the detector did not list among the participants is
        said to be outside them rather than leaked as a raw id.

        An empty edge list is stated as a fact about the detector, not about the code: only
        one of the three patterns records edges, and a stage told nothing would report that
        the elements are unrelated.
        """

        names = {item.node_id: item.qualified_name for item in candidate.participants}
        outside = "an element outside this boundary's participants"
        return {
            "participants": [
                {
                    "qualified_name": item.qualified_name,
                    "part_played": item.role,
                    "where": (
                        f"{item.location.path}:{item.location.start_line}"
                        if item.location is not None
                        else "not recorded"
                    ),
                }
                for item in candidate.participants
            ],
            "relationships": (
                [
                    (
                        f"{names.get(edge.source_id, outside)}"
                        f" —{edge.edge_type.value}→ "
                        f"{names.get(edge.target_id, outside)}"
                    )
                    for edge in candidate.relationships
                ]
                if candidate.relationships
                else (
                    "none recorded — the "
                    f"{candidate.pattern.value} detector does not record edges between "
                    "its participants, which says nothing about whether the code relates "
                    "them"
                )
            ),
        }

    @staticmethod
    def _excerpt_note(item: BoundaryExcerpt) -> str | None:
        """Both captions an excerpt can carry, as one sentence or two, or nothing.

        An excerpt can be a pinned copy of a repository that has moved on and be clipped
        short of its recorded span at the same time; each caveat changes what the stage may
        claim from the code, so neither may displace the other.
        """

        captions: list[str] = []
        if item.provenance:
            captions.append(item.provenance)
        if item.truncated_after_line is not None and item.location is not None:
            captions.append(
                f"Truncated: the recorded span runs to line {item.location.end_line}, "
                f"but only lines up to {item.truncated_after_line} are shown. Never "
                "claim the lines past that point say nothing."
            )
        return " ".join(captions) or None

    @staticmethod
    def _atlas_map_payload(atlas_map: AtlasMap | None) -> object:
        """The repository's structure at review time, or a statement of why it is absent.

        Omitted counts render as sentences rather than bare numbers, because a trimmed map
        must not read as a complete one: "3 modules omitted" is the difference between
        "that module does not exist" and "that module was folded away for space".
        """

        if atlas_map is None:
            return "not assembled for this stage"
        if atlas_map.unavailable:
            return f"unavailable: {atlas_map.unavailable}"
        return {
            "modules": [
                {
                    "module": module.path,
                    "declares": module.members,
                    **(
                        {
                            "declarations_omitted": (
                                f"{module.members_omitted} declarations omitted to fit "
                                "the budget — absence from this list is not absence from "
                                "the module"
                            )
                        }
                        if module.members_omitted
                        else {}
                    ),
                }
                for module in atlas_map.modules
            ],
            "module_relationships": [
                f"{item.source_module} depends on {item.target_module}: {item.kinds}"
                for item in atlas_map.relations
            ],
            **(
                {
                    "modules_omitted": (
                        f"{atlas_map.modules_omitted} modules omitted to fit the budget"
                    )
                }
                if atlas_map.modules_omitted
                else {}
            ),
            **(
                {
                    "relationships_omitted": (
                        f"{atlas_map.relations_omitted} module relationships omitted to "
                        "fit the budget"
                    )
                }
                if atlas_map.relations_omitted
                else {}
            ),
        }

    @staticmethod
    def _policy_corpus_payload(knowledge: MethodKnowledge) -> object:
        """The corpus as background, or the reason there is none.

        The reason is presented instead of an empty list because the two mean different
        things: an empty corpus is a workspace without policies, while an unreadable one is
        a failure the stage should repeat to a reader who asks about policies rather than
        answering as though none exist.
        """

        if knowledge.policy_corpus_unavailable:
            return f"unavailable: {knowledge.policy_corpus_unavailable}"
        return [
            {"title": policy.title, "text": policy.body}
            for policy in knowledge.policies
        ]

    @staticmethod
    def _source_for(
        excerpts: list[BoundaryExcerpt],
        reference: str,
    ) -> list[dict[str, object]]:
        """The code recorded for one boundary, as the conversation stages are shown it.

        Attached to the boundary rather than listed separately, because "which lines belong
        to which finding" is exactly what a reader is asking when they ask to see the code,
        and a flat list would make the stage rebuild that mapping from paths.

        An excerpt that could not be read carries its reason in place of its text. Presented
        rather than dropped: "this repository has changed since the review ran" is the
        honest answer to "show me the code", and silently omitting it would leave the stage
        to conclude the review has no source at all — which is the failure this exists to
        fix.
        """

        return StructuredReasoningProvider._source_entries(
            [item for item in excerpts if item.reference == reference]
        )

    @staticmethod
    def _source_entries(excerpts: list[BoundaryExcerpt]) -> list[dict[str, object]]:
        """The same rendering, for excerpts already narrowed to one thing.

        Split out because judging is shown the code at one candidate's spans, and that
        candidate has no `BR-nnn` yet — references are assigned from position once the
        verdicts exist. One shape for both, so what a judging stage sees and what a
        conversation stage sees are the same four fields in the same order.
        """

        return [
            {
                "where": (
                    f"{item.location.path}:{item.location.start_line}"
                    if item.location is not None
                    else "not recorded"
                ),
                "what_it_contributes": item.role,
                "code": item.text or None,
                "why_there_is_no_code": item.unavailable or None,
                # A caption about the text, when the text needs one — a pinned copy served
                # because the repository has moved on, or a span the excerpt ceiling cut
                # short. Carried beside the code rather than folded into it, so the stage
                # can repeat the caveat without mistaking it for a line of the file.
                "note": StructuredReasoningProvider._excerpt_note(item),
            }
            for item in excerpts
        ]

    @staticmethod
    def _boundaries_for_reading(
        boundaries: list[ReviewedBoundary],
    ) -> list[dict[str, object]]:
        """Every verdict as the two set-wide stages are shown it.

        One presentation, shared, because the two stages read the same set for two different
        purposes and a boundary described differently to each would make their answers
        incomparable — the questions one asks are about the verdicts the other reports.

        No reference codes, for the same reason policies are presented without IDs: an
        identifier in the input is one the model can quote back, and position is already a
        complete and unforgeable binding (12.0).
        """

        return [
            {
                "position": index,
                "boundary": item.candidate.summary,
                # Spelled out rather than passed as `material`. A live run grouped a
                # boundary judged material among the ones "maintained for testability",
                # which is what that word invites: read as ordinary English it says the
                # boundary matters, and the verdict means the opposite. The settled verdict
                # must not be re-readable.
                "verdict": (
                    "NOT earning its place — this boundary should change"
                    if item.material
                    else "earning its place — this boundary should stay as it is"
                ),
                "reasoning": item.rationale,
                "recommended_response": item.recommended_response,
                "policies_that_bear": [
                    f"{bearing.policy_title}: {bearing.how}"
                    for bearing in item.policy_bearings
                ],
                # The detector's own statement of what it could not see. Without it a live
                # run filled the overview's `limits` field with "<No limits provided in
                # input>": the stage was asked to state the limits of a method it had never
                # been told anything about.
                "detection_limits": item.candidate.limitations,
                # What the *case* did not say, which is the other half of what the verdict
                # rested on and the only half a user can fix. Neither stage can consolidate
                # hinges it was never shown, and a question composed without them would be
                # that stage's own uncertainty rather than the judgement's (6C.2).
                "verdict_turns_on": (
                    {
                        "unknown": item.hinge.unknown,
                        "if_confirmed": item.hinge.if_confirmed,
                        "if_denied": item.hinge.if_denied,
                    }
                    if item.hinge is not None
                    # Spelled out rather than omitted, for the reason the verdict is: an
                    # absent key is read as "not mentioned", and this is a positive finding —
                    # the judgement considered what it lacked and concluded the verdict holds
                    # regardless.
                    else "nothing — this verdict stands whichever way the "
                    "unanswered questions about this case fall"
                ),
            }
            for index, item in enumerate(boundaries, start=1)
        ]

    def summarise_review(
        self,
        case: ArchitectureCase,
        boundaries: list[ReviewedBoundary],
    ) -> ReviewOverview:
        expected = len(boundaries)
        proposed = self._complete(
            ReasoningTask.SUMMARISE_REVIEW,
            {
                "case": case.model_dump(mode="json"),
                "boundaries": self._boundaries_for_reading(boundaries),
            },
            ProposedReviewOverview,
            runtime_instruction=(
                f"Every entry in themes and recommended_sequence must carry exactly "
                f"{expected} supported_by flags, one for each boundary, in the order the "
                "boundaries appear above. situation and limits are prose and carry no flags."
            ),
            schema_override=grounded_schema(
                ProposedReviewOverview, boundary_count=expected
            ),
            candidate_validator=lambda item: [
                *prose_defects("situation", item.situation),
                *prose_defects("limits", item.limits),
                *(
                    f"every supported_by must contain exactly {expected} flags, one per "
                    f"boundary in order, but one entry contains "
                    f"{len(statement.supported_by)}"
                    for statement in (*item.themes, *item.recommended_sequence)
                    if len(statement.supported_by) != expected
                ),
            ],
        )
        # No `open_questions`. This stage runs only on a second pass and its schema has no
        # field for one, which is what stops the elicitation loop from reopening itself.
        #
        # The other half of that termination is a stage away, in the judging contract: a second
        # pass hinges again unless it can see that the reader already answered, and it sees
        # that in the case's `clarifications` — the questions and answers of the first round,
        # kept as pairs. This schema makes re-asking unrepresentable; that list is what makes
        # re-hinging unnecessary.
        return ReviewOverview(
            situation=proposed.situation.strip(),
            themes=grounded_statements(proposed.themes, boundaries),
            recommended_sequence=grounded_statements(
                proposed.recommended_sequence, boundaries
            ),
            limits=proposed.limits.strip(),
        )

    def answer_review_question(
        self,
        review: BoundaryReview,
        evidence: ReviewEvidence,
        history: list[ReviewMessage],
        question: str,
        knowledge: MethodKnowledge,
        investigator: SourceInvestigator | None = None,
    ) -> ReviewAnswer:
        return self._answer(
            review, evidence, history, question, knowledge, investigator, preview=None
        )

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
        """The same answer, with its prose reported as it is written.

        One code path, one validation, one returned answer: the preview is handed to the same
        call `answer_review_question` makes. Where the transport cannot stream, or the reply
        needs the repair round, nothing is emitted and the answer simply arrives at the end —
        so a caller never has to ask which of two behaviours it got.
        """

        return self._answer(
            review,
            evidence,
            history,
            question,
            knowledge,
            investigator,
            preview=ProsePreview(field="answer", emit=on_prose),
        )

    def _answer(
        self,
        review: BoundaryReview,
        evidence: ReviewEvidence,
        history: list[ReviewMessage],
        question: str,
        knowledge: MethodKnowledge,
        investigator: SourceInvestigator | None,
        *,
        preview: ProsePreview | None,
    ) -> ReviewAnswer:
        report = review.report
        if report is None:
            raise ValueError("A review without a report cannot be questioned")
        boundaries = report.reviewed
        expected = len(boundaries)
        # Where each conclusion entry came from, by position rather than by code. A
        # statement stores `BR-` references, which must never enter an input the model can
        # quote back (12.0) — but the positions behind them are ArchCompass's own key and
        # are already the vocabulary every boundary below is presented in.
        #
        # Without this, "tell me more about recommendation 3" can only be answered by
        # matching words against the boundary list, and a live conversation showed what
        # that costs: three turns sourced from the conclusion's own summary, one of them
        # saying so outright, while citing a boundary whose record was never opened.
        position_of = {item.reference: index for index, item in enumerate(boundaries, start=1)}

        def rests_on(statement: OverviewStatement) -> list[int]:
            return sorted(
                position_of[reference]
                for reference in statement.supporting_references
                if reference in position_of
            )

        payload: dict[str, object] = {
            "case_title": report.case_title,
            # The case whole, not the report's two-sentence restatement of its problem.
            # It is half of what every verdict here was reached from — the judging stage
            # weighed each boundary against these constraints, non-goals and expected
            # changes — so an explanation that could not see them was explaining a
            # conclusion from half its evidence.
            "case": evidence.case.model_dump(mode="json"),
            # The whole repository's structure as it was when the review ran — what
            # exists and what depends on what, with no verdicts and no code. It is how
            # a question about a module no detector flagged gets a structural answer
            # instead of "I was not shown that", and nothing in a reply may cite it:
            # grounding stays boundaries-only.
            "pinned_atlas_map": self._atlas_map_payload(evidence.atlas_map),
            "counts": report.headline,
            # The round that produced this pass, both halves together. Asked "what were
            # the questions and answers again?", this stage said the review holds no such
            # record — true of the review it was shown and false of what the workspace
            # keeps: the questions are pinned in the first pass for ever, the answers on
            # the case revision this pass runs against.
            #
            # No `Q-n` and no `BR-nnn`, for the reason nothing else here carries one.
            # A reader names a question by what it asked.
            "elicitation_round": self._elicitation_round(
                evidence.elicitation,
                answers_were_recorded=evidence.answers_were_recorded,
            ),
            # The conclusion a reader has in front of them, so a question about it is
            # answerable. Composed from these same verdicts by an earlier call, which is
            # why the contract names it as the review's own reading rather than as
            # evidence — it adds no fact about the repository.
            #
            # Text only. Every statement knows which boundaries it rests on, and those
            # references are exactly what must not appear in an input the model can quote
            # back (12.0); the boundaries themselves are all below with their reasoning.
            "conclusion": {
                "situation": report.overview.situation,
                "themes": [
                    {"text": item.text, "rests_on_boundary_positions": rests_on(item)}
                    for item in report.overview.themes
                ],
                # Numbered as the reader sees them. The page renders this as an ordered
                # list, so "recommendation 3" is the third entry here and nothing has to
                # be inferred from the order of a bare array.
                "recommended_sequence": [
                    {
                        "number": number,
                        "text": item.text,
                        "rests_on_boundary_positions": rests_on(item),
                    }
                    for number, item in enumerate(
                        report.overview.recommended_sequence, start=1
                    )
                ],
                "limits": report.overview.limits,
            },
            # Background about the method, carried under a name that says what it is
            # and is not. It has no positions and nothing binds to it: an answer's
            # grounding is boundaries alone, so nothing here can be cited back — which
            # is also why the policies keep their titles here, unlike in the judging
            # stage where the reply must bind to them by position instead.
            "background_how_archcompass_works": knowledge.method,
            "background_policy_corpus": self._policy_corpus_payload(knowledge),
            # No reference codes. The model is shown the substance and answers by
            # position; codes exist for the reader, not for the model to quote back.
            "boundaries": [
                {
                    "position": index,
                    "boundary": item.candidate.summary,
                    # Which of the three detectors found this. The advice for the two
                    # directions of the catalogue points opposite ways, so a question
                    # about what a boundary even is depends on knowing which it is.
                    "pattern": item.candidate.pattern.value,
                    # Spelled out, for the same reason the summary stage spells it out:
                    # read as ordinary English "material" says the boundary matters,
                    # and the verdict means the opposite.
                    "verdict": (
                        "NOT earning its place — this boundary should change"
                        if item.material
                        else "earning its place — this boundary should stay as it is"
                    ),
                    "reasoning": item.rationale,
                    "recommended_response": item.recommended_response,
                    # The numbers the pattern was detected from — four modules stating a
                    # constant, two distinct values among them. Without them a question
                    # like "how many copies are there?" is answerable only from whatever
                    # the prose happens to have restated.
                    "measurements": [
                        {"name": measure.name, "value": measure.value, "unit": measure.unit}
                        for measure in item.candidate.measurements
                    ],
                    "policies_that_bear": [
                        f"{bearing.policy_title}: {bearing.how}"
                        for bearing in item.policy_bearings
                    ],
                    "detection_limits": item.candidate.limitations,
                    # Which elements make this boundary up and which edges the detector
                    # recorded among them — what the judging stage had and this one
                    # lacked, so "what implements this?" no longer depends on the prose
                    # having restated it.
                    **self._structure_for(item.candidate),
                    # The lines this boundary was measured from, read from the repository
                    # it pinned. Without them a reader asking to see the leak was told
                    # the review "does not include the specific lines" — true of what
                    # reached this stage, and false of what the record holds.
                    "source": self._source_for(evidence.excerpts, item.reference),
                }
                for index, item in enumerate(boundaries, start=1)
            ],
            "earlier_questions": [
                {
                    "question": message.question,
                    "answer": "" if message.answer is None else message.answer.answer,
                }
                for message in history
            ],
            "question": question,
        }
        # Before the answer and from the same input, so the stage looks at the review it
        # is about to speak about rather than at a summary of it. The findings then enter
        # that input as one more key, exactly as they do at elicitation: the grounded
        # schema, the arity validator, the repair round and the preview are all untouched
        # by whether anything was looked up.
        #
        # And it happens here, before `_complete` is entered, which is what keeps a
        # streamed reply a reply: the preview begins with the first fragment of the answer
        # itself, and no part of an investigation is ever shown on its way past.
        findings = self._investigate(
            ReasoningTask.INVESTIGATE_FOR_ANSWER,
            canonical_json(payload),
            investigator,
            force_first=False,
        )
        if findings:
            payload["investigation"] = findings
        proposed = self._complete(
            ReasoningTask.ANSWER_REVIEW_QUESTION,
            payload,
            ProposedReviewAnswer,
            runtime_instruction=(
                f"Return exactly {expected} supported_by values, one for each boundary, in "
                "the order the boundaries appear above."
            ),
            schema_override=review_answer_schema(boundary_count=expected),
            candidate_validator=lambda item: [
                *prose_defects("answer", item.answer),
                *(
                    [
                        f"supported_by must contain exactly {expected} values, one per "
                        f"boundary in order, but contains {len(item.supported_by)}"
                    ]
                    if len(item.supported_by) != expected
                    else []
                ),
            ],
            preview=preview,
        )
        return ReviewAnswer(
            answer=proposed.answer,
            supporting_references=[
                item.reference
                for item, supports in zip(boundaries, proposed.supported_by, strict=True)
                if supports
            ],
        )

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
        return self._discuss(
            review, evidence, question, history, asked, knowledge, investigator, preview=None
        )

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
        return self._discuss(
            review,
            evidence,
            question,
            history,
            asked,
            knowledge,
            investigator,
            preview=ProsePreview(field="answer", emit=on_prose),
        )

    def _discuss(
        self,
        review: BoundaryReview,
        evidence: ReviewEvidence,
        question: OpenQuestion,
        history: list[ReviewMessage],
        asked: str,
        knowledge: MethodKnowledge,
        investigator: SourceInvestigator | None,
        *,
        preview: ProsePreview | None,
    ) -> ReviewAnswer:
        report = review.report
        if report is None:
            raise ValueError("A review without a report cannot be discussed")
        # The cited boundaries and no others, in the order the report stores them. This is
        # the whole of what makes the stage safe to run while a first pass is withholding
        # its verdicts: the ones not cited are not in the input, so there is no side door to
        # the held set (§6C.6). It is also the honest scope — these are the verdicts this
        # question would settle, and the rest have nothing to do with it.
        cited = set(question.supporting_references)
        boundaries = [item for item in report.reviewed if item.reference in cited]
        if not boundaries:
            raise ValueError(
                f"Question {question.reference} cites no boundary this review contains"
            )
        expected = len(boundaries)
        # The conclusion is shown only once the review has concluded. Mid-elicitation the
        # overview is composed from known facts with the themes left empty, and a stage
        # that read it would be reading a summary of the set this reader has deliberately
        # not been shown (§6C.6). But this stage also serves question-scoped conversations
        # about reviews that have since concluded, where the conclusion is on the reader's
        # page and "how does this fit the overall recommendation?" deserves a grounded
        # answer rather than a stage that has never seen the recommendation.
        #
        # Its groundings need care: the conclusion's statements rest on the whole reviewed
        # set while only the cited subset is numbered here, so a full-set position would
        # collide with this payload's own vocabulary. A boundary in the subset is named by
        # its position; one outside it is named by its summary — public on a concluded
        # review — and marked as not shown, so nothing invites citing it.
        concluded = review.status is ReviewStatus.SUCCEEDED
        position_in_subset = {
            item.reference: index for index, item in enumerate(boundaries, start=1)
        }
        summaries = {item.reference: item.candidate.summary for item in report.reviewed}

        def resting(statement: OverviewStatement) -> list[dict[str, object]]:
            return [
                (
                    {"position": position_in_subset[reference]}
                    if reference in position_in_subset
                    else {"boundary_not_shown_in_this_discussion": summaries[reference]}
                )
                for reference in statement.supporting_references
                if reference in summaries
            ]

        # A waiting review may have been carried on from: the loop concludes in a *new*
        # review, so the conclusion the reader has on their page lives on the successor the
        # application looked up, not on the review this thread pins. Shown from there, with
        # its groundings matched back onto the cited subset by boundary fingerprint — the
        # structural identity that survives a re-run — and by summary where an older review
        # carries no fingerprint.
        successor = evidence.concluded_by.report if evidence.concluded_by else None

        def resting_on_successor(statement: OverviewStatement) -> list[dict[str, object]]:
            assert successor is not None
            by_fingerprint = {
                item.fingerprint: index
                for index, item in enumerate(boundaries, start=1)
                if item.fingerprint
            }
            by_summary = {
                item.candidate.summary: index
                for index, item in enumerate(boundaries, start=1)
            }
            entries: list[dict[str, object]] = []
            for reference in statement.supporting_references:
                match = next(
                    (item for item in successor.reviewed if item.reference == reference),
                    None,
                )
                if match is None:
                    continue
                position = (
                    by_fingerprint.get(match.fingerprint) if match.fingerprint else None
                ) or by_summary.get(match.candidate.summary)
                entries.append(
                    {"position": position}
                    if position is not None
                    else {"boundary_not_shown_in_this_discussion": match.candidate.summary}
                )
            return entries

        def rendered(
            overview: ReviewOverview,
            grounding: Callable[[OverviewStatement], list[dict[str, object]]],
        ) -> dict[str, object]:
            return {
                "situation": overview.situation,
                "themes": [
                    {"text": item.text, "rests_on": grounding(item)}
                    for item in overview.themes
                ],
                "recommended_sequence": [
                    {"number": number, "text": item.text, "rests_on": grounding(item)}
                    for number, item in enumerate(overview.recommended_sequence, start=1)
                ],
                "limits": overview.limits,
            }

        conclusion: object
        if concluded:
            conclusion = rendered(report.overview, resting)
        elif successor is not None:
            conclusion = {
                # Said in the payload, not only in the contract: the verdicts above are
                # this round's, and the conclusion came from the pass that ran after the
                # reader's answers — a re-judged boundary may have moved between the two.
                "reached_by": (
                    "a later pass that ran after this round's answers were recorded; the "
                    "verdicts shown above are this round's own"
                ),
                **rendered(successor.overview, resting_on_successor),
            }
        else:
            # Spelled out rather than omitted, as every absence here is: an absent key
            # reads as "reviews have no conclusions", and this one has one on the way.
            conclusion = (
                "withheld — this review is still waiting on answers, so its conclusion "
                "and the verdicts outside this question are not settled enough to show"
            )
        payload: dict[str, object] = {
            "case_title": report.case_title,
            # The case whole, and it matters most here. The reader is being asked to add
            # something to this document, so "what does it already say about that" is
            # among the first things they will ask.
            #
            # This is the revision the review pinned, which means it holds what was
            # written before this round — including answers from any earlier round — and
            # not the answers being typed right now. Those batch into one revision at the
            # end (§6C.4). So this stage cannot see a reply the reader is still free to
            # change or delete, which is correct: an answer is not an answer until they
            # save it.
            "case": evidence.case.model_dump(mode="json"),
            # As the answering stage carries it: structure only, no verdicts, so it
            # widens nothing the cited-boundaries scope protects.
            "pinned_atlas_map": self._atlas_map_payload(evidence.atlas_map),
            **(
                {"counts": report.headline}
                if concluded
                else {"counts": successor.headline} if successor is not None else {}
            ),
            "conclusion": conclusion,
            "the_question_being_discussed": {
                "what_the_review_saw": question.what_the_review_saw,
                "the_unknown": question.unknown,
                "why_it_matters": question.why_it_matters,
                "question_put_to_the_reader": question.question,
                "where_their_answer_would_be_recorded": (
                    question.answer_belongs_in.value
                ),
            },
            "background_how_archcompass_works": knowledge.method,
            "background_policy_corpus": self._policy_corpus_payload(knowledge),
            # Presented as the answering stage presents them, minus the reference codes
            # for the usual reason (12.0). The same fields, because a reader asking
            # "why does this boundary make you ask that" needs what that stage needed.
            "boundaries_this_question_would_settle": [
                {
                    "position": index,
                    "boundary": item.candidate.summary,
                    "pattern": item.candidate.pattern.value,
                    "verdict": (
                        "NOT earning its place — this boundary should change"
                        if item.material
                        else "earning its place — this boundary should stay as it is"
                    ),
                    "reasoning": item.rationale,
                    "recommended_response": item.recommended_response,
                    "measurements": [
                        {"name": measure.name, "value": measure.value, "unit": measure.unit}
                        for measure in item.candidate.measurements
                    ],
                    "policies_that_bear": [
                        f"{bearing.policy_title}: {bearing.how}"
                        for bearing in item.policy_bearings
                    ],
                    "detection_limits": item.candidate.limitations,
                    # As the answering stage carries it, and for the same reason: the
                    # reader being asked to settle what relates these elements needs
                    # what the detector recorded about how they relate.
                    **self._structure_for(item.candidate),
                    "source": self._source_for(evidence.excerpts, item.reference),
                    # What this verdict said it turned on, which is why this boundary is
                    # cited at all. Without it the reader can be told the verdict but not
                    # what their answer would do to it.
                    "verdict_turns_on": (
                        None
                        if item.hinge is None
                        else {
                            "unknown": item.hinge.unknown,
                            "if_confirmed": item.hinge.if_confirmed,
                            "if_denied": item.hinge.if_denied,
                        }
                    ),
                }
                for index, item in enumerate(boundaries, start=1)
            ],
            "earlier_turns": [
                {
                    "asked": message.question,
                    "replied": "" if message.answer is None else message.answer.answer,
                }
                for message in history
            ],
            "asked": asked,
        }
        # As in `_answer`, and under the same contract: the looking happens before the reply
        # is composed, from the input the reply will be composed from, and its findings enter
        # that input as one key. The scope this stage is under is a scope on the verdicts it
        # is shown and not on the repository it may read — see where the toolbox is built.
        findings = self._investigate(
            ReasoningTask.INVESTIGATE_FOR_ANSWER,
            canonical_json(payload),
            investigator,
            force_first=False,
        )
        if findings:
            payload["investigation"] = findings
        proposed = self._complete(
            ReasoningTask.DISCUSS_OPEN_QUESTION,
            payload,
            ProposedQuestionDiscussion,
            runtime_instruction=(
                f"Return exactly {expected} supported_by values, one for each boundary, in "
                "the order the boundaries appear above."
            ),
            schema_override=review_answer_schema(
                ProposedQuestionDiscussion, boundary_count=expected
            ),
            candidate_validator=lambda item: [
                *prose_defects("answer", item.answer),
                *(
                    [
                        f"supported_by must contain exactly {expected} values, one per "
                        f"boundary in order, but contains {len(item.supported_by)}"
                    ]
                    if len(item.supported_by) != expected
                    else []
                ),
            ],
            preview=preview,
        )
        return ReviewAnswer(
            answer=proposed.answer,
            supporting_references=[
                item.reference
                for item, supports in zip(boundaries, proposed.supported_by, strict=True)
                if supports
            ],
            suggested_answer=proposed.suggested_answer.strip(),
        )
    def _complete(
        self,
        task: ReasoningTask,
        payload: BaseModel | Mapping[str, object],
        output_type: type[Item],
        *,
        runtime_instruction: str = "",
        schema_override: Mapping[str, object] | None = None,
        candidate_validator: Callable[[Item], list[str]] | None = None,
        candidate_error_factory: (Callable[[Item], ModelOutputValidationError] | None) = None,
        allow_repair: bool = True,
        think: ThinkLevel = None,
        temperature: float | None = None,
        preview: ProsePreview | None = None,
    ) -> Item:
        contract = STAGE_PROMPTS[task]
        label = self._transport.provider_label
        data = payload.model_dump(mode="json") if isinstance(payload, BaseModel) else dict(payload)
        instruction = contract.request
        if runtime_instruction:
            instruction = f"{instruction}\n\nRun-specific constraints:\n{runtime_instruction}"
        messages = [
            {
                "role": "system",
                "content": contract.system_prompt,
            },
            {
                "role": "user",
                "content": f"{instruction}\n\nInput:\n{canonical_json(data)}",
            },
        ]
        try:
            content = self._chat(
                output_type,
                messages,
                task=task,
                schema_override=schema_override,
                think=self._think_for(think),
                temperature=temperature,
                preview=preview,
            )
            try:
                candidate = output_type.model_validate_json(content)
            except ValidationError as first_error:
                validation_errors = str(first_error)
            else:
                candidate_errors = (
                    candidate_validator(candidate) if candidate_validator is not None else []
                )
                if not candidate_errors:
                    return candidate
                validation_errors = "; ".join(candidate_errors)
            if not allow_repair:
                raise ModelOutputValidationError(
                    f"{label} returned invalid structured output: {validation_errors}"
                )
            repair_messages = [
                *messages,
                {"role": "assistant", "content": content},
                {
                    "role": "user",
                    "content": (
                        "The previous JSON failed validation. Return the complete corrected "
                        "JSON object only, under the same schema. Do not omit valid content. "
                        f"Validation errors:\n{validation_errors}"
                    ),
                },
            ]
            # Deliberately not previewed. The repair round rewrites a reply that failed
            # validation, so streaming it would replace text a reader is part-way through
            # with a second version of the same answer, and there is no honest way to
            # narrate that in a stream of fragments. The repaired answer lands whole.
            repaired = self._chat(
                output_type,
                repair_messages,
                task=task,
                schema_override=schema_override,
                think=self._think_for(think),
                temperature=temperature,
            )
            try:
                candidate = output_type.model_validate_json(repaired)
            except ValidationError as final_error:
                raise ModelOutputValidationError(
                    f"{label} returned invalid structured output after one repair pass: "
                    f"{final_error}"
                ) from final_error
            candidate_errors = (
                candidate_validator(candidate) if candidate_validator is not None else []
            )
            if candidate_errors:
                if candidate_error_factory is not None:
                    raise candidate_error_factory(candidate)
                raise ModelOutputValidationError(
                    f"{label} returned invalid structured output after one repair pass: "
                    + "; ".join(candidate_errors)
                )
            return candidate
        except (KeyError, TypeError, ValueError) as error:
            # A malformed response can still surface as one of these while it is mapped
            # back onto domain types. Transport failures are already `ProviderError`.
            raise ProviderError(f"{label} reasoning request failed: {error}") from error





    def _guard_prompt_budget(
        self,
        task: ReasoningTask,
        messages: list[ChatMessage],
        format_value: Mapping[str, object],
    ) -> None:
        """Refuse a request that cannot fit, rather than let it be truncated.

        The response schema is counted. Whether a provider spends prompt tokens on it or
        compiles it to a sampler grammar is a property of the build being talked to, and
        the fail-safe direction is to count it: over-counting refuses a borderline
        request with an explicit message, while under-counting reproduces exactly the
        silent front-truncation this exists to prevent.
        """

        prompt_characters = sum(
            len(message["role"]) + len(message["content"]) for message in messages
        )
        schema_characters = len(canonical_json(dict(format_value)))
        estimated_tokens = math.ceil(
            (prompt_characters + schema_characters) / self._config.chars_per_token
        )
        budget = self._config.context_window_tokens - self._config.max_output_tokens
        if estimated_tokens <= budget:
            return
        raise PromptBudgetExceededError(
            f"The {task.value} request does not fit the context window: "
            f"~{estimated_tokens} estimated prompt tokens "
            f"({prompt_characters} prompt characters plus {schema_characters} schema "
            f"characters at {self._config.chars_per_token} characters per token) "
            f"exceed the {budget} tokens left by a "
            f"{self._config.context_window_tokens}-token window reserving "
            f"{self._config.max_output_tokens} for output."
        )

    def _chat(
        self,
        output_type: type[Item],
        messages: list[ChatMessage],
        *,
        task: ReasoningTask,
        schema_override: Mapping[str, object] | None = None,
        think: ThinkLevel = None,
        temperature: float | None = None,
        preview: ProsePreview | None = None,
    ) -> str:
        # The schema is the full JSON Schema, not a generic "return JSON" flag: that
        # constrains generation to the exact shape rather than merely to valid JSON,
        # which is what makes enumerated handles and dispositions unrepresentable.
        resolved_schema: Mapping[str, object] = (
            schema_override if schema_override is not None else output_type.model_json_schema()
        )
        self._guard_prompt_budget(task, messages, resolved_schema)
        transport = self._transport
        # The budget guard runs first either way. A preview asked for by a stage whose
        # transport cannot stream is not an error and not worth reporting: the answer is the
        # same one, and the only difference is that no fragment arrives before it.
        if preview is not None and isinstance(transport, StreamingChatTransport):
            return accumulate_reply(
                transport.stream(
                    messages,
                    schema=resolved_schema,
                    task=task,
                    think=think,
                    temperature=temperature,
                ),
                preview,
            )
        return transport.complete(
            messages,
            schema=resolved_schema,
            task=task,
            think=think,
            temperature=temperature,
        )

#: Conformance to the optional streaming capability, stated so the type checker verifies it.
#: The application reaches this class through `isinstance`, which compares method names and
#: not signatures, so without this a drifted `stream_review_answer` would be caught by
#: nothing until it failed on the call. The class object rather than an instance: this needs
#: a configured transport to build, and nothing here needs one to check the signature.
_conforms: type[StreamingAnswerReasoner] = StructuredReasoningProvider
