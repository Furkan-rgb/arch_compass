"""The two stages that remain, and the contracts that make them checkable."""

from __future__ import annotations

from dataclasses import replace

from archcompass.adapters.models.deterministic import DeterministicReasoningProvider
from archcompass.adapters.models.prompt_contracts import (
    ANSWER_REVIEW_QUESTION,
    DISCUSS_OPEN_QUESTION,
    ELICIT_QUESTIONS,
    INVESTIGATE_FOR_ANSWER,
    INVESTIGATE_USAGE,
    JUDGE_FINDING_CANDIDATE,
    STAGE_PROMPTS,
    SUMMARISE_REVIEW,
)
from archcompass.domain.base import canonical_json
from archcompass.ports.reasoning import ReasoningTask


def _normalized(value: str) -> str:
    return " ".join(value.casefold().split())


def test_canonical_json_uses_one_serializer_for_models_and_mappings() -> None:
    payload = {"case_id": "case-test", "revision": 1}

    assert canonical_json(payload) == canonical_json(dict(payload))
    assert "'case_id': 'case-test'" not in canonical_json({"outer": payload})


def test_every_reasoning_task_has_a_contract_and_every_contract_a_task() -> None:
    """The enum and the registry must not drift; a gap surfaces as a runtime KeyError."""

    expected_versions = {
        ReasoningTask.JUDGE_FINDING_CANDIDATE: 12,
        ReasoningTask.INVESTIGATE_USAGE: 2,
        ReasoningTask.INVESTIGATE_FOR_ANSWER: 1,
        ReasoningTask.ELICIT_QUESTIONS: 5,
        ReasoningTask.SUMMARISE_REVIEW: 7,
        ReasoningTask.ANSWER_REVIEW_QUESTION: 9,
        ReasoningTask.DISCUSS_OPEN_QUESTION: 3,
    }

    assert set(STAGE_PROMPTS) == set(ReasoningTask)
    assert set(STAGE_PROMPTS) == set(expected_versions)
    identities = []
    for task, version in expected_versions.items():
        contract = STAGE_PROMPTS[task]
        assert contract.identity.startswith(f"{contract.name}:v{version}:")
        assert len(contract.content_fingerprint) == 12
        identities.append(contract.identity)
    assert len(identities) == len(set(identities))


def test_a_changed_prompt_changes_its_identity_without_a_version_bump() -> None:
    """Otherwise an audit trail names a prompt that was not the one actually run."""

    changed = replace(
        JUDGE_FINDING_CANDIDATE,
        request=JUDGE_FINDING_CANDIDATE.request + " Materially changed.",
    )

    assert changed.version == JUDGE_FINDING_CANDIDATE.version
    assert changed.identity != JUDGE_FINDING_CANDIDATE.identity


def test_the_shared_contract_still_carries_the_evidence_rules() -> None:
    shared = _normalized(JUDGE_FINDING_CANDIDATE.system_prompt)

    assert "evidence hierarchy" in shared
    assert "absence of evidence is not evidence of absence" in shared
    assert "minimum architecture" in shared


def test_the_judgement_contract_treats_both_errors_as_errors() -> None:
    """A stage that names one verdict as the default gets that verdict.

    Measured rather than assumed: while the contract said "not material is the ordinary
    answer", every error across four fixture runs was a false clear and none was a false
    condemn.
    """

    contract = _normalized(JUDGE_FINDING_CANDIDATE.stage_contract)

    assert "two errors are equally wrong" in contract
    assert "neither verdict is the safe one" in contract
    assert "condemning a shape that is earning what it costs" in contract
    assert "clearing one that is not" in contract
    assert "clearing reads as approval" in contract


def test_the_judgement_request_puts_the_argument_before_the_verdict() -> None:
    """Field order is the reasoning order; the request must not contradict the schema."""

    request = _normalized(JUDGE_FINDING_CANDIDATE.request)

    assert "answer the fields in the order they appear" in request
    assert request.index("first, in rationale") < request.index("only then set verdict")
    assert "never write a policy's name, number or identifier" in request


def test_the_answer_contract_forbids_writing_a_reference_code() -> None:
    """Grounding is positional; a code in model text would be a key the model authored."""

    request = _normalized(ANSWER_REVIEW_QUESTION.request)

    assert "never write a br- code" in request
    assert "in the order the boundaries were supplied" in request


