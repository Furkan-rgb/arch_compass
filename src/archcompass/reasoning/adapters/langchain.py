"""LangChain model boundary: Pydantic outside, frozen dataclasses inside."""

from __future__ import annotations

import json
from collections.abc import Sequence
from typing import Literal, cast

from langchain_core.language_models import BaseChatModel
from pydantic import BaseModel, Field, model_validator

from archcompass.domain import (
    ArchitectureCase,
    Candidate,
    CaseFacet,
    Evidence,
    Finding,
    Measurement,
    Policy,
    PolicyBearing,
    Question,
    Review,
    ReviewDelta,
    Verdict,
)
from archcompass.domain.errors import ModelOutputValidationError
from archcompass.ports.capabilities import ReviewSynopsis
from archcompass.ports.investigation import InvestigatorSource
from archcompass.ports.policy_retrieval import RetrievedPolicySet
from archcompass.ports.review_conversation import (
    ConversationAnswer,
    ConversationMessage,
)
from archcompass.reasoning.adapters.tool_loop import (
    investigate_with_tools,
    recorded_investigation,
)
from archcompass.retrying import call_with_retry


class PolicyBearingOutput(BaseModel):
    policy_position: int = Field(ge=1)
    reasoning: str = Field(min_length=1)


class FindingOutput(BaseModel):
    material: bool
    reasoning: str = Field(min_length=1)
    policy_bearings: list[PolicyBearingOutput] = Field(
        default_factory=list[PolicyBearingOutput]
    )
    hinge: str | None = None
    recommended_response: str | None = None

    @model_validator(mode="after")
    def response_only_for_material_finding(self) -> FindingOutput:
        if self.hinge and self.recommended_response:
            raise ValueError(
                "a finding with an uncertainty hinge cannot recommend a response"
            )
        if not self.material and self.recommended_response:
            raise ValueError("only a material finding may recommend a response")
        return self


class QuestionOutput(BaseModel):
    text: str = Field(min_length=1)
    facet: Literal[
        "goal", "constraint", "decision", "assumption", "expected_change", "non_goal"
    ]
    candidate_positions: list[int] = Field(min_length=1)
    # Answers the model thinks likely, so the common case is a click rather than an essay.
    #
    # Required now, where it used to be optional "when the honest answers are too open to
    # enumerate". That reasoning had the escape hatch in the wrong place: the interface
    # always offers writing your own and skipping outright, structurally, under every
    # question — so a menu is never a closed set and never needs the model to leave room for
    # one. Optional in the schema meant an empty list in practice, and an empty list is a
    # blank box, which is the thing the charter's "never make someone type what they could
    # pick" exists to prevent.
    #
    # Capped at four because a list long enough to need reading is slower than the sentence
    # it replaced.
    options: list[str] = Field(min_length=2, max_length=4)


class QuestionsOutput(BaseModel):
    questions: list[QuestionOutput] = Field(default_factory=list[QuestionOutput])


# The interface already offers writing your own answer and skipping the question, so a model
# that proposes those anyway is spending a choice on something the reviewer already has.
_ESCAPE_HATCHES = frozenset(
    {
        "dont know",
        "i dont know",
        "na",
        "none of the above",
        "none of these",
        "not applicable",
        "not sure",
        "other",
        "something else",
        "unknown",
        "unsure",
    }
)


def _is_escape_hatch(option: str) -> bool:
    bare = "".join(
        character
        for character in option.casefold()
        if character.isalnum() or character == " "
    )
    return bare.strip() in _ESCAPE_HATCHES


def _offered_answers(options: Sequence[str]) -> tuple[str, ...]:
    """The options worth showing: no escape hatches, and never a choice of one.

    Still tolerant of an empty result even though the schema now requires two. A model that
    spends both of its options on "other" and "not sure" has offered nothing, and the
    question is better asked with a blank box than with a menu of one.
    """

    kept = [option for option in options if not _is_escape_hatch(option)]
    return tuple(kept) if len(kept) > 1 else ()


