from provider import QwenProvider, qwen_voices
from workflow import narrate


def run() -> bytes:
    voices = qwen_voices()
    return narrate(QwenProvider(), "hello", voices[0])