def test_the_answer_contract_says_what_the_conclusion_is_and_is_not() -> None:
    """It is shown so a reader's question is answerable, not as a second source of fact.

    The conclusion is composed from the same verdicts, so a stage that read it as evidence
    could ground an answer in a synthesis of the thing it was meant to be citing.
    """

    contract = _normalized(ANSWER_REVIEW_QUESTION.stage_contract)

    assert "adds no fact about the repository" in contract
    assert "cite boundaries, never the conclusion" in contract
    assert "the boundaries are what happened" in contract


def test_the_answer_contract_sends_a_question_to_the_boundary_it_is_about() -> None:
    """v3 said what to cite and nothing about what to read, and got the difference.

    Shown the conclusion, a live conversation answered three escalating "why"s out of it —
    each turn longer, none carrying a measurement, a policy or the case — and said so in as
    many words while citing a boundary whose record it had never opened. Naming the
    conclusion an index is the half of the fix that lives in the contract; the positions it
    now carries are the half that lives in the payload.
    """

    contract = _normalized(ANSWER_REVIEW_QUESTION.stage_contract)
    request = _normalized(ANSWER_REVIEW_QUESTION.request)

    assert "an index, not a source" in contract
    assert "positions of the boundaries it was built from" in contract
    assert "never write that something is so according to the conclusion" in contract
    # Saying less than the record holds is a failure too, which v3 never said anywhere.
    assert 'restating the verdict is not an answer to "why"' in request


def test_the_answer_contract_reports_a_verdict_at_odds_with_its_reasoning() -> None:
    """Resolving it silently is what produced a fabricated rationale.

    Asked why a boundary was condemned when its stored reasoning argued the opposite, the
    stage invented a reason that fit the verdict and stated it as the review's finding.
    Nothing had told it the two could disagree, so there was no sanctioned answer but to
    make them agree.
    """

    contract = _normalized(ANSWER_REVIEW_QUESTION.stage_contract)

    assert "reasoning and its verdict can disagree" in contract
    assert "that contradiction is the answer" in contract


def test_the_judgement_request_names_which_word_means_which_verdict() -> None:
    """The polarity has to be stated where the choice is made, not only downstream.

    It was already spelled out in three consuming places — the answer stage, the summary
    stage and the report headline — and in none of them could it prevent the flag being
    recorded backwards in the first place.
    """

    request = _normalized(JUDGE_FINDING_CANDIDATE.request)

    assert "should_change when that argument concluded the pattern is a problem" in request
    assert "leave_as_is when it concluded the shape is earning what it costs" in request
    assert "read your own rationale back before you choose" in request
    # The exact sentence one live run wrote into `recommended_response` beside "should change".
    assert "the current abstraction is appropriate" in request


def test_the_summary_contract_separates_prose_fields_from_grounded_ones() -> None:
    """v3 said "every statement carries one supported_by flag", of four fields.

    Two of those fields are prose, and one of them — `situation` — reads exactly like a
    statement, so a live run wrote `{"statement": ..., "supported_by": [...]}` into it as
    text. The contract now names which fields carry grounding and which are sentences.
    """

    request = _normalized(SUMMARISE_REVIEW.request)

    assert "situation and limits are prose" in request
    assert "never write an object or a list into either of them" in request
    assert "every entry in those two lists — and nothing else in the reply —" in request


def test_the_substitute_names_the_same_prompts_as_the_real_registry() -> None:
    """A stage the substitute cannot identify is one the test suite never really ran."""

    substitute = DeterministicReasoningProvider()

    for task in ReasoningTask:
        assert substitute.prompt_identity(task)


def test_the_judgement_request_makes_an_unnameable_hinge_the_other_answer() -> None:
    """A half-filled hinge is not a weaker hinge, and the contract has to say so.

    A live `gemma4:26b` run set `turns_on_this_unknown` and left the three fields blank,
    twice, through the repair round. The adapter drops such a hinge rather than raising;
    this is the half of the fix that stops it being produced.
    """

    request = _normalized(JUDGE_FINDING_CANDIDATE.request)

    assert "if you cannot name the unknown" in request
    assert "then the answer is stands_either_way" in request
    assert "say nothing was open rather than that something was, unnamed" in request


def test_the_judgement_request_keeps_the_hinge_inside_the_argument() -> None:
    """Field order is the reasoning order, and a hinge is part of what the verdict rests on."""

    request = _normalized(JUDGE_FINDING_CANDIDATE.request)

    assert request.index("first, in rationale") < request.index("then fill in hinge")
    assert request.index("then fill in hinge") < request.index("only then set verdict")
    # The unknown must be the reader's to settle, not the repository's or nobody's.
    assert "whether requirements might change" in request
    assert "asking them to do the detector's job" in request