class ConversationAnswerOutput(BaseModel):
    answer: str = Field(min_length=1)
    candidate_positions: list[int] = Field(default_factory=list[int])


def case_text(case: ArchitectureCase) -> str:
    """What a person has told ArchCompass about this architecture, so far.

    An empty case used to reach the model as `{"constraints": [], "decisions": [],
    "answers": []}`. That is three empty arrays next to a fully-stocked policy corpus, and
    a model reading it has a rule to judge against and a blank where the team's intent
    would be — so the cheapest coherent move is to judge on the policy and never ask. The
    empty case now says what it is, in a sentence, because "nobody has told us anything
    about this repository yet" is a fact worth acting on and `[]` is punctuation.
    """

    if not case.answers:
        return (
            "Nobody has answered anything about this architecture yet. This is the first "
            "review, or no judgement has needed a person so far — either way you are "
            "reading this repository without the team's intent, and you should say so "
            "wherever it would change your verdict."
        )
    return json.dumps(
        {
            "answers": [
                {
                    "question": item.question.text,
                    "status": item.status.value,
                    "value": item.value,
                }
                for item in case.answers
            ]
        },
        ensure_ascii=False,
    )


def structured_output[Output: BaseModel](
    model: BaseChatModel,
    schema: type[Output],
    prompt: str,
    *,
    subject: str,
    model_identity: str | None = None,
) -> Output:
    """One structured call, with the raw response kept so a refusal can be explained.

    `include_raw=True` is what makes a schema violation reportable instead of a bare
    `ValidationError` from somewhere inside the runnable: the call answers with the parsed
    value, the raw message, and the parsing error side by side. The cost is that the result
    is a mapping and never the schema, and forgetting that is exactly the bug this function
    exists to make impossible — two of the three callers used to cast the mapping straight to
    their schema and would have failed on the first attribute they read.
    """

    # Every model call in the application arrives here, which is why the retry sits here
    # too: one place to be sure a rate limit costs a wait rather than the whole review.
    # It wraps the call and nothing else — a response that arrives and fails its schema is
    # not a refusal, and asking again for it would only spend the quota faster.
    structured = model.with_structured_output(schema, method="json_schema", include_raw=True)
    result = cast(
        dict[str, object],
        call_with_retry(lambda: structured.invoke(prompt), subject=f"Producing {subject}"),
    )
    parsing_error = result.get("parsing_error")
    output = result.get("parsed")
    if parsing_error is None and isinstance(output, schema):
        return output

    raw_content = getattr(result.get("raw"), "content", "")
    preview = " ".join(str(raw_content).split())
    if len(preview) > 240:
        preview = preview[:237] + "..."

    named = (
        "The reasoning model"
        if model_identity is None
        else f"Reasoning model {model_identity}"
    )
    message = (
        f"{named} returned output that did not match the required JSON schema "
        f"for {subject}."
    )
    # The parser's own account of what was wrong, not just what was said. Without it a
    # cross-field rule the JSON schema cannot express — a hinge beside a recommendation —
    # reads as "the model returned nonsense", and the nonsense is well-formed JSON.
    if parsing_error is not None:
        reason = " ".join(str(parsing_error).split())
        message += f" The parser reported: {reason[:400]}"
    if preview:
        message += f" Response started with: {preview!r}."
    message += (
        " Judging is a structured call against a JSON schema, and not every model honours "
        "one. Choose a model whose runtime supports structured JSON output, or — on a "
        "model that offers it — enable Thinking."
    )
    if isinstance(parsing_error, Exception):
        raise ModelOutputValidationError(message) from parsing_error
    raise ModelOutputValidationError(message)


