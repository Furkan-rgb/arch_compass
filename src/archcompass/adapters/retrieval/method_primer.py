"""Read the bundled primer on ArchCompass's own method.

An adapter because it reads a packaged resource, and nothing more than that: there is no
parsing, no index and no ranking. The corpus fits whole, so the only question is where the
bytes come from.
"""

from __future__ import annotations

from importlib.resources import files


def load_method_primer() -> str:
    return files("archcompass.knowledge").joinpath("method.md").read_text(encoding="utf-8")
