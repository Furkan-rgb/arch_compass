"""The Pydantic base every feature's validated records are built on.

Top level rather than inside a feature because five of them need it, and because it is
the counterpart to `domain/_support.py`: that one is what a frozen domain dataclass is
made of, this one is what a record crossing a boundary — an analyser's output, a policy
document, a model catalogue — is made of.

The dependency runs one way, and only one way is possible: `domain/` may not import this,
which a boundary test enforces. So the three primitives both halves need — the clock and
the two id mints — are defined there and re-exported here. They used to be written out
twice, once on each side, and the codebase imported them from whichever module the author
happened to be looking at: `utc_now` twelve times from one and five from the other. Two
identical functions is not two implementations, it is one implementation and one place a
reader can be wrong about which they are reading.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict
from pydantic_core import to_jsonable_python

from archcompass.domain._support import new_id, stable_id, utc_now

#: The named depths a provider offers, where it offers a depth rather than a switch.
#:
#: Google's is the vocabulary, because Google is the provider that has one: Gemini 3 takes
#: `thinking_level` and the four words below, and has no way to be told simply "yes". A
#: provider with a switch is still a switch — see `ThinkingMode`.
THINKING_LEVELS = ("minimal", "low", "medium", "high")

ThinkingLevel = Literal["minimal", "low", "medium", "high"]

#: How hard a model is asked to think before it answers, in whichever of the two shapes the
#: chosen provider actually has.
#:
#: `None` asks for nothing and leaves the model to its own default, which on a Gemini 3
#: model means dynamic thinking rather than none. `True` and `False` are the switch Ollama
#: has. A level is the dial Google has. Every adapter owes all of them, in its own spelling
#: — a provider that spells depth as a level rather than a switch reads the ends of this
#: `False` there is the floor rather than off.
ThinkingMode = bool | ThinkingLevel | None


class BoundaryDTO(BaseModel):
    """Base for immutable, strict data-transfer objects at system boundaries."""

    model_config = ConfigDict(extra="forbid", frozen=True)


#: Re-exported, not redefined. Importing them from here goes on working, which is most of
#: the codebase, and there is now one body to read.
__all__ = ["BoundaryDTO", "canonical_json", "new_id", "stable_id", "utc_now"]


def canonical_json(model: BaseModel | dict[str, Any]) -> str:
    import json

    return json.dumps(
        to_jsonable_python(model),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
