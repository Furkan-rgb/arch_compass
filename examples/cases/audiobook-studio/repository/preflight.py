"""Check that everything a run needs is present, before any of it is paid for."""

from __future__ import annotations

import importlib

# What the speech backend needs in order to start.
REQUIRED_PACKAGES = ("torch", "qwen_tts", "soundfile", "numpy")


def check_environment() -> list[str]:
    """Return the names of anything missing, so a run fails early and cheaply."""

    missing: list[str] = []
    for package in REQUIRED_PACKAGES:
        try:
            importlib.import_module(package)
        except ImportError:
            missing.append(package)
    return missing


def check_checkpoint(path: str) -> bool:
    """A Qwen checkpoint has to be on disk before narration can begin."""

    return bool(path)