# Asking is an outcome, not a failure to reach one.
#
# The instruction always permitted a hinge, and in practice a model given a well-stocked
# policy corpus and an empty case judges on the policy and never states one — so the
# clarification round, which is the product's answer to "a codebase records what was built,
# not what the team was trying to build", almost never ran. The permission was there; the
# standing was not. So the contract now says out loud what the charter says: a confident
# wrong answer is worth less than an honest question, and a policy is a rule about
# architectures in general while a hinge is about this team's.
#
# It is deliberately not an instruction to ask more often. A hinge on something the
# evidence already settles is worse than no hinge at all: it stops a review to ask a person
# a question the repository answered.
JUDGEMENT_INSTRUCTION = (
    "Judge whether this detected structure costs more than it earns. "
    "Use only the supplied evidence and case. Policies are numbered from 1; "
    "refer to them only by position.\n\n"
    "Asking is a first-class outcome here, not a failure to decide. A policy tells you what "
    "is usually true of architectures; it cannot tell you what this team decided, what they "
    "are about to change, or what they already accepted and why. Where your verdict would "
    "turn on one of those, state one concise hinge naming the single fact you would need, "
    "and leave the recommended response empty: a judgement waiting on an answer does not "
    "yet recommend anything. A hinge stops the review and puts your question to a person, "
    "so it is worth their interruption — do not hinge on something the supplied evidence "
    "already settles, and do not hinge merely to avoid committing.\n\n"
    "Only a material finding with no hinge may recommend a response. "
    "Return only the structured response required by the supplied output schema. "
    "Do not return Markdown or explanatory prose outside the structured response."
)


def judgement_prompt(
    candidate: Candidate,
    case: ArchitectureCase,
    policies: RetrievedPolicySet,
) -> str:
    """The one prompt every transport sends.

    Shared rather than duplicated because a batched judgement and an interactive one have
    to be the same judgement — a review that was submitted as a batch is not allowed to
    have been asked a different question.
    """

    return "\n\n".join(
        (
            JUDGEMENT_INSTRUCTION,
            f"CASE\n{case_text(case)}",
            f"CANDIDATE\n{candidate_text(candidate)}",
            "POLICIES\n"
            + "\n\n".join(
                f"[{position}] {policy.title}\n{policy.body}"
                for position, policy in enumerate(policies.policies, start=1)
            ),
        )
    )


def candidate_text(candidate: Candidate) -> str:
    """One candidate laid out as sections a model can address, rather than as a repr.

    The dataclass repr was doing this job, and it escapes every newline in an excerpt: the
    code arrived as one very long line punctuated by literal ``\\n``. Measurements arrived
    the same way, so the ``structural_proxy`` tag that says "this count is a hint, not a
    fact" was present and unreadable at the same time.

    Relationships are stated before the evidence on purpose. Placement is what the verdict
    rests on — which abstraction is implemented by which adapter, and whether the parser or
    the type checker established it — and it should be read before the code rather than
    reconstructed from underneath it.
    """

    blocks = [f"pattern: {candidate.pattern}", f"summary: {candidate.summary}"]
    blocks.append(
        "participants:\n"
        + "\n".join(
            f"  - {item.qualified_name} — {item.role}" for item in candidate.participants
        )
    )
    if candidate.relationships:
        blocks.append(
            "relationships:\n"
            + "\n".join(
                f"  - {item.source} --{item.kind}--> {item.target} "
                f"(established by the {item.resolved_by} pass)"
                for item in candidate.relationships
            )
        )
    if candidate.measurements:
        blocks.append(
            "measurements:\n"
            + "\n".join(_measurement_text(item) for item in candidate.measurements)
        )
    if candidate.evidence:
        blocks.append(
            "evidence:\n"
            + "\n\n".join(_evidence_text(item) for item in candidate.evidence)
        )
    if candidate.limitations:
        blocks.append(f"what this detection method cannot see: {candidate.limitations}")
    return "\n\n".join(blocks)


def _measurement_text(measurement: Measurement) -> str:
    lines = [
        f"  - {measurement.name} = {measurement.display} [{measurement.nature.value}]"
    ]
    if measurement.definition:
        lines.append(f"    counts: {measurement.definition}")
    if measurement.limitations:
        lines.append(f"    cannot establish: {measurement.limitations}")
    return "\n".join(lines)


