"""Strategy-neutral verdict reuse around one ArchitectureJudge capability call."""

from __future__ import annotations

from collections.abc import Callable
from hashlib import sha256
from typing import Protocol

from archcompass.domain import (
    ArchitectureCase,
    Candidate,
    Finding,
    RecordedInvestigation,
    Review,
)
from archcompass.ports.capabilities import (
    ArchitectureJudge,
    ReviewedSubject,
    ReviewRecorder,
)
from archcompass.ports.policy_retrieval import RetrievedPolicySet


class FindingCache(Protocol):
    """Reuse of a verdict, and the record of which review first made it durable.

    `get` and `put` both return the finding carrying the key they were called with, on
    `Finding.cache_key`, and `record_sources` is entitled to find its rows by nothing else.
    That is the whole contract: an implementation that stores a judgement under a key it
    does not hand back has broken the join, and the shape of that break is a review whose
    provenance quietly stops being recorded rather than an error anybody sees.
    """

    def get(self, key: str) -> Finding | None: ...

    def put(self, key: str, finding: Finding) -> Finding: ...

    def record_sources(self, review: Review) -> None: ...


class CachingReviewRecorder:
    """Record the review, then make it the provenance source for fresh cache entries."""

    def __init__(self, reviews: ReviewRecorder, cache: FindingCache) -> None:
        self._reviews = reviews
        self._cache = cache

    def record(self, review: Review) -> Review:
        recorded = self._reviews.record(review)
        self._cache.record_sources(recorded)
        return recorded


class JudgementInForce(Protocol):
    """What is about to judge, as the key needs to read it.

    Structural rather than imported: this module is strategy-neutral — it wraps whatever
    `ArchitectureJudge` it was handed — and importing the concrete record out of
    `reasoning/adapters/selected.py` to name two strings would tie the cache to one
    selection mechanism. `SelectedLangChainJudge.in_force` satisfies it, and pyright checks
    that at the one call site in `bootstrap`.

    Both identities come off one record for a reason. They used to be two callables, read
    one after the other, so a workspace that changed its model between the two reads could
    key a finding under one model's name and the other's prompt.
    """

    @property
    def model_identity(self) -> str: ...

    @property
    def prompt_identity(self) -> str: ...


class CachingArchitectureJudge:
    def __init__(
        self,
        judge: ArchitectureJudge,
        cache: FindingCache,
        *,
        in_force: Callable[[], JudgementInForce],
    ) -> None:
        self._judge = judge
        self._cache = cache
        self._in_force = in_force

    def judge(
        self,
        candidate: Candidate,
        case: ArchitectureCase,
        policies: RetrievedPolicySet,
        investigation: RecordedInvestigation | None = None,
        *,
        subject: ReviewedSubject | None = None,
    ) -> Finding:
        """A verdict, reused where reusing one is honest.

        Only a judgement that looked at nothing is stored. That one depends on its candidate,
        its case and the policies it was sent, all of which are in the key — so serving it
        again is serving the same answer to the same question.

        A judgement that used a tool depends on what the tool said, on which files it chose
        to read, and possibly on a policy it went and found for itself. None of that exists
        when the key is built, and a cache holding only the `Finding` would hand back a
        verdict whose supporting record this review never had: the manifest would be missing
        the lookups the verdict rests on, and `retrieval_identity` would name a widened
        provenance nothing composed. Reconstructing that is a design of its own and it is not
        this one, so those are recomputed. They are also the minority — measured on two
        providers, a fifth of judgements used no tool at all.
        """

        key = self.key(candidate, case, policies, investigation)
        cached = self._cache.get(key)
        if cached is not None:
            return cached
        finding = self._judge.judge(
            candidate, case, policies, investigation, subject=subject
        )
        if subject is not None and subject.lookups:
            return finding
        return self._cache.put(key, finding)

    def key(
        self,
        candidate: Candidate,
        case: ArchitectureCase,
        policies: RetrievedPolicySet,
        investigation: RecordedInvestigation | None = None,
    ) -> str:
        # This tuple is the only enumeration of what a judgement depends on that anything
        # acts on, and it must stay that way. `persistence/findings.py` used to hold a second
        # one, assembled out of the stamps a finding carries; it could not see the case, and
        # thirteen pairs of rows in one workspace were two different judgements filed under
        # one name because of it. That module now carries the argument in full. What matters
        # here is the consequence: a term added below is carried into the cache's identity
        # without a second edit anywhere, because there is no second edit to make.
        #
        # The case is in it because the case is in the prompt. A candidate judged against
        # "this is a monolith we are keeping" is asked a different question from the same
        # candidate judged against "we are extracting the payments domain", and `ChangeCause`
        # already says so at review scale — `analysis/delta.py` invalidates every verdict when
        # the case moves. It has to say the same thing at row scale, and the measured cost of
        # it not doing so was three of those thirteen pairs holding different verdicts.
        #
        # The investigation is in the key even though nothing passes one today. The second
        # pass that produced one is gone — `workflow/graph.py` says why, and both the deep
        # judge and the deterministic stand-in now `del` the argument — so every row in the
        # workspace hashes `""` here. It stays because `LangChainArchitectureJudge` still
        # renders an investigation into its prompt for the one caller that could hand it one,
        # and a key that dropped the term would serve a verdict reached before anything was
        # looked up to a question asked after it. `identity` rather than the record: a content
        # hash of every lookup, its arguments and its answer.
        #
        # The last two terms are the judge's own answers to what it is and what it sends —
        # `bootstrap` hands `SelectedLangChainJudge.in_force` here and to the revision
        # calculator, the same method to both, and neither derives either value itself. The
        # prompt used to be a constant chosen beside this one that read `judge:v3` while the
        # judge in force stamped `judge:deep-v2`, and the danger in that is not the one it
        # looks like: the key was consistent with itself, so nothing was ever missed. What it
        # was is a stale hit waiting for the next prompt revision. Bumping the deep judge from
        # `deep-v2` to `deep-v3` would have moved the stamp on every finding and left this key
        # byte-identical, and the first review after the bump would have been served verdicts
        # reached under the prompt that had just been replaced.
        #
        # Correcting it moved every key, so rows written before it can never be hit again.
        # That was the right outcome rather than a cost to mitigate: each of them was filed
        # under a prompt that was not the prompt that produced it. Nothing is deleted and
        # nothing serves a wrong answer — the cache is simply cold once, and refills.
        #
        # One `in_force()` for both, rather than a call each: the two are read together or a
        # selection that moved between the two reads keys a row under one model's name and
        # another model's prompt — a pair no selection ever had, so the row it writes is
        # reachable by nothing, and every candidate judged while somebody was switching models
        # is re-judged for ever after.
        #
        # That was an argument and nothing more until this was guarded. Reverting this line to
        # a call each left every unit test in the tree passing, because every stub the suite
        # hands this class answers the same thing twice, and no behavioural test in it could
        # tell one reading from two. Two guards hold it now: `test_reasoning_adapters.py` asks
        # for a key against a selection that moves between calls and refuses the two mixtures,
        # and `test_no_function_reads_the_model_selection_more_than_once` in
        # `test_boundaries.py` asks it of every function in `src/` — which is the form that
        # also covers the six other readers `bootstrap` hands `in_force` to, and the seventh
        # nobody has written yet.
        #
        # The terms stay in this order and this shape because every key already written hashes
        # them that way.
        in_force = self._in_force()
        material = repr(
            (
                candidate,
                case,
                policies.provenance.identity,
                investigation.identity if investigation else "",
                in_force.model_identity,
                in_force.prompt_identity,
            )
        )
        return sha256(material.encode()).hexdigest()