def test_the_judgement_contract_makes_the_stage_read_the_case_before_asking() -> None:
    """Saying what a hinge is for was not enough to stop it hinging everything.

    A live `gemma4:26b` run hinged 8 of 8 on the *complete* `speech-vendor` case, one
    verdict resting on "whether a second speech vendor is actually being introduced" against
    a case whose expected_future_changes opens by saying one is under contract. The check
    against the case is now a step with an order and a named failure rather than a property
    the stage was expected to infer from what a hinge is for.
    """

    contract = _normalized(JUDGE_FINDING_CANDIDATE.stage_contract)

    assert "before you claim the case is silent, go and look" in contract
    # The fields it must actually look in, so "the case" is not left as an abstraction.
    for field in ("expected_future_changes", "confirmed_facts", "non_goals", "clarifications"):
        assert field in contract
    assert "the case answered you" in contract
    assert "a partial answer in the case is still an answer" in contract
    assert "a hinge on every boundary is the same as a hinge on none" in contract


def test_the_judgement_contract_reads_the_answers_already_given() -> None:
    """What terminates the loop, asserted where the rule actually lives.

    A hinge becomes a question, so a stage that cannot recognise an answer it has already been
    given hinges on the same fact for ever and the reader is handed back a question they have
    replied to. The answers arrive as `clarifications` — the question a review asked beside what
    the reader wrote — and this is the one place the check against them can be made.
    """

    contract = _normalized(JUDGE_FINDING_CANDIDATE.stage_contract)

    assert "clarifications is where an earlier round of this same asking was recorded" in contract
    assert "must not be asked a second time" in contract
    assert "that is what brings this loop to an end" in contract
    # And an answer is not a weaker sort of evidence for being phrased as a reply: the force
    # is the field its bears_on names, or the pair says less than the line it replaced did.
    assert "carries the same force as an entry in the field its bears_on names" in contract
    assert "binds the design exactly as a listed constraint does" in contract


def test_the_judgement_contract_says_what_the_code_in_front_of_it_is_for() -> None:
    """The stage now sees source, and a stage shown evidence must be told what it weighs.

    Two properties, and the second is the one that was measured. Naming the field is not
    enough: a prototype that showed the code without saying a claim must cite it produced
    rationales that agreed with the excerpts by coincidence and contradicted them elsewhere.
    A verdict about what code does now has to point at the lines it rests on, and the
    comments beside a definition are named as part of what a constant means — that is where
    the decisive fact sat in every bench case.
    """

    contract = _normalized(JUDGE_FINDING_CANDIDATE.stage_contract)

    assert "source_evidence is the code at this candidate's recorded spans" in contract
    assert "read by the application" in contract
    assert "a claim about what this code does must cite it" in contract
    assert "the copies are one fact" in contract
    assert "a comment beside a definition is part of what the constant means" in contract


def test_the_judgement_contract_says_what_it_means_when_there_is_no_code() -> None:
    """The field is absent on a candidate whose spans could not be read, and absence lies.

    A stage told to cite source and then given none either invents a citation or refuses a
    verdict it is perfectly able to reach from structure. So the contract names the third
    answer: judge from the structure, and say in the rationale that it was all there was.
    """

    contract = _normalized(JUDGE_FINDING_CANDIDATE.stage_contract)

    assert "where source_evidence is absent, the structure alone is the evidence" in contract
    assert "and your rationale may say so" in contract


def test_the_elicitation_request_asks_for_a_force_rather_than_a_destination() -> None:
    """`answer_belongs_in` stopped naming a list the moment the pair became the record.

    The answer used to be composed into one of five lists, so the field really was a
    destination. It is not moved anywhere now — the question and the answer stay together —
    and what the field decides is how a later judgement weighs the pair. A stage still told it
    is filing a sentence would pick by where the words look tidiest rather than by what the
    answer does.
    """

    request = _normalized(ELICIT_QUESTIONS.request)
    contract = _normalized(ELICIT_QUESTIONS.stage_contract)

    assert "set answer_belongs_in to the force the answer would carry" in request
    assert "recorded in the case as a question-and-answer pair" in request
    assert "nothing is moved anywhere" in request
    # The `unknown` is no longer half of a composed line, and the request must not still say
    # it is: a stage told to write a subject for a join writes for a join that never happens.
    assert "joins this to the reader's answer" not in request
    # And the stage that asks is told not to ask twice.
    assert "do not ask again what one of them already answers" in contract


