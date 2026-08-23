"""Choosing which policies a candidate is judged against.

`retrieval_query` is the text a candidate and its case are embedded as — the one place that
decides what retrieval is actually asked. `DensePolicyRetriever` is the shipped strategy:
mandatory and applicable policies by scope, plus a dense top-K, merged deterministically.
`RejudgeAllCandidates` is the selector a clarification round uses.

The result type and the contract it satisfies are in `ports.py`, so a strategy can be
replaced without anything above it noticing.
"""

from __future__ import annotations

from hashlib import sha256

from archcompass.domain import (
    AnswerStatus,
    ArchitectureCase,
    Candidate,
    CandidateId,
    Policy,
    PolicyScope,
    PolicyStrength,
    RetrievalProvenance,
)
from archcompass.policies.ports import DensePolicyIndex
from archcompass.ports.policy_retrieval import PolicySelection, RetrievedPolicySet

DENSE_RETRIEVER_RELEASE_TOP_K = 20


def corpus_fingerprint(corpus: tuple[Policy, ...]) -> str:
    ordered = sorted(corpus, key=lambda policy: policy.id)
    material = "\0".join(f"{item.id}:{item.content_hash}" for item in ordered)
    return sha256(material.encode()).hexdigest()


def retrieval_query(candidate: Candidate, case: ArchitectureCase) -> str:
    participants = ", ".join(item.qualified_name for item in candidate.participants)
    measurements = "; ".join(
        f"{item.name}: {item.display}" for item in candidate.measurements
    )
    # The case contributes what a person has answered, and nothing else — there is no
    # hand-authored intent to embed any more. An unanswered case says so rather than
    # contributing an empty line, because "none" is a fact about this repository and a
    # blank is a fact about the query builder.
    answered = "; ".join(
        f"{item.question.text} {item.value}"
        for item in case.answers
        if item.status is AnswerStatus.ANSWERED and item.value
    )
    return "\n".join(
        (
            f"Pattern: {candidate.pattern}",
            f"Candidate: {candidate.summary}",
            f"Participants: {participants}",
            f"Measurements: {measurements or 'none'}",
            f"Detection limits: {candidate.limitations or 'none stated'}",
            f"Answered about this architecture: {answered or 'nothing yet'}",
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
        if revised_case.id != previous_case.id:
            raise ValueError("rejudgement requires the same case")
        # Answers, not the revision number: one review keeps one revision however many
        # rounds it asks, so what says a round happened is that the case records answers
        # the round before it did not. They are appended in order, which makes the earlier
        # answers a prefix of the later ones and the check exact.
        earlier = previous_case.answers
        if revised_case.answers[: len(earlier)] != earlier:
            raise ValueError("rejudgement requires the answers already recorded")
        if len(revised_case.answers) == len(earlier):
            raise ValueError("rejudgement requires answers the previous round did not record")
        return candidates
