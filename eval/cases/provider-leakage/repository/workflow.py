from preflight import validate_voice
from provider import VoiceProvider


def narrate(provider: VoiceProvider, text: str, voice: str) -> bytes:
    validate_voice(voice)
    return provider.synthesize(text, voice)

