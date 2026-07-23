from provider import BUILT_IN_VOICES as PROVIDER_BUILT_IN_VOICES

BUILT_IN_VOICES = [*PROVIDER_BUILT_IN_VOICES]


def voice_options() -> list[str]:
    return [voice.title() for voice in BUILT_IN_VOICES]

