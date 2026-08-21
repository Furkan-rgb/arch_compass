"""The bounded lookups a review may make into a repository before it speaks.

This is the one boundary in the codebase where the model chooses what to look at, and it
exists because of a failure that has no other cure. A judgement sees pinned excerpts and
nothing else, so when its verdict turns on a fact those excerpts do not carry it emits a
hinge — and a hinge stops the review to ask a person. Many of them are questions for the
repository: how a symbol is used, whether anything implements a port, whether a seam has
tests. The judgement contract already forbids asking a person one of those, while giving
the judgement no way to find out.

The split this lives under is deliberate and narrow. Verdict evidence stays
application-chosen: the detector picks the spans, the application reads them, and nothing a
model asks for is pinned as evidence. What is allowed here is *investigation* — finding out,
before interrupting somebody, whether the interruption is warranted — and it is allowed only
because every lookup is recorded. A finding nobody can trace back to a call is the
unverifiable evidence the charter refuses; a transcript of exactly what was asked and
exactly what came back is not.

Surface-agnostic on purpose. A hinge investigation and a reader asking "where else is this
used?" have the same problem, and a second toolbox written for the second one would have
been a second set of bounds to get wrong. What differs between them is the contract they are
held under and whether their first turn is forced, both of which live where the loop runs;
the bounds and the recording are one thing, here.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Protocol

from archcompass.domain import RepositoryAtlas, RepositoryRef


@dataclass(frozen=True)
class ToolSpec:
    """One tool as a model is offered it: what it is called, what it does, what it takes.

    `parameters` is JSON Schema for the arguments object, and it is carried as plain data
    rather than as a Pydantic model for the same reason a response schema is: a transport
    hands it to a vendor that wants JSON Schema, and a shape assembled above the transport
    boundary must not need translating on the way down.
    """

    name: str
    description: str
    parameters: Mapping[str, object]


@dataclass(frozen=True)
class RecordedLookup:
    """One call and its answer, kept whether or not the answer was any use.

    The failures matter most. A pass that asked four times and was refused four times kept
    its hinge from nothing, and without the refused calls the record would show an
    investigation that never happened as one that found nothing to say.
    """

    tool: str
    arguments: Mapping[str, object]
    result: str


class SourceInvestigator(Protocol):
    """A repository, as a small set of read-only questions a pass may put to it."""

    @property
    def tools(self) -> Sequence[ToolSpec]:
        """Everything this investigator can be asked, in the order a model is shown them."""
        ...

    def call(self, name: str, arguments: Mapping[str, object]) -> str:
        """Run one lookup and return what it found, as text the model reads.

        **This never raises.** An unknown tool, an argument of the wrong type, a node id
        that does not exist, a repository that has moved — each comes back as a sentence
        saying so. That is not leniency: the alternative is a review that fails because a
        model guessed at an identifier, and a hinge that had to be kept is a far better
        outcome than a run that produced nothing at all.

        Every call is appended to `transcript` before this returns, including the ones that
        answered nothing.
        """
        ...

    @property
    def transcript(self) -> Sequence[RecordedLookup]:
        """Every call made through this investigator, in the order they were made."""
        ...

    def conclude(self, closing: str, abandoned: str) -> None:
        """Close the record: what the pass made of its lookups, and why the looking ended.

        Called once, by the loop that drove the investigation, on every way out of it. The
        two halves have different authors and neither can be recovered from the transcript:
        `closing` is the model's own prose about which findings mattered, and `abandoned` is
        the loop's account of why it stopped short — a failed turn, a size ceiling reached.
        Either may be empty, and both being empty is the ordinary end of an investigation
        that simply had nothing left to check.

        Here rather than returned to the caller because the transcript is here. A record
        assembled from a return value and a property read separately is one a later exit
        path can leave half-written, and the half that would go missing is the reason the
        looking ended.
        """
        ...

    @property
    def closing(self) -> str:
        """What the pass said it made of its findings, or "" until it has said anything."""
        ...

    @property
    def abandoned(self) -> str:
        """Why the looking stopped short, or "" where it ran to its own end."""
        ...


@dataclass(frozen=True)
class OfferedInvestigator:
    """A toolbox, or the application's own sentence about why there is none.

    One value rather than two reads, because the two facts are produced together and must
    not be readable apart: a caller that found `investigator is None` and never looked for
    the reason would report an investigation that found nothing, when what happened is that
    nothing could look. That sentence is shown to a reader verbatim, so it names the way
    back — re-index this repository — rather than describing a fault.
    """

    investigator: SourceInvestigator | None = None
    withheld: str = ""


class InvestigatorSource(Protocol):
    """Where a toolbox over one review's own atlas comes from."""

    def for_review(
        self, repository: RepositoryRef, atlas: RepositoryAtlas
    ) -> OfferedInvestigator:
        """A toolbox answering about exactly the atlas this review judged.

        The atlas is passed in rather than looked up. A review analyses a repository into an
        atlas it never persists, so a toolbox that fetched the latest *indexed* atlas would
        answer about a different snapshot than the verdicts were reached against — which is
        the one failure the recording exists to make impossible.
        """
        ...
