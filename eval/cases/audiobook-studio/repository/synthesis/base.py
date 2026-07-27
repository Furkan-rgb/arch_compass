"""The speech boundary: what a narration backend must be able to do."""

from __future__ import annotations

from typing import Protocol, runtime_checkable


class SynthesisError(RuntimeError):
    """A backend could not produce audio."""


@runtime_checkable
class Voice(Protocol):
    """An opaque handle a backend hands back and callers pass straight back in.

    Never inspected: for one backend it wraps a precomputed clone prompt, for another it
    might be a speaker embedding or a remote identifier.
    """


@runtime_checkable
class SynthesisProvider(Protocol):
    """Implemented by the current backend and by whichever one is contracted next."""

    def describe(self) -> str:
        """The backend's display name, answerable without loading a model."""
        ...

    def check_available(self) -> None:
        """Raise :class:`SynthesisError` when packages or hardware are missing."""
        ...

    def load_voice(self, spec: str) -> Voice:
        """Prepare the narrator *spec* names and return its handle."""
        ...

    def narrate(self, text: str, voice: Voice) -> bytes:
        """Render one passage as audio."""
        ...

    def close(self) -> None:
        """Release whatever is resident."""
        ...