def _evidence_text(evidence: Evidence) -> str:
    where = (
        "location not recorded"
        if evidence.location is None
        else f"{evidence.location.path}:{evidence.location.start_line}"
        f"-{evidence.location.end_line}"
    )
    lines = [f"  - {evidence.description}", f"    {where}"]
    if evidence.note:
        lines.append(f"    note: {evidence.note}")
    if evidence.excerpt:
        lines.append("    ```")
        lines.extend(f"    {line}" for line in evidence.excerpt.splitlines())
        lines.append("    ```")
    else:
        lines.append("    (no code was read at this location)")
    return "\n".join(lines)


def finding_from_output(
    output: FindingOutput,
    candidate: Candidate,
    policies: RetrievedPolicySet,
    *,
    model_identity: str,
    prompt_identity: str,
) -> Finding:
    """The validated response as a domain finding, with the model's citations checked."""

    bearings: list[PolicyBearing] = []
    seen: set[int] = set()
    for bearing in output.policy_bearings:
        if bearing.policy_position > len(policies.policies):
            raise ValueError(
                f"model cited policy position {bearing.policy_position}, but only "
                f"{len(policies.policies)} policies were presented"
            )
        if bearing.policy_position in seen:
            raise ValueError("model cited one policy position more than once")
        seen.add(bearing.policy_position)
        bearings.append(
            PolicyBearing(policies.policies[bearing.policy_position - 1], bearing.reasoning)
        )
    verdict = (
        Verdict.HELD
        if output.hinge
        else Verdict.MATERIAL if output.material else Verdict.CLEARED
    )
    return Finding(
        candidate=candidate,
        verdict=verdict,
        reasoning=output.reasoning,
        policies=tuple(bearings),
        evidence=candidate.evidence,
        hinge=output.hinge,
        recommended_response=output.recommended_response,
        model_identity=model_identity,
        prompt_identity=prompt_identity,
        retrieval_identity=policies.provenance.identity,
    )


class LangChainArchitectureJudge:
    """One controlled structured call; the model never supplies ArchCompass identity."""

    def __init__(
        self,
        model: BaseChatModel,
        *,
        model_identity: str,
        prompt_identity: str = "judge:v2",
    ) -> None:
        self._model = model
        self._model_identity = model_identity
        self._prompt_identity = prompt_identity

    def judge(
        self,
        candidate: Candidate,
        case: ArchitectureCase,
        policies: RetrievedPolicySet,
    ) -> Finding:
        output = structured_output(
            self._model,
            FindingOutput,
            judgement_prompt(candidate, case, policies),
            subject="a review finding",
            model_identity=self._model_identity,
        )
        return finding_from_output(
            output,
            candidate,
            policies,
            model_identity=self._model_identity,
            prompt_identity=self._prompt_identity,
        )


