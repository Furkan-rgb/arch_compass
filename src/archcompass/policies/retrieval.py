"""Choosing which policies a candidate is judged against.

`retrieval_query` is the text a candidate and its case are embedded as — the one place that
decides what retrieval is actually asked. `DensePolicyRetriever` is the shipped strategy:
mandatory and applicable policies by scope, plus a dense top-K, merged deterministically.

The result type and the contract it satisfies are in `ports.py`, so a strategy can be
replaced without anything above it noticing.
"""

from __future__ import annotations

from dataclasses import dataclass
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

#: The K the evaluation gate selected, recorded here rather than chosen by hand.
#: `archcompass retrieval evaluate` tries 8, 12, 16 and 20 and reports the smallest that
#: passes; this is that number. It fell from 20 to 16 when retrieval became two queries.
DENSE_RETRIEVER_RELEASE_TOP_K = 16

#: The damping constant of reciprocal rank fusion, at the value the method is published
#: with. It decides how much the very top of one ranking may dominate the other: at 60, a
#: first place is worth 1/61 and a tenth 1/70, so a policy both queries like beats one that
#: only one of them ranks first. Not tuned — two weightings were measured against the whole
#: gate and equal weighting won, so there was nothing to tune it against.
_FUSION_DAMPING = 60

#: What the fusion is, in the provenance. Changing either the rule or the damping changes
#: which policies a review was judged against, so it changes this too.
FUSION_STRATEGY = "rrf-equal-1"


def corpus_fingerprint(corpus: tuple[Policy, ...]) -> str:
    ordered = sorted(corpus, key=lambda policy: policy.id)
    material = "\0".join(f"{item.id}:{item.content_hash}" for item in ordered)
    return sha256(material.encode()).hexdigest()


def structural_query(candidate: Candidate) -> str:
    """What was found, with nothing a person said about it.

    One of the two queries retrieval asks. It exists because a candidate and its case are
    two different topics and a dense query is one point: put a person's answers about
    payment providers and team ownership into the same string as "a constant stated in two
    modules", and the vector lands between them rather than on either.

    Measured on two duplicated-constant candidates whose repository had answered about PCI
    scope and a payment vendor: `explicit-source-of-truth` — the policy the second of those
    candidates most obviously bears on — ranked 23rd and 27th with the case in the query,
    and 5th and 5th with it removed. Shaping did not recover it. Capping the case text,
    dropping the question stems and repeating the structural half two and three times all
    left it outside the top fifteen, because a single embedding has no notion of a
    secondary section.
    """

    participants = ", ".join(item.qualified_name for item in candidate.participants)
    measurements = "; ".join(
        f"{item.name}: {item.display}" for item in candidate.measurements
    )
    return "\n".join(
        (
            f"Pattern: {candidate.pattern}",
            f"Candidate: {candidate.summary}",
            f"Participants: {participants}",
            f"Measurements: {measurements or 'none'}",
            f"Detection limits: {candidate.limitations or 'none stated'}",
        )
    )


def retrieval_query(candidate: Candidate, case: ArchitectureCase) -> str:
    """The structural query with what a person has answered, which is the other one.

    Not a replacement for `structural_query` and not a superset that makes it redundant:
    the two are ranked separately and fused, so this one is free to be about the case
    without having to also be dominated by the candidate.
    """

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


@dataclass(frozen=True, slots=True)
class _FusedMatch:
    """One policy's place after fusion, in the shape the loop below already reads.

    `score` is the fused rank score, not a cosine. It orders the selection and is not
    recorded: what a reader needs to reproduce the choice is the rule and the K, both of
    which are in the provenance by name.
    """

    policy_id: str
    score: float


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
        """Release identity: the fusion rule, and the mechanically selected limit.

        Both belong in it because both decide which policies a review was judged against.
        `2-` rather than `1-` because retrieval became two queries — a stored review from
        before that was produced by a different function and should not read as though it
        were not.
        """

        return f"2-{FUSION_STRATEGY}-k{self._top_k}"

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
        # Two queries, fused by rank. The measured reason is in `structural_query`; the
        # reason it is *rank* fusion rather than score fusion is that the two queries are
        # different topics, so their cosines are not on one scale — 0.57 against the
        # structural query and 0.57 against the case query do not mean the same thing, and
        # adding them pretends they do. A rank says only "this one before that one", which
        # is true within each list and comparable across them.
        #
        # Both lists are the whole corpus rather than a truncated pool, so there is no depth
        # to choose and the fusion sees every policy either query has an opinion about.
        structural = structural_query(candidate)
        query = retrieval_query(candidate, case)
        fused: dict[str, float] = {}
        for ordered in (
            self._index.search(structural, limit=len(corpus)),
            self._index.search(query, limit=len(corpus)),
        ):
            # Equal weight, which is the whole rule. A structural preference of 2:1 and 3:1
            # were both measured against the complete gate and neither beat this at the K
            # the gate selects — so there is no weight here to explain or to drift.
            for rank, match in enumerate(
                sorted(ordered, key=lambda item: (-item.score, item.policy_id)), 1
            ):
                fused[match.policy_id] = fused.get(match.policy_id, 0.0) + 1.0 / (
                    _FUSION_DAMPING + rank
                )
        dense = [
            _FusedMatch(policy_id=policy_id, score=score)
            for policy_id, score in sorted(
                fused.items(), key=lambda item: (-item[1], item[0])
            )[: self._top_k]
        ]

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
                # What somebody would need to reproduce this selection, and nothing else.
                # Not the per-policy scores: they are an intermediate of a rule the version
                # already names, and provenance that grows with the corpus stops being read.
                metadata=(
                    ("top_k", str(self._top_k)),
                    ("fusion", FUSION_STRATEGY),
                    ("index_identity", self._index.identity),
                    ("dimensions", str(self._index.dimensions)),
                ),
            ),
        )
