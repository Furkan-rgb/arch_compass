"""The turns a stage may spend looking things up, and what it hands on afterwards.

One loop. A stage gives a model a toolbox and its own input, the model asks the repository
questions, and this renders what was asked and what came back as one block of text for the
stage that follows. Two caps bound it — how many turns, and how many characters of findings
— and both exist so an investigation terminates in front of a reader watching a review run.

Failure here degrades rather than propagates: investigating is an improvement to a question,
and the worst outcome allowed is a stage that asks the way it asked before.
"""

from __future__ import annotations

from collections.abc import Sequence

from archcompass.adapters.models.prompt_contracts import STAGE_PROMPTS
from archcompass.adapters.models.structured.chat_transports import (
    AssistantToolTurn,
    ChatTransport,
    InvestigationMessage,
    ThinkLevel,
    ToolCallingChatTransport,
    ToolResultTurn,
)
from archcompass.domain.base import canonical_json
from archcompass.domain.errors import ProviderError
from archcompass.ports.investigation import RecordedLookup, SourceInvestigator
from archcompass.ports.reasoning import ReasoningTask

#: How many rounds of tool calling one investigation may take before the stage has to ask
#: with what it has. Six is enough for a search, two reads and a check, which is the shape
#: the three worthwhile lookups take; past that a stage is browsing, and the failure a cap
#: prevents is not expense but an investigation that never terminates in front of a reader
#: watching a review run. The cap is spent without a further model call: a turn the loop
#: would not act on is a request nobody reads.
MAX_INVESTIGATION_TURNS = 6

#: The ceiling on what a whole investigation may hand the asking stage, in characters across
#: every recorded result. The per-result clamp bounds one answer and the turn cap bounds the
#: conversation's length, but neither bounds their product: a model may put several calls in
#: one turn, and six turns of many clamped results could still swell the elicitation request
#: until the budget guard refuses it — failing a stage whose worst permitted outcome is to
#: ask the way it always asked. Findings gathered before the ceiling are kept and said to be
#: cut short; five clamped results fit under it, which is more than any investigation worth
#: reading has needed.
MAX_INVESTIGATION_CHARACTERS = 20_000


def _rendered_investigation(
    transcript: Sequence[RecordedLookup],
    closing: str,
    abandoned: str,
) -> str:
    """What was looked up and what came back, as one block of text for the next stage.

    Rendered from the record rather than from the conversation, so what the asking stage
    reads is what a reader of this review could be shown: the call as it was made, with its
    arguments in the codebase's one canonical form, and the answer underneath it. Nothing is
    summarised — a lookup that found nothing is printed saying so, because "checked and
    empty" and "never checked" are opposite facts about a question.

    Empty when nothing happened at all, which is the signal the caller reads: no key is
    added, and the stage is told nothing rather than told that an investigation found
    nothing.
    """

    blocks = [
        f"{item.tool}({canonical_json(dict(item.arguments))})\n{item.result}"
        for item in transcript
    ]
    if closing:
        blocks.append(closing)
    if abandoned:
        # Named where the findings are, not logged away from them. A stage shown two results
        # and no note would take them for the whole of what could be found, and ask its
        # questions as though the repository had been read.
        blocks.append(f"investigation abandoned: {abandoned}")
    return "\n\n".join(blocks)


def investigate(
    transport: ChatTransport,
    task: ReasoningTask,
    payload_json: str,
    investigator: SourceInvestigator | None,
    *,
    # Whether the opening turn must produce a tool call. True for elicitation, which runs
    # once per review and proved it would skip looking when it was allowed to. False for
    # a conversation turn, which runs once per message and is usually about text already
    # in front of the stage: a forced lookup there spends a call answering a question
    # about the review's own words, and every such call is a result the reply has to
    # carry. The two stages differ in the one thing this flag names, so it is a flag
    # rather than two loops.
    force_first: bool = True,
    think: ThinkLevel = None,
) -> str:
    """Let the model look things up, and render what it looked at.

    Returns "" whenever there is nothing to render — no investigator, or a transport
    without the capability, or a model that decided immediately that it had nothing to
    check. That empty string is what keeps every provider behaving exactly as it did
    before this existed: the caller adds no key, and the request it sends is byte for
    byte the one it sent yesterday.

    What comes back is a rendering of the *transcript*, not of the conversation. The
    difference matters: the transcript is the record of what was asked of the repository
    and what it said, produced by the application, and it is the only part of this a
    later question can be traced to. The model's closing prose is appended after it
    because it is the one thing the record cannot hold — which of those findings it
    thought mattered — and it is appended rather than interleaved so it cannot be
    mistaken for a result.

    A `ProviderError` mid-investigation degrades to a note and does not propagate.
    Investigating is an improvement to a question, and losing an improvement must never
    cost the review that the question belongs to: the worst outcome allowed here is a
    stage that asks the way it asked before.
    """

    if investigator is None or not isinstance(transport, ToolCallingChatTransport):
        return ""
    contract = STAGE_PROMPTS[task]
    messages: list[InvestigationMessage] = [
        {"role": "system", "content": contract.system_prompt},
        {"role": "user", "content": f"{contract.request}\n\nInput:\n{payload_json}"},
    ]
    closing = ""
    abandoned = ""
    for turn in range(MAX_INVESTIGATION_TURNS):
        try:
            exchange = transport.complete_with_tools(
                messages,
                tools=investigator.tools,
                # Only the opening turn is ever constrained, and only where the stage
                # asked for it. Where it did, the repository gets first refusal on every
                # question and a first look is how that rule survives a model inclined
                # to skip it; from the second turn on, stopping is a judgement the model
                # must be free to make.
                require_call=force_first and turn == 0,
                task=task,
                think=think,
                temperature=None,
            )
        except ProviderError as error:
            abandoned = str(error)
            break
        if not exchange.calls:
            closing = exchange.text.strip()
            break
        messages.append(
            AssistantToolTurn(
                text=exchange.text,
                calls=exchange.calls,
                # Carried across untouched. What is in it is the transport's business —
                # a Gemini thought signature today — and the loop's only part in it is
                # not losing it on the way from the reply to the replay.
                vendor_state=exchange.vendor_state,
            )
        )
        # Every call is executed, including the ones after a failure, because a failure
        # is a result here — `call` never raises — and a model that asked three things
        # is owed three answers in the order it asked them.
        messages.extend(
            ToolResultTurn(
                call_name=call.name,
                content=investigator.call(call.name, call.arguments),
            )
            for call in exchange.calls
        )
        # Measured over the record rather than over the messages, because the record is
        # what the rendering below will hand the asking stage — and that stage's request
        # is the one the ceiling exists to keep inside its budget.
        if (
            sum(len(item.result) for item in investigator.transcript)
            >= MAX_INVESTIGATION_CHARACTERS
        ):
            abandoned = (
                "its findings reached the size ceiling, so nothing further was looked up"
            )
            break
    # Told to the investigator before anything is rendered, and on every way out of the
    # loop above. The rendering is spent on the next request; the investigator is what
    # the run that built it still holds, so this is the only route these two sentences
    # have to a record anybody can read afterwards.
    investigator.conclude(closing, abandoned)
    return _rendered_investigation(investigator.transcript, closing, abandoned)
