"""The Pydantic base every feature's validated records are built on.

Top level rather than inside a feature because five of them need it, and because it is
the counterpart to `domain/_support.py`: that one is what a frozen domain dataclass is
made of, this one is what a record crossing a boundary — an analyser's output, a policy
document, a model catalogue — is made of. Neither imports the other, and `domain/` may
not import this.
"""

from __future__ import annotations

from datetime import UTC, datetime
from hashlib import sha256
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict
from pydantic_core import to_jsonable_python

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
#: — see `google_thinking_level` for the one place a switch is read as a dial, and why
#: `False` there is the floor rather than off.
ThinkingMode = bool | ThinkingLevel | None


class BoundaryDTO(BaseModel):
    """Base for immutable, strict data-transfer objects at system boundaries."""

    model_config = ConfigDict(extra="forbid", frozen=True)


def utc_now() -> datetime:
    return datetime.now(UTC)


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex}"


def stable_id(prefix: str, *parts: str, length: int = 24) -> str:
    payload = "\0".join(parts).encode("utf-8")
    return f"{prefix}_{sha256(payload).hexdigest()[:length]}"


def canonical_json(model: BaseModel | dict[str, Any]) -> str:
    import json

    return json.dumps(
        to_jsonable_python(model),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