class LangChainQuestionGenerator:
    def __init__(
        self, model: BaseChatModel, *, prompt_identity: str = "questions:v1"
    ) -> None:
        self._model = model
        self._prompt_identity = prompt_identity

    @property
    def prompt_identity(self) -> str:
        return self._prompt_identity

    def generate(
        self,
        case: ArchitectureCase,
        findings: tuple[Finding, ...],
        *,
        round: int,
        excluded_equivalence_keys: frozenset[str],
    ) -> tuple[Question, ...]:
        if not findings or not any(finding.hinge for finding in findings):
            return ()
        prompt = "\n\n".join(
            (
                "Ask only questions whose answers could settle the supplied findings. "
                "Merge duplicates. Candidate positions are numbered from 1. Do not invent "
                "identifiers and do not ask about a finding without a hinge.",
                "For each question, offer two to four answers you consider likely, in "
                "`options`, likeliest first. Each option must be a complete statement "
                "that could be recorded on the architecture case exactly as written — "
                "not a label like 'yes' or 'option A' — and the options must be "
                "mutually exclusive. Never offer 'other', 'none of these', 'unknown' or "
                "any variation: the reviewer is always offered writing their own answer "
                "and skipping the question, beneath every question, so offering it back "
                "to them wastes a choice. If you cannot name two likely answers, the "
                "question is too open to be worth a person's interruption — ask a "
                "narrower one instead.",
                f"CASE\n{case_text(case)}",
                "FINDINGS\n"
                + "\n".join(
                    f"[{position}] {finding.candidate.summary}; hinge={finding.hinge}"
                    for position, finding in enumerate(findings, start=1)
                ),
            )
        )
        output = structured_output(
            self._model, QuestionsOutput, prompt, subject="the review's questions"
        )
        questions: list[Question] = []
        seen: set[str] = set()
        for proposed in output.questions:
            positions = tuple(sorted(set(proposed.candidate_positions)))
            if any(position < 1 or position > len(findings) for position in positions):
                raise ValueError("model returned an unknown candidate position")
            if any(not findings[position - 1].hinge for position in positions):
                raise ValueError(
                    "model returned a candidate position for a finding without a hinge"
                )
            question = Question.create(
                text=proposed.text,
                facet=CaseFacet(proposed.facet),
                candidate_ids=tuple(
                    str(findings[position - 1].candidate.id) for position in positions
                ),
                round=round,
                options=_offered_answers(proposed.options),
            )
            if (
                question.equivalence_key not in excluded_equivalence_keys
                and question.equivalence_key not in seen
            ):
                seen.add(question.equivalence_key)
                questions.append(question)
        return tuple(questions)


# The contract a conversation is held to. It is deliberately not the judgement contract.
#
# A reader arrives at this box having already read a finding, and the question they type is
# usually "so what do I do about it". Answering that with "the review does not contain any
# information on how to fix the identified issues" is technically true of a document and
# useless to a person: what to do follows from what was found, and following from it is the
# job. So facts stay pinned to the review while reasoning over those facts is expected, and
# the answer says which of the two the reader is looking at.
CONVERSATION_CONTRACT = (
    "A reader has this architecture review open and is asking you about it.\n\n"
    "Two kinds of question arrive here. Some ask what the review found — answer those from "
    "the review alone. Others ask what to do about what it found: how a finding would be "
    "fixed, what the options are, which to take first. Answer those too. They are not "
    "outside the review; they are why somebody read it. Reason from the findings, the "
    "policies they bear on and any recommended response already recorded, and make plain "
    "which part of your answer the review records and which part is you reasoning from "
    "it.\n\n"
    "Facts about this codebase come only from the review. Do not invent a module, a call "
    "site or a name you were not shown. Where a fix turns on something the review does not "
    "establish, say what would have to be true and which finding's evidence would settle "
    "it. Say the review cannot answer only when it lacks the facts the question needs — "
    "never merely because the question asks for judgement.\n\n"
    "You are told where each piece of evidence sits, but not what the code at those lines "
    "says. So describe a fix as structure and placement, cite the locations, and do not "
    "write a patch as though you had read the file.\n\n"
    "Cite the findings you relied on by their numbered positions. Write prose a reader can "
    "act on: no headings, no restating the question."
)

#: Added to the contract only where the reader's repository can actually be asked. Kept
#: apart from `CONVERSATION_CONTRACT` because the sentence "you may look it up" is false
#: wherever no toolbox was offered, and a contract that says it anyway teaches a model to
#: claim it checked.
CONVERSATION_LOOKUPS = (
    "You can also ask this repository structural questions directly — what implements "
    "something, what depends on it, what calls it, what tests it, and what the code at a "
    "named part of it says. Use that where the review does not settle a question and the "
    "structure would. A fact still has to come from the review or from something you "
    "actually looked up; say which."
)


def _conversation_policies(review: Review) -> tuple[Policy, ...]:
    """Every policy this review's findings bear on, once each.

    Gathered here rather than repeated under each finding because the rule a fix has to
    respect is the same rule however many findings bore on it, and its wording is what makes
    a proposed fix answerable against it.
    """

    seen: dict[str, Policy] = {}
    for finding in review.findings:
        for bearing in finding.policies:
            seen.setdefault(bearing.policy.id, bearing.policy)
    return tuple(seen.values())


