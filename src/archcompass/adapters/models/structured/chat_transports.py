"""How this package talks to a vendor, and what one exchange can contain.

Three protocols and the small vocabulary they speak. `ChatTransport` is the one call every
stage needs; the other two are capabilities a vendor either has or has not — streaming a
reply as it is generated, and letting a model call tools before it answers — checked with
`isinstance` so a transport without one simply omits the method and every stage goes on
working.

A transport owns request options, timeouts, retries, and turning a vendor's failure into
`ProviderError`. It decides nothing about content: the messages, the schema and the budget
check have all happened above it.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Iterable, Iterator, Mapping, Sequence
from dataclasses import dataclass
from typing import Literal, Protocol, runtime_checkable

from archcompass.ports.investigation import ToolSpec
from archcompass.ports.reasoning import ReasoningTask

#: One turn of the conversation sent to a model, in the role/content form every chat
#: API accepts. A transport reshapes it into whatever its own SDK wants.
ChatMessage = dict[str, str]

#: Reasoning-effort control: off, on, or an explicit level. Named after Ollama's
#: `think` parameter because that is where it was first needed; a transport whose
#: vendor spells it differently maps it.
ThinkLevel = bool | Literal["low", "medium", "high"] | None


@dataclass(frozen=True)
class ProsePreview:
    """Which string field to report as it is generated, and where to send it.

    A preview is a preview. Nothing sent to `emit` is stored, validated, or bound to
    anything: the reply that counts is the one this stage validates whole, after generation
    finishes, exactly as it would have without a preview. What the reader gains is the
    prose arriving as it is written rather than after the last token.

    Only a field the schema puts first can be previewed usefully, which is why
    `ProposedReviewAnswer` declares `answer` before `supported_by` — a reason it already had
    (master plan 12.0, field order) and now also depends on.
    """

    #: The name of the string property to decode a prefix of, as it appears in the schema.
    field: str
    #: Called with each new fragment of that field, never with text already sent.
    emit: Callable[[str], None]


def prose_prefix(field: str, partial: str) -> str:
    """Decode as much of one string field as has arrived in an incomplete JSON document.

    A streamed structured reply is not JSON until its last token, so nothing can parse it
    while it is growing. What can be done is narrower: find the field, then hand the bytes
    that have arrived to the real JSON decoder by closing the string. That keeps escape
    handling — `\\n`, `\\"`, `\\uXXXX` — in the decoder rather than reimplementing it here,
    where a subtly different reading would show the reader text the model did not write.

    Returns "" until the field's opening quote has arrived, and a growing prefix after that.
    The result never shrinks: an incomplete trailing escape is dropped and returns with the
    chunk that completes it, so a caller may treat the difference as the new fragment.
    """

    marker = f'"{field}"'
    key = partial.find(marker)
    if key < 0:
        return ""
    cursor = key + len(marker)
    # Only a colon and whitespace may sit between the key and its value. Anything else means
    # this is not the string property it names — a substring of some other field's text, or a
    # non-string value — and guessing would print the wrong thing.
    separator = partial[cursor:]
    stripped = separator.lstrip()
    if not stripped.startswith(":"):
        return ""
    value = stripped[1:].lstrip()
    if not value.startswith('"'):
        return ""
    body = value[1:]
    escaped = False
    for offset, character in enumerate(body):
        if escaped:
            escaped = False
            continue
        if character == "\\":
            escaped = True
            continue
        if character == '"':
            body = body[:offset]
            break
    # Trim back over an escape the stream has not finished sending. `\uXXXX` is the longest,
    # so five characters is the whole search space; a still-unparseable tail is text this
    # cannot read and is reported as nothing rather than as a guess.
    for trim in range(6):
        candidate = body[: len(body) - trim] if trim else body
        try:
            decoded = json.loads(f'"{candidate}"')
        except ValueError:
            continue
        return decoded if isinstance(decoded, str) else ""
    return ""


class ChatTransport(Protocol):
    """One vendor's chat API, reduced to the single call this package needs.

    An implementation encodes the supplied messages and JSON Schema for its API, applies
    its own options and retry policy, and returns the response text. It decides nothing
    about content: the messages, the schema, and the budget check have already happened.

    Every failure it cannot complete must surface as `ProviderError`, so the stage logic
    above never handles a vendor's exception types.
    """

    #: How this provider is named in an error a user reads, e.g. "Ollama".
    provider_label: str

    def complete(
        self,
        messages: list[ChatMessage],
        *,
        schema: Mapping[str, object],
        task: ReasoningTask,
        think: ThinkLevel,
        temperature: float | None,
    ) -> str: ...


@runtime_checkable
class StreamingChatTransport(Protocol):
    """A transport that can also report one reply's text as it is generated.

    Separate from `ChatTransport` and checked with `isinstance`, because streaming a
    schema-constrained reply is a property of a vendor's API rather than of this package: a
    transport that cannot do it omits the method and every stage still works, answering after
    the last token instead of during. Adding `stream` to `ChatTransport` would instead make
    every transport claim a capability and raise when asked to use it.

    That check is by name only. `runtime_checkable` compares which methods exist and nothing
    about their signatures, and a transport is held here as a `ChatTransport`, which says
    nothing about streaming — so a drifted `stream` would pass `isinstance` and fail on the
    call with nothing before it noticing. Every transport that streams therefore states its
    conformance to this protocol where it is defined.

    `stream` yields the same text `complete` would have returned, in order and in fragments
    of whatever size the vendor sends. Concatenated, the fragments are the whole reply and
    are validated as one — a stream changes when text arrives, never what is checked.

    A transient failure is retried only while nothing has been yielded. Once a fragment has
    been reported, a retry would replay text the reader has already seen, so a failure after
    that point is final and surfaces as `ProviderError` like any other.
    """

    def stream(
        self,
        messages: list[ChatMessage],
        *,
        schema: Mapping[str, object],
        task: ReasoningTask,
        think: ThinkLevel,
        temperature: float | None,
    ) -> Iterator[str]: ...


@dataclass(frozen=True)
class ToolCall:
    """One tool a model asked for, as it asked for it.

    The arguments are carried as they arrived rather than validated here. Whether they make
    sense is the investigator's question, and it answers it in text the model reads — a
    transport that refused a malformed call would turn a model's bad guess into a failed
    stage.
    """

    name: str
    arguments: Mapping[str, object]


@dataclass(frozen=True)
class ToolExchange:
    """One turn of an investigation: what the model said, and what it wants looked up.

    An empty `calls` is the terminating answer and the only one — the model saying it has
    seen enough. There is no separate "done" signal, because a model that has to remember to
    send one will eventually forget, and a turn with neither text nor calls would then hang
    the loop rather than end it.
    """

    #: Assistant prose, often empty. A model with tools to call frequently calls them
    #: without saying anything first, and that is not a defect worth prompting away.
    text: str
    calls: tuple[ToolCall, ...]
    #: Whatever the transport that produced this turn needs handed back when the turn is
    #: replayed, in whatever shape that vendor's SDK holds it. Written and read only there:
    #: nothing above the transport boundary may look inside it, compare it, or store it, and
    #: the loop that carries it from here onto the replayed turn is a courier rather than a
    #: reader. `None` is the ordinary value — a vendor with nothing to hand back, a fake, a
    #: transport written before any of this existed — and every path stays correct for it.
    vendor_state: object | None = None


@dataclass(frozen=True)
class AssistantToolTurn:
    """The model's own turn, replayed to it, with the calls it made attached.

    Replayed rather than summarised: a vendor that receives tool results without the calls
    they answer has no way to pair them, and pairing is positional — result *n* answers call
    *n* of the turn before it.
    """

    text: str
    calls: tuple[ToolCall, ...]
    #: The `ToolExchange.vendor_state` this turn was built from, carried back down to the
    #: transport that wrote it. Gemini's 3-series is the reason it exists: it attaches a
    #: thought signature to a function call and expects that signature returned with the
    #: history, and a turn rebuilt from `text` and `calls` alone is a turn with the signature
    #: stripped off. Provider-neutral dataclasses are the wrong place to hold a vendor's
    #: private token, so this holds it without describing it — opaque here, meaningful only
    #: where it came from, and never persisted with the review.
    vendor_state: object | None = None


@dataclass(frozen=True)
class ToolResultTurn:
    """What one tool answered, on its way back to the model.

    `call_name` rather than a call id, because the pairing is by position and the name is
    there for the vendors whose wire format asks for one. Two calls of the same tool in one
    turn are therefore distinguished by their order and by nothing else, which is exactly
    how they were sent.
    """

    call_name: str
    content: str


#: One turn of an investigation, in either direction. A closed union rather than a widened
#: `ChatMessage`, because a tool result is not a role and a call is not text: encoding them
#: as prose would leave every transport parsing its own history back out of strings.
InvestigationMessage = ChatMessage | AssistantToolTurn | ToolResultTurn


@runtime_checkable
class ToolCallingChatTransport(Protocol):
    """A transport that can also let a model call tools before it answers.

    Separate from `ChatTransport` and checked with `isinstance`, exactly as streaming is: a
    vendor either has a function-calling API or does not, and a transport without one omits
    the method while every stage goes on working — asking from pinned evidence alone, which
    is what every stage did before this existed. Putting `complete_with_tools` on
    `ChatTransport` would instead make every transport claim the capability and raise when
    it was used.

    That check is by name only. `runtime_checkable` compares which methods exist and nothing
    about their signatures, and a transport is held as a `ChatTransport`, which says nothing
    about tools — so a drifted `complete_with_tools` would pass `isinstance` and fail on the
    call. Every transport that can do this therefore states its conformance to this protocol
    where it is defined.

    No response schema on these requests, deliberately. An investigation is unconstrained
    text plus tool calls; the strict-schema call that composes the questions is unchanged
    and happens afterwards, so nothing about what a stage may *return* is loosened by this.

    `require_call` asks the vendor to constrain the reply to a tool call, where the API has
    such a mode (Gemini spells it function-calling mode ANY). The loop sets it on the first
    turn only: a prompt alone proved too weak an instruction for a small model, which spent
    its permission not to look exactly as written — and a stage that looked at nothing
    cannot tell the asking stage what was checked. Every later turn is the model's own
    judgement, because a forced call on the last turn would be a loop that cannot end.
    """

    def complete_with_tools(
        self,
        messages: list[InvestigationMessage],
        *,
        tools: Sequence[ToolSpec],
        require_call: bool,
        task: ReasoningTask,
        think: ThinkLevel,
        temperature: float | None,
    ) -> ToolExchange: ...


def accumulate_reply(chunks: Iterable[str], preview: ProsePreview) -> str:
    """Join a streamed reply, reporting each new fragment of the previewed field.

    The decoded prefix only ever grows, so the difference in length is the fragment that
    just arrived. Emitting the difference rather than the whole prefix each time keeps this
    usable by a caller that appends — a wire protocol, a text node — without asking it to
    diff two strings.
    """

    content = ""
    reported = ""
    for chunk in chunks:
        content += chunk
        prose = prose_prefix(preview.field, content)
        if len(prose) > len(reported):
            preview.emit(prose[len(reported) :])
            reported = prose
    return content
