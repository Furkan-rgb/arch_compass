"""The structural identity of a boundary, independent of any single run.

A review numbers its boundaries BR-001, BR-002, … in detection order, and a candidate's
``candidate_id`` is a random UUID minted at detection time. Neither survives a re-run,
so neither can anchor anything that has to outlive one — a cached verdict, a standing
decision, a boundary's line across revisions. The fingerprint can: it is derived from what
the boundary *is* — which detector recognised it and which named things participate in it —
so the same structural situation produces the same fingerprint on every run that observes it.

What is deliberately left out:

- File paths and line numbers, on their own. They churn under ordinary editing. A
  participant's qualified name does embed its module, so moving a participant to a new
  module changes the fingerprint — that is the accepted V1 position (a moved boundary is
  a re-judged boundary; see docs/plans/company-readiness.md §2), chosen over fuzzy
  matching and its failure modes.
- Measurements. Metrics move with almost every edit; a fingerprint that includes them
  would never survive long enough to be worth storing.
- Anything a model wrote. Roles, summaries and rationales are prose; identity is not.

Identity is not the whole of what a verdict rests on, and the second function here is the
other half. The shape says *which* boundary this is; the content fingerprint says whether the
code under it is the code that was judged. Two boundaries with the same shape and different
content are the same question asked about different code, and answering the second from the
first is exactly the stale-verdict gap the delta rule exists to close: rewrite a class body
without renaming anything and the shape does not move at all.

So the shape is identity and the content is an input. Nothing keys on the content
fingerprint except the verdict cache — a standing decision, a discussion thread and the line
through revisions all attach to the shape, because a team's opinion about a boundary is not
undone by somebody editing it.
"""

from __future__ import annotations

from collections.abc import Iterable

from archcompass.domain.atlas import FindingCandidate
from archcompass.domain.base import stable_id


def boundary_fingerprint(candidate: FindingCandidate) -> str:
    """Derive the run-independent identity of a detected boundary.

    Participants are sorted so that detector-internal ordering, which is a presentation
    choice, cannot leak into identity.
    """
    return stable_id(
        "bdry",
        candidate.pattern.value,
        *sorted(participant.qualified_name for participant in candidate.participants),
    )


def content_fingerprint(sources: Iterable[tuple[str, str]]) -> str:
    """Identify the code under one boundary, by what it says rather than where it sits.

    Each pair is one participant's qualified name and the source at its recorded span. Sorted
    by name for the same reason the shape sorts its participants: which order a detector
    happened to list them in is a presentation choice and must not reach identity.

    A participant whose span could not be read contributes an empty text, so an unreadable
    file gives a stable answer rather than a different one each time. That is deliberately
    optimistic in one direction — an unreadable boundary carries rather than being re-judged
    for ever — and the check that matters happens elsewhere: a review runs only against a
    repository that has just been confirmed fresh.
    """

    return stable_id(
        "cont",
        *[f"{name}\n{text}" for name, text in sorted(sources)],
    )
