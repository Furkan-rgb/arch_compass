"""The bounded lookups a stage may make into the repository before it speaks.

This is the one boundary in the codebase where the model chooses what to look at, and it
exists because of a failure that has no other cure: `elicit_questions` sees pinned excerpts
and nothing else, so it asks the reader questions the code already answers — how a symbol is
used, whether two constants are really one fact, whether a configuration value is read
anywhere. Those are questions for the repository, and the elicitation contract says so in as
many words while giving the stage no way to ask it.

The §12.0 split it lives under is deliberate and narrow. Verdict evidence stays
application-chosen: the detector picks the spans, the application reads them, and nothing a
model asks for reaches a judgement. What is allowed here is *investigation* — finding out,
before composing a question, whether the question is worth putting to a person — and it is
allowed only because every lookup is recorded. A finding nobody can trace back to a call is
the unverifiable evidence 12.0 refuses; a transcript of exactly what was asked and exactly
what came back is not.

Stage-agnostic on purpose, though only one stage uses it today. Nothing in these three types
names elicitation, because the conversation stages have the same problem — a reader asking
"where else is this used?" is asking about the repository — and a second toolbox written for
them would be a second set of bounds to get wrong.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class ToolSpec:
    """One tool as a model is offered it: what it is called, what it does, what it takes.

    `parameters` is JSON Schema for the arguments object, and it is carried as plain data
    rather than as a pydantic model for the same reason a response schema is: a transport
    hands it to a vendor that wants JSON Schema, and a shape assembled above the transport
    boundary must not need translating on the way down.
    """

    name: str
    description: str
    parameters: Mapping[str, object]


@dataclass(frozen=True)
class RecordedLookup:
    """One call and its answer, kept whether or not the answer was any use.

    The failures matter most. A stage that asked four times and was refused four times
    composed its questions from nothing, and without the refused calls the record would show
    an investigation that never happened as an investigation that found nothing to say.
    """

    tool: str
    arguments: Mapping[str, object]
    result: str


class SourceInvestigator(Protocol):
    """A repository, as a small set of read-only questions a stage may put to it."""

    @property
    def tools(self) -> Sequence[ToolSpec]:
        """Everything this investigator can be asked, in the order a model is shown them."""
        ...

    def call(self, name: str, arguments: Mapping[str, object]) -> str:
        """Run one lookup and return what it found, as text the model reads.

        **This never raises.** An unknown tool, an argument of the wrong type, a path that
        escapes the repository, a file that is not there — each comes back as a sentence
        saying so. That is not leniency: the alternative is a review that fails because a
        model guessed at a filename, and a stage that had to ask without investigating is a
        far better outcome than a run that produced nothing at all.

        Every call is appended to `transcript` before this returns, including the ones that
        answered nothing.
        """
        ...

    @property
    def transcript(self) -> Sequence[RecordedLookup]:
        """Every call made through this investigator, in the order they were made."""
        ...

    def conclude(self, closing: str, abandoned: str) -> None:
        """Close the record: what the stage made of its lookups, and why the looking ended.

        Called once, by the loop that drove the investigation, on every way out of it. The
        two halves have different authors and neither can be recovered from the transcript:
        `closing` is the model's own prose about which of those findings mattered, and
        `abandoned` is the loop's account of why it stopped short — a failed turn, a size
        ceiling reached. Either may be empty, and both being empty is the ordinary end of an
        investigation that simply had nothing left to check.

        Here rather than returned to the caller because the transcript is here. A record
        assembled from a return value and a property read separately is one a later exit
        path can leave half-written, and the half that would go missing is the reason the
        looking ended.
        """
        ...

    @property
    def closing(self) -> str:
        """What the stage said it made of its findings, or "" until it has said anything."""
        ...

    @property
    def abandoned(self) -> str:
        """Why the looking stopped short, or "" where it ran to its own end."""
        ...