def test_the_investigation_contract_bounds_what_looking_is_for() -> None:
    """The one stage that chooses its own evidence, told what it may choose it for.

    §12.0 is amended for asking and not for judging, and the whole of the amendment's safety
    is that this stage cannot decide anything: it may find out how something is used, and it
    may not propose a change or re-open a verdict. Said in the contract because there is no
    schema here to say it in — an investigation turn is unconstrained text and tool calls.
    """

    contract = _normalized(INVESTIGATE_USAGE.stage_contract)

    # v2's rule: the code's kind of question must be looked up, the reader's kind left alone.
    assert "the repository gets first refusal" in contract
    assert "is your kind, and every question of that kind" in contract
    assert "is the reader's kind, and no amount of reading answers it" in contract
    assert "stop when every concern of your kind is settled" in contract
    assert "do not propose a change" in contract
    # The three kinds of question that were being handed to the reader, named.
    assert "how a flagged element is actually used" in contract
    assert "whether two constants stating one value state one fact" in contract
    assert "whether a configuration value is consumed" in contract
    # The discipline the first trial showed a search-only model lacks.
    assert "a search hit is a line, not its meaning" in contract
    # And the reason the amendment holds: nothing here is invisible.
    assert "everything you look at is recorded" in contract


def test_the_two_investigation_contracts_pull_in_opposite_directions() -> None:
    """Same two tools, and the restraint inverts — which is why they are two contracts.

    Elicitation prepares questions for a person, so the repository gets first refusal on
    every one of them and its opening turn is forced at the transport. A conversation turn
    prepares a reply to a person who has already asked, and most of what they ask is about
    the review's own reasoning, which no lookup improves. A stage told to look before it may
    speak would spend a call on "why was this boundary condemned?", so this one says plainly
    that returning nothing is the common right move.
    """

    asking = _normalized(INVESTIGATE_USAGE.stage_contract)
    answering = _normalized(INVESTIGATE_FOR_ANSWER.stage_contract)

    assert "the repository gets first refusal" in asking
    assert "the repository gets first refusal" not in answering
    assert "returning no tool calls at all is therefore the common right move" in answering
    assert "only where the question turns on what the code does" in answering
    # The two rules both contracts hold, because they are what make the amendment safe.
    assert "a search hit is a line, not its meaning" in answering
    assert "do not propose a change" in answering
    assert "do not re-open a verdict" in answering
    assert "everything you look at is recorded and shown to the person who asked" in answering


def test_both_conversation_contracts_read_their_own_findings() -> None:
    """The findings are this stage's own lookups, and they still ground nothing.

    Two rules and they are not the same rule. The first is that a claim the investigation
    settles is stated from it — a stage reading it as somebody else's report writes "the
    review saw this, but you should confirm it" about a repository it just read. The second
    is that grounding does not widen: only a boundary can be marked, so a finding that rests
    on a lookup alone says where it came from and marks nothing.
    """

    for contract in (ANSWER_REVIEW_QUESTION, DISCUSS_OPEN_QUESTION):
        text = _normalized(contract.stage_contract)
        assert "an `investigation` field may be present in the input" in text
        assert "read it as your own findings rather than as somebody's report" in text
        assert "the investigation is not a boundary and never becomes one" in text
        # An absent or abandoned investigation is a stated fact rather than an empty one.
        assert "nothing was checked" in text
        # And the lookups are disclosed beside the reply, which is why the stage points at a
        # line instead of copying it — the same rule `source` is already under.
        assert "name the file and the line rather than copying the lines out" in text


def test_the_elicitation_contract_reads_its_own_findings_before_it_asks() -> None:
    """A question the stage has already answered for itself must not reach a person.

    The findings arrive as `investigation`, and a stage not told what that field is would
    read it as somebody else's report — which is the reading that produces "the review saw
    this, but you should confirm it" instead of a question worth a reader's afternoon.
    """

    contract = _normalized(ELICIT_QUESTIONS.stage_contract)

    assert "an `investigation` field may be present in the input" in contract
    assert "a question the investigation already answers must not be asked" in contract
    assert "may be stated in `what_the_review_saw`" in contract
    # An abandoned or absent investigation is a stated fact rather than an empty one.
    assert "nothing was checked" in contract


