"""Deciding which voice a chapter is actually narrated with."""

from __future__ import annotations

from typing import Protocol

#: The voices narration will use as asked. `ethan` was added to the picker and to the
#: pre-flight check when the account was upgraded, and never reached this copy, so a book
#: started in Ethan is narrated in Serena without anything reporting a problem.
BUILT_IN_VOICES = ["serena", "ryan", "chelsie"]

#: What a book is narrated in when the requested voice is not one we know.
FALLBACK_VOICE = "serena"


class VoiceResolver(Protocol):
    """The voice narration uses, given the one the listener asked for."""

    def resolve(self, requested: str) -> str: ...


class QwenVoiceResolver(VoiceResolver):
    """Resolves against the Qwen voices narration was written for."""

    def resolve(self, requested: str) -> str:
        return requested if requested in BUILT_IN_VOICES else FALLBACK_VOICE
