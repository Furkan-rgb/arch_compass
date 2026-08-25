"""Which models have been measured against the judgement gate, and how they fared.

A table rather than a branch. Every model reaches the same `ArchitectureJudge` with the same
tools, the same contract and the same schema — the difference between them is how well they
use it, and that belongs where somebody choosing a model can read it rather than in code that
routes around it.

Nothing here restricts what may be selected. A model absent from this table is `unknown`,
which is most of them and is not a refusal: it means nobody has run the gate on it.

The gate is the focused corpus in the repository's own test fixtures plus a complete review,
and what it measures is not tool count. A judgement that settles from the dossier alone is
sound where the dossier settles it. What fails is leaving a premise the repository could have
answered unresolved, asserting a fact the dossier contradicts, returning one verdict for
everything, or output the contract cannot use.
"""

from __future__ import annotations

from archcompass.reasoning.records import Qualification

#: What each measured model did on the gate, keyed by `(provider, model)`.
_MEASURED: dict[tuple[str, str], Qualification] = {
    # Holds its invariants over repeated runs and a complete review. In use.
    ("ollama", "qwen3.8:27b"): "qualified",
    ("openrouter", "google/gemini-3.5-flash-lite"): "qualified",
    # Sound reasoning, valid citations, no unsupported claims — and it did not look anything
    # up once in a complete review, where the two qualified models looked on 4 and 3 of the
    # same six candidates. Verdicts stay defensible, so this is not a failure; it is a model
    # that decides from the dossier where the dossier does not always settle it.
    ("openrouter", "openai/gpt-5.6-luna-pro"): "experimental",
    # One verdict for every candidate across two runs of the gate, no lookups, and reasoning
    # that contradicted the dossier it was given — it reported no test substitution on a
    # candidate whose own measurements listed three.
    ("openrouter", "openai/gpt-oss-120b"): "not_qualified",
}


def qualification(provider: str, model: str) -> Qualification:
    """How this model fared on the gate, or `unknown` where nobody has run it.

    The exact name first, then the name without whatever follows a colon. The two providers
    spell that suffix differently and only one of them means "the same model, another route":
    `openai/gpt-oss-120b:exacto` is a routing variant of a model measured here, while
    `qwen3.8:27b` is a tag naming which weights they are. Trying the whole name first is what
    keeps the second from being read as the first.
    """

    measured = _MEASURED.get((provider, model))
    if measured is not None:
        return measured
    return _MEASURED.get((provider, model.split(":", maxsplit=1)[0]), "unknown")
