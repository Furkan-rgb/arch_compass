from provider import BUILT_IN_VOICES as PROVIDER_BUILT_IN_VOICES

BUILT_IN_VOICES = [*PROVIDER_BUILT_IN_VOICES]


def validate_voice(voice: str) -> None:
    if voice not in BUILT_IN_VOICES:
        raise ValueError("Unknown Qwen voice")

