"""Registry for preparation backends."""

from __future__ import annotations

from collections.abc import Callable

from .base import NarrationPreparer
from .ollama import OllamaPreparer

PreparerFactory = Callable[..., NarrationPreparer]
_BACKENDS: dict[str, PreparerFactory] = {}


def register(name: str, factory: PreparerFactory) -> None:
    _BACKENDS[name.casefold()] = factory


def build(name: str, **options: object) -> NarrationPreparer:
    return _BACKENDS[name.casefold()](**options)


register("ollama", OllamaPreparer)