def _conversation_finding_text(position: int, finding: Finding) -> str:
    """One finding as breadth rather than depth.

    Judgement reads a single candidate in full, code included. A conversation ranges over
    every finding at once and cannot afford that, so it is given what each finding is, what
    it bears on, what was recommended, and where the evidence sits — but not the code at
    those lines. That is a click away in the workbench, which is exactly where citing a
    finding puts the reader.
    """

    candidate = finding.candidate
    lines = [
        f"[{position}] {candidate.summary}",
        f"    pattern: {candidate.pattern}",
        f"    verdict: {finding.verdict.value}",
        f"    reasoning: {finding.reasoning}",
    ]
    if finding.recommended_response:
        lines.append(f"    recommended response: {finding.recommended_response}")
    if finding.hinge:
        lines.append(f"    held, waiting on: {finding.hinge}")
    lines.extend(
        f"    bears on '{bearing.policy.title}' ({bearing.policy.strength.value}): "
        f"{bearing.reasoning}"
        for bearing in finding.policies
    )
    if candidate.participants:
        lines.append(
            "    participants: "
            + ", ".join(
                f"{item.qualified_name} ({item.role})" for item in candidate.participants
            )
        )
    lines.extend(
        f"    {item.source} --{item.kind}--> {item.target}"
        for item in candidate.relationships
    )
    lines.extend(
        f"    measured: {item.name} = {item.display} [{item.nature.value}]"
        + (f"; counts {item.definition}" if item.definition else "")
        for item in candidate.measurements
    )
    # `finding.evidence` is not a second, judged selection: every producer copies
    # `candidate.evidence` into it whole. Listing both put every excerpt in twice.
    lines.extend(
        f"    evidence: {_conversation_evidence_text(item)}"
        for item in candidate.evidence
    )
    if candidate.limitations:
        lines.append(f"    this detection cannot see: {candidate.limitations}")
    return "\n".join(lines)


def _conversation_evidence_text(evidence: Evidence) -> str:
    where = (
        "location not recorded"
        if evidence.location is None
        else f"{evidence.location.path}:{evidence.location.start_line}"
        f"-{evidence.location.end_line}"
    )
    note = f"; {evidence.note}" if evidence.note else ""
    return f"{evidence.description} ({where}){note}"


def conversation_prompt(
    review: Review,
    history: Sequence[ConversationMessage],
    question: str,
    *,
    transcript: str = "",
    can_look: bool = False,
    for_lookups: bool = False,
) -> str:
    repository = review.repository
    where = str(repository.path)
    if repository.branch:
        where += f" on {repository.branch}"
    if repository.commit:
        where += f" at {repository.commit[:12]}"
    sections = [
        *(
            ()
            if for_lookups
            # The loop sends the contract as a system message, so the turn that opens it
            # would otherwise state the rules twice.
            else (CONVERSATION_CONTRACT + (f"\n\n{CONVERSATION_LOOKUPS}" if can_look else ""),)
        ),
        f"REVIEW\nnumber {review.sequence} of {where}\nstatus: {review.status.value}",
        f"CASE\n{case_text(review.case)}",
    ]
    if review.questions:
        sections.append(
            "STILL UNANSWERED BY THE TEAM\n"
            + "\n".join(f"  - {item.text}" for item in review.questions)
        )
    policies = _conversation_policies(review)
    if policies:
        sections.append(
            "POLICIES THESE FINDINGS BEAR ON\n"
            + "\n\n".join(
                f"'{policy.title}' ({policy.strength.value})\n{policy.body}"
                for policy in policies
            )
        )
    sections.append(
        "FINDINGS\n"
        + "\n\n".join(
            _conversation_finding_text(position, finding)
            for position, finding in enumerate(review.findings, start=1)
        )
    )
    if history:
        sections.append(
            "WHAT HAS ALREADY BEEN ASKED HERE\n"
            + "\n".join(f"Q: {item.question}\nA: {item.answer.text}" for item in history)
        )
    if transcript:
        sections.append(f"WHAT YOU LOOKED UP\n{transcript}")
    sections.append(f"QUESTION\n{question}")
    return "\n\n".join(sections)


