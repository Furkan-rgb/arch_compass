"""Neutral contracts crossing the policy-retrieval capability boundary."""

from __future__ import annotations

from dataclasses import dataclass, replace

from archcompass.domain import Policy, RetrievalProvenance
from archcompass.domain._support import freeze_pairs, freeze_sequences


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

    def widened_by(self, found: tuple[Policy, ...]) -> RetrievedPolicySet:
        """The same retrieval, plus what a judgement went and found for itself.

        A judgement may search the corpus when the policies it was sent do not cover the
        concern it has arrived at. Whatever the search returned was genuinely available to
        it, so it belongs in `selected_policy_ids` — which is what the citation check reads,
        and what a reader is shown as "the policies this verdict could have rested on". A
        provenance still claiming only the deterministic top-K would be a record saying a
        cited policy was never sent.

        `identity` hashes `selected_policy_ids`, so widening the set changes the identity on
        its own: a finding whose judgement searched cannot carry the same retrieval identity
        as one whose judgement did not. The invariant is enforced by the hash rather than by
        anyone remembering to enforce it.

        The two halves stay told apart. `retriever` and `version` are left alone because the
        deterministic retriever really did produce the first set, and `metadata` records how
        many of them there were and which ids arrived the other way.
        """

        if not found:
            return self
        return replace(
            self,
            selections=(
                *self.selections,
                *(PolicySelection(policy, (("source", "judge_search"),)) for policy in found),
            ),
            provenance=replace(
                self.provenance,
                selected_policy_ids=(
                    *self.provenance.selected_policy_ids,
                    *(policy.id for policy in found),
                ),
                metadata=(
                    *self.provenance.metadata,
                    ("retrieved_policies", str(len(self.selections))),
                    ("judge_searched", ",".join(policy.id for policy in found)),
                ),
            ),
        )
