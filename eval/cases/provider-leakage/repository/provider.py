from typing import Protocol

BUILT_IN_VOICES = ["serena", "ryan"]


class VoiceProvider(Protocol):
    def synthesize(self, text: str, voice: str) -> bytes: ...


class QwenProvider(VoiceProvider):
    def synthesize(self, text: str, voice: str) -> bytes:
        return f"{voice}:{text}".encode()


def qwen_voices() -> list[str]:
    return list(BUILT_IN_VOICES)