class LangChainReviewAnswerer:
    """A grounded answer, after whatever the reader's question made worth looking up.

    The lookups are optional and the first turn is never forced, unlike a hinge
    investigation's. A reader is usually asking about text already in front of them — "what
    does this finding mean", "which of these first" — and a forced call there spends a round
    trip asking the repository about the review's own words. Where the question *is* about
    the repository, the model reaches for the toolbox itself.
    """

    def __init__(
        self,
        model: BaseChatModel,
        investigators: InvestigatorSource | None = None,
    ) -> None:
        self._model = model
        self._investigators = investigators

    def answer(
        self,
        review: Review,
        history: tuple[ConversationMessage, ...],
        question: str,
    ) -> ConversationAnswer:
        offered = (
            None
            if self._investigators is None
            else self._investigators.for_review(review.repository, review.atlas)
        )
        investigator = None if offered is None else offered.investigator
        transcript = ""
        if investigator is not None:
            transcript = investigate_with_tools(
                self._model,
                investigator,
                system=CONVERSATION_CONTRACT + "\n\n" + CONVERSATION_LOOKUPS,
                opening=conversation_prompt(
                    review, history, question, can_look=True, for_lookups=True
                ),
                subject="a reader's question about this review",
                force_first=False,
            )
        output = structured_output(
            self._model,
            ConversationAnswerOutput,
            conversation_prompt(
                review,
                history,
                question,
                transcript=transcript,
                can_look=investigator is not None,
            ),
            subject="a grounded answer",
        )
        positions = tuple(sorted(set(output.candidate_positions)))
        if any(
            position < 1 or position > len(review.findings) for position in positions
        ):
            raise ValueError("model returned an unknown finding position")
        return ConversationAnswer(
            output.answer,
            tuple(
                str(review.findings[position - 1].candidate.id)
                for position in positions
            ),
            recorded_investigation(
                investigator,
                candidate_id="",
                withheld="" if offered is None else offered.withheld,
                atlas_fingerprint=review.repository.content_id,
            ),
        )


# The contract the review's opening paragraph is held to.
#
# The report already told the reader how many candidates were judged and in what states. A
# number is orientation and not an answer: "two material, three held" does not say whether
# the two are one problem seen twice, whether either can wait, or which one a person should
# open first. That is what this paragraph is for, and it is the only place in the product
# where the model is asked about a review rather than about a candidate.
#
# Everything it may say has already been judged. It is summarising, not judging again — so
# it gets verdicts, hinges, policies and delta states, and it gets no evidence, no
# measurements and no atlas, because a sentence about a line of code is a sentence it would
# be inventing.
SYNOPSIS_CONTRACT = (
    "You are writing the opening paragraph of an architecture review. It is read away from "
    "the tool — attached to a pull request, downloaded as a document, pasted into a "
    "channel — by somebody deciding whether to open the review at all.\n\n"
    "Say what this review amounts to. Lead with what needs a person: the material findings, "
    "whether they are separate problems or one problem in several places, and which to take "
    "first. Then what judgement is waiting on, if anything. Then what moved since the "
    "previous review, if there was one. Candidates that were cleared are worth a clause at "
    "most.\n\n"
    "Every fact must come from the findings below. Do not name a module, a metric or a "
    "policy you were not shown. Do not make a verdict sound stronger or weaker than it was "
    "recorded, do not recommend a fix that no finding recommends, and do not tell the "
    "reader the architecture is sound — this review saw the candidates it was given and "
    "nothing else. Where you say two findings are related, that relation has to be visible "
    "in what you were shown.\n\n"
    "Name a candidate by the identifier you were given, in backticks, and only where naming "
    "it is what makes the sentence useful. Three to five sentences of plain prose. No "
    "headings, no bullets, no counts — the line above yours already gives them."
)


