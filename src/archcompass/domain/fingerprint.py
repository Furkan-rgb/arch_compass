"""The structural identity of a boundary, independent of any single run.

A review numbers its boundaries BR-001, BR-002, … in detection order, and a candidate's
``candidate_id`` is a random UUID minted at detection time. Neither survives a re-run,
so neither can anchor anything that has to outlive one — a cached verdict, a baseline
entry, a standing decision. The fingerprint can: it is derived from what the boundary
*is* — which detector recognised it and which named things participate in it — so the
same structural situation produces the same fingerprint on every run that observes it.

What is deliberately left out:

- File paths and line numbers, on their own. They churn under ordinary editing. A
  participant's qualified name does embed its module, so moving a participant to a new
  module changes the fingerprint — that is the accepted V1 position (a moved boundary is
  a re-judged boundary; see docs/plans/company-readiness.md §2), chosen over fuzzy
  matching and its failure modes.
- Measurements. Metrics move with almost every edit; a fingerprint that includes them
  would never survive long enough to be worth storing.
- Anything a model wrote. Roles, summaries and rationales are prose; identity is not.
"""

from __future__ import annotations

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
