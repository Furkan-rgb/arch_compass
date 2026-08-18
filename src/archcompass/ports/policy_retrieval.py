"""Neutral contracts crossing the policy-retrieval capability boundary."""

from __future__ import annotations

from dataclasses import dataclass

from archcompass.domain.core import Policy, RetrievalProvenance
from archcompass.domain.core._support import freeze_pairs, freeze_sequences


@dataclass(frozen=True, slots=True)
class PolicySelection:
    policy: Policy
    provenance: tuple[tuple[str, str], ...] = ()

    def __post_init__(self) -> None:
        freeze_pairs(self, "provenance")


@dataclass(frozen=True, slots=True)
class RetrievedPolicySet:
    candidate_id: str
    selections: tuple[PolicySelection, ...]
    provenance: RetrievalProvenance

    def __post_init__(self) -> None:
        freeze_sequences(self, "selections")

    @property
    def policies(self) -> tuple[Policy, ...]:
        return tuple(selection.policy for selection in self.selections)
