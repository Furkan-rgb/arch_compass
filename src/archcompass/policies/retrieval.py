"""Stable policy-retrieval result and the minimum production strategy."""

from __future__ import annotations

from hashlib import sha256

from archcompass.domain import (
    ArchitectureCase,
    Candidate,
    CandidateId,
    Policy,
    PolicyScope,
    PolicyStrength,
    RetrievalProvenance,
)
from archcompass.ports.dense_policy_index import DensePolicyIndex
from archcompass.ports.policy_retrieval import PolicySelection, RetrievedPolicySet

DENSE_RETRIEVER_RELEASE_TOP_K = 20


def corpus_fingerprint(corpus: tuple[Policy, ...]) -> str:
    ordered = sorted(corpus, key=lambda policy: policy.id)
    material = "\0".join(f"{item.id}:{item.content_hash}" for item in ordered)
    return sha256(material.encode()).hexdigest()


def retrieval_query(candidate: Candidate, case: ArchitectureCase) -> str:
    participants = ", ".join(item.qualified_name for item in candidate.participants)
    measurements = "; ".join(f"{key}: {value}" for key, value in candidate.measurements)
    constraints = "; ".join(item.text for item in case.constraints)
    return "\n".join(
        (
            f"Pattern: {candidate.pattern}",
            f"Candidate: {candidate.summary}",
            f"Participants: {participants}",
            f"Measurements: {measurements or 'none'}",
            f"Detection limits: {candidate.limitations or 'none stated'}",
            f"Architecture goal: {case.goal or 'not stated'}",
            f"Constraints: {constraints or 'none stated'}",
        )
    )


class DensePolicyRetriever:
    """Mandatory/applicable scoped policies plus dense top-K, deterministically merged."""

    implementation = "dense-scoped"

    def __init__(self, index: DensePolicyIndex, *, top_k: int) -> None:
        if top_k not in {8, 12, 16, 20}:
            raise ValueError("top_k must be one of the evaluated values: 8, 12, 16, 20")
        self._index = index
        self._top_k = top_k

    @property
    def version(self) -> str:
        """Release identity includes the mechanically selected retrieval limit."""

        return f"1-k{self._top_k}"

    def retrieve(
        self,
        candidate: Candidate,
        case: ArchitectureCase,
        corpus: tuple[Policy, ...],
    ) -> RetrievedPolicySet:
        self._index.synchronize(corpus)
        by_id = {policy.id: policy for policy in corpus}
        context = case.policy_context
        mandatory = sorted(
            (
                policy
                for policy in corpus
                if policy.applies_in(
                    user=context.user,
                    organisation=context.organisation,
                    repository=context.repository,
                )
                and (
                    policy.scope is not PolicyScope.GENERAL
                    or policy.strength is PolicyStrength.REQUIRED
                )
            ),
            key=lambda policy: policy.id,
        )
        query = retrieval_query(candidate, case)
        dense = sorted(
            self._index.search(query, limit=self._top_k),
            key=lambda match: (-match.score, match.policy_id),
        )

        selections: list[PolicySelection] = []
        seen: set[str] = set()
        for policy in mandatory:
            seen.add(policy.id)
            selections.append(
                PolicySelection(
                    policy,
                    (
                        ("selection_reason", "mandatory_or_scoped"),
                        ("rank", str(len(selections) + 1)),
                    ),
                )
            )
        for match in dense:
            policy = by_id.get(match.policy_id)
            if policy is None or policy.id in seen:
                continue
            if not policy.applies_in(
                user=context.user,
                organisation=context.organisation,
                repository=context.repository,
            ):
                continue
            seen.add(policy.id)
            selections.append(
                PolicySelection(
                    policy,
                    (
                        ("selection_reason", "dense"),
                        ("rank", str(len(selections) + 1)),
                        ("score", repr(match.score)),
                    ),
                )
            )

        return RetrievedPolicySet(
            candidate_id=str(candidate.id),
            selections=tuple(selections),
            provenance=RetrievalProvenance(
                candidate_id=CandidateId(str(candidate.id)),
                retriever=self.implementation,
                version=self.version,
                corpus_fingerprint=corpus_fingerprint(corpus),
                selected_policy_ids=tuple(item.policy.id for item in selections),
                model_identity=self._index.embedding_identity,
                query_fingerprint=sha256(query.encode()).hexdigest(),
                metadata=(
                    ("top_k", str(self._top_k)),
                    ("index_identity", self._index.identity),
                    ("dimensions", str(self._index.dimensions)),
                ),
            ),
        )


class RejudgeAllCandidates:
    """Initial correctness strategy, replaceable without changing the graph."""

    def select(
        self,
        candidates: tuple[Candidate, ...],
        previous_case: ArchitectureCase,
        revised_case: ArchitectureCase,
    ) -> tuple[Candidate, ...]:
        if revised_case.id != previous_case.id or revised_case.revision <= previous_case.revision:
            raise ValueError("rejudgement requires a later revision of the same case")
        return candidates