class SynopsisOutput(BaseModel):
    summary: str = Field(min_length=1)


def _synopsis_finding_text(finding: Finding, delta_state: str | None) -> str:
    """One judged candidate, reduced to what a summary can honestly use."""

    name = finding.candidate.participants[0].qualified_name
    parts = [
        f"`{name}` — {finding.verdict.value}",
        f"pattern: {finding.candidate.pattern}",
        f"summary: {finding.candidate.summary}",
        f"reasoning: {finding.reasoning}",
    ]
    if delta_state:
        parts.append(f"since the previous review: {delta_state}")
    if finding.hinge:
        parts.append(f"waiting on: {finding.hinge}")
    if finding.recommended_response:
        parts.append(f"recommended response: {finding.recommended_response}")
    if finding.policies:
        parts.append(
            "bears on: "
            + "; ".join(item.policy.title for item in finding.policies)
        )
    return "\n  ".join(parts)


def _synopsis_delta_states(delta: ReviewDelta) -> dict[str, str]:
    states = {str(item.id): "new" for item in delta.new}
    for change in delta.changed:
        causes = ", ".join(cause.value for cause in change.causes)
        states[str(change.candidate.id)] = f"changed ({causes})" if causes else "changed"
    for item in delta.unchanged:
        states[str(item.id)] = "unchanged"
    return states


def synopsis_prompt(
    case: ArchitectureCase,
    findings: Sequence[Finding],
    *,
    questions: Sequence[Question],
    delta: ReviewDelta,
    previous_sequence: int | None,
    waiting: bool,
) -> str:
    """The one prompt the summary is written from."""

    states = _synopsis_delta_states(delta)
    sections = [SYNOPSIS_CONTRACT, f"CASE\n{case_text(case)}"]
    if waiting:
        sections.append(
            "THIS REVIEW IS NOT FINISHED. It is waiting on answers before it can judge "
            "everything, and the reader is told so above your paragraph. Summarise what it "
            "has so far and do not present it as settled."
        )
    sections.append(
        "FINDINGS\n"
        + "\n\n".join(
            _synopsis_finding_text(finding, states.get(str(finding.candidate.id)))
            for finding in findings
        )
    )
    if previous_sequence is None:
        sections.append(
            "This is the first review in its lineage, so there is nothing to compare it "
            "against and nothing has moved."
        )
    elif delta.addressed:
        sections.append(
            f"NO LONGER DETECTED SINCE REVIEW {previous_sequence}\n"
            + "\n".join(
                f"- {item.title} (last judged {item.last_verdict.value})"
                for item in delta.addressed
            )
        )
    if questions:
        sections.append(
            "QUESTIONS THIS REVIEW IS ASKING\n"
            + "\n".join(f"- {question.text}" for question in questions)
        )
    return "\n\n".join(sections)


class LangChainReviewSynopsist:
    """The model's account of the review it has just finished judging."""

    def __init__(self, model: BaseChatModel, *, model_identity: str = "") -> None:
        self._model = model
        self._model_identity = model_identity

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
        # Nothing judged is not a summary of nothing; it is a report that opens on the
        # sentence it already has, which says the analysis found no candidates and declines
        # to call that a clean bill of health. A model asked to summarise an empty list
        # would write the second half of that on its own.
        if not findings:
            return None
        prompt = synopsis_prompt(
            case,
            findings,
            questions=questions,
            delta=delta,
            previous_sequence=None if previous is None else previous.sequence,
            waiting=waiting,
        )
        output = structured_output(
            self._model,
            SynopsisOutput,
            prompt,
            subject="the review's summary",
            model_identity=self._model_identity or None,
        )
        text = output.summary.strip()
        return ReviewSynopsis(text, self._model_identity) if text else None
