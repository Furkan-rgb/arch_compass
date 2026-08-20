"""Registry that keeps the rest of the application backend-agnostic."""

from __future__ import annotations

from collections.abc import Callable

from .base import SynthesisProvider
from .qwen import QwenSynthesis

SynthesisFactory = Callable[..., SynthesisProvider]
_BACKENDS: dict[str, SynthesisFactory] = {}


def register(name: str, factory: SynthesisFactory) -> None:
    _BACKENDS[name.casefold()] = factory


def build(name: str, **options: object) -> SynthesisProvider:
    return _BACKENDS[name.casefold()](**options)


def names() -> tuple[str, ...]:
    return tuple(sorted(_BACKENDS))


register("qwen", QwenSynthesis)