def test_the_summary_contract_reads_a_clarification_as_part_of_the_case() -> None:
    """This stage only ever runs on an answered case, so the answers are its material.

    They reach it as pairs in `clarifications` rather than as lines appended to the five
    deciding lists. A stage not told what a pair is would read the sentences that moved every
    verdict it is summarising as an exchange printed beside the case instead of as what the
    case now says.
    """

    contract = _normalized(SUMMARISE_REVIEW.stage_contract)

    assert "that case will usually carry a clarifications list" in contract
    assert "weighs exactly as much as an entry in the field its bears_on names" in contract
    assert "part of what the case states rather than as commentary beside it" in contract


def test_the_judgement_contract_names_the_two_ways_a_stage_hedges() -> None:
    """Both measured on `warehouse-sync`, which hinged 5 of 5 where 2 was right.

    They are the failures that survive the "go and look" check of v8: the stage reads the
    case, finds the fact, and hinges on whether it will *stay* true — which can be asked of
    every fact in every case and separates nothing — or hinges on the very question it was
    asked to decide, which the reader cannot answer because it was never theirs.
    """

    contract = _normalized(JUDGE_FINDING_CANDIDATE.stage_contract)

    assert "look like diligence here and are refusals to decide" in contract
    assert "whether a stated fact will stay true" in contract
    assert "judge the case as it stands" in contract
    assert "the question you were asked" in contract
    assert "it is the verdict left unmade" in contract


def test_the_judgement_contract_will_not_read_silence_as_evidence() -> None:
    """A case may now say nothing at all, and that must not condemn everything.

    Measured before it was allowed: told nothing about the future, a run condemned three
    boundaries the written case justifies, because nothing in the case justified them. Read
    that way an unwritten case is evidence against every boundary at once, and the advisor
    becomes the abstraction destroyer §3.1 exists to correct — on the first run a new user
    sees. The rule was already in the shared contract; this applies it where the verdict is
    actually made.
    """

    contract = _normalized(JUDGE_FINDING_CANDIDATE.stage_contract)

    assert "a case may say nothing at all" in contract
    assert "absence of evidence is not evidence of absence" in contract
    assert "leave it as it is and put what you were not told in the hinge" in contract
    # And silence must not become a blanket excuse in the other direction either.
    assert "a silent case is not a reason to clear a constant copied into four modules" in contract


def test_the_answer_contract_shows_the_code_rather_than_reporting_it_absent() -> None:
    """The record always held the spans; the stage was never given the lines.

    Asked to show the problematic code, a live conversation answered that the review "only
    contains the names of these modules and does not include the specific lines of code".
    True of what reached the stage, false of what the review holds — every participant
    carries an exact span, and those lines now arrive as `source` on each boundary.
    """

    contract = _normalized(ANSWER_REVIEW_QUESTION.stage_contract)
    request = _normalized(ANSWER_REVIEW_QUESTION.request)

    assert "each boundary carries `source`" in contract
    assert "never answer that the review does not contain it" in contract
    # An absence is stated rather than hidden: "this repository has changed since the review
    # ran" is the answer, and dropping it would let the stage conclude there is no source.
    assert "where an entry carries `why_there_is_no_code` instead" in contract
    # The lines are there to be reasoned about, not copied out — the marking is what puts
    # them on screen, and the rendering is the application's.
    assert "read the `source` lines and answer from what they show" in request


def test_the_answer_contract_separates_a_repository_claim_from_craft() -> None:
    """The refusal rule was right, and was being applied to the wrong category.

    "Where the record does not settle what was asked, say what is missing" stops a review of
    six boundaries speaking about a seventh. Applied to "show me how to carry out the
    consolidation you recommended" it produced three refusals in a row, because the contract
    had no category for demonstrating a recommendation it had already made and grounded.
    """

    contract = _normalized(ANSWER_REVIEW_QUESTION.stage_contract)
    request = _normalized(ANSWER_REVIEW_QUESTION.request)

    # The original rule survives in both halves, narrowed to what it was always about.
    assert "a review that examined six boundaries cannot speak about a seventh" in contract
    assert "does not settle a *fact about this repository*" in request
    # And the category it was crowding out is named.
    assert "that rule is about **claims concerning this repository**" in contract
    assert "is not a claim about the repository" in contract
    assert "do it. write the example" in contract
    assert (
        '"the review does not contain example fix snippets" is a refusal to do your job'
        in request
    )


def test_an_illustrated_fix_is_grounded_and_labelled_as_an_illustration() -> None:
    """It may demonstrate a recommendation; it may not present one as a reviewed result."""

    contract = _normalized(ANSWER_REVIEW_QUESTION.stage_contract)
    request = _normalized(ANSWER_REVIEW_QUESTION.request)

    assert "it rests on the boundary whose recommendation it illustrates" in contract
    assert "the review did not run it, test it or verify it" in contract
    # Permission to write code is not permission to invent a repository.
    assert "build it from `source` and not from memory" in contract
    assert "do not invent a module, a function or an import you were not shown" in contract
    assert "say that it is an illustration of the recommendation" in request


def test_the_answer_contract_never_asks_the_model_to_reproduce_the_repository() -> None:
    """The rule §12.0 already held, applied to the place that escaped it.

    An earlier version told the stage to copy the source "character for character", which is
    the one remedy §12.0 rules out: a model that must reproduce a value to be understood will
    eventually reproduce it wrongly, silently, and plausibly. It did — `"chelsine"` for
    `"chelsie"` — after that instruction landed.

    So reproduction moved to the side that already holds the characters, and this asserts the
    instruction is gone rather than merely softened. Left in, a later edit could reasonably
    read "be exact" as the rule and tighten it again.
    """

    contract = _normalized(ANSWER_REVIEW_QUESTION.stage_contract)
    request = _normalized(ANSWER_REVIEW_QUESTION.request)

    assert "**do not reproduce those lines in your answer.**" in contract
    assert "read the `source` lines and answer from what they show, without copying" in request
    # The reason is the division of labour, not the stage's accuracy. Phrasing it as care
    # is what produced the instruction this replaced.
    assert "the application already holds every one of these characters" in contract
    # The rules that told it to copy are gone, not reworded.
    for banned in (
        "copy those lines character for character",
        "transcribe them exactly",
        "quote the `source` lines when they are what is being asked about",
    ):
        assert banned not in contract and banned not in request

    # Composing an illustration is the one exception, and is named as a different act rather
    # than as a licence to be less careful.
    assert "illustrating is composing something that does not exist yet" in contract
    assert "this is the one thing you write in a code block" in request or (
        "the one thing you write in a code block" in request
    )


def test_the_answer_contract_carries_the_round_that_produced_it() -> None:
    """Asked what the questions and answers were, a review said it holds no such record.

    True of the review it was shown — `summarise_review` has no field for a question, which
    is what ends the elicitation loop — and false of the workspace, which keeps the questions
    on the first pass and the answers on the case revision this pass ran against.
    """

    contract = _normalized(ANSWER_REVIEW_QUESTION.stage_contract)
    request = _normalized(ANSWER_REVIEW_QUESTION.request)

    assert "`elicitation_round` is the round of questions this review grew out of" in contract
    assert "never that the review holds no record of them" in contract
    # A skipped question is evidence about why a verdict still hinges, not an omission to
    # pass over — which is the reading that makes carrying skips worth anything.
    assert "a question shown as skipped is worth as much as an answered one" in contract
    assert "answer from `elicitation_round`" in request


def test_no_contract_tells_a_model_to_reproduce_what_the_application_holds() -> None:
    """Across every stage, not only the one that got it wrong.

    Invariant 22's checkable sentence was "nothing the model writes is used as a key", and a
    retyped code snippet is not a key — nothing looks it up. So the letter of the rule
    permitted the instruction that produced a false quotation, and the prose explaining why
    lived a section away in §12.0. This is the missing enforcement: an instruction to
    transcribe, copy or reproduce is a defect wherever it appears, and the phrasings below
    are the ones that were actually written before anyone noticed.

    Deliberately a banned-phrase list rather than a judgement about intent. It is coarse, and
    coarse is what makes it hold: a future edit reaching for "be exact about the source"
    trips it and has to argue with this docstring instead of with nobody.
    """

    forbidden = (
        "character for character",
        "transcribe them exactly",
        "transcribe it exactly",
        "copy them exactly",
        "copy it exactly",
        "reproduce the source",
        "reproduce these lines",
        "quote it verbatim",
        "verbatim copy",
        "same identifiers, same spelling",
    )

    for task, contract in STAGE_PROMPTS.items():
        halves = (
            _normalized(contract.system_prompt),
            _normalized(contract.stage_contract),
            _normalized(contract.request),
        )
        for phrase in forbidden:
            assert not any(phrase in half for half in halves), (
                f"{task.value} instructs the model to reproduce source ({phrase!r}). "
                "Where the application already holds the value, the stage points at it and "
                "the interface renders it — see invariant 22 and §12.0."
            )
