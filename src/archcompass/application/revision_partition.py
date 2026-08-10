"""Which boundaries does this revision owe a judgement, and why.

One question, answered before the first model call. Every candidate the sweep found is
placed against the branch's previous revision — carried, judged, or succeeding something
that has gone — and every placement names the input that moved. What disappeared and was
claimed by nothing closes as addressed; what closed and has come back resurfaces. The
arithmetic is here, whole, and `ReviewService` orchestrates around it.

Placing before judging is the point rather than an optimisation. A boundary placed as
`carried` costs no model call and can never earn an elicitation question, which is what
makes re-asking a settled question structurally impossible rather than merely cached away.
It is also what lets a run refuse itself: the counts exist before anything has been written.

The comparison is always against the revision immediately behind this one, never against
the verdict cache. The cache remembers every question ever answered, so a boundary that
changed in revision 8 and changed back in revision 9 would hit on revision 7's row and be
reported as untouched by a revision that did touch it.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from archcompass.application.review_source import ReviewSourceService
from archcompass.domain.atlas import FindingCandidate
from archcompass.domain.case import CaseRevision
from archcompass.domain.delta import (
    AddressedBoundary,
    BoundaryLineEventType,
    BoundaryShape,
    BoundaryState,
    JudgedBecause,
    RevisionDelta,
    match_successions,
)
from archcompass.domain.fingerprint import boundary_fingerprint
from archcompass.domain.policy import PolicyDocument
from archcompass.domain.review import BoundaryReview, ReviewedBoundary
from archcompass.domain.verdict_cache import (
    case_fingerprint,
    policy_corpus_fingerprint,
    verdict_cache_key,
)
from archcompass.ports.repositories import (
    BoundaryLineRepository,
    BoundaryReviewRepository,
)


def _shape_for_matching(fingerprint: str, candidate: FindingCandidate) -> BoundaryShape:
    """A candidate reduced to what succession matching compares."""

    return BoundaryShape(
        fingerprint=fingerprint,
        pattern=candidate.pattern,
        participants=[
            participant.qualified_name for participant in candidate.participants
        ],
    )


def _what_moved(
    seen: ReviewedBoundary,
    previous: BoundaryReview | None,
    content: str,
    running: BoundaryReview,
) -> JudgedBecause:
    """Which input moved under a boundary the previous revision also had.

    Named rather than left as "changed", which is the word that broke the baseline: a reader
    hears it as a statement about their code and it was just as often the model having been
    upgraded. Every answer here is something a person can point at.

    The terms are checked in the order a reader cares about them, and the corpus is reached by
    elimination rather than by comparison. A review records the case, model and prompt it ran
    under and a boundary records its own content, so four of the five are a direct comparison;
    the policy corpus is not stored on a review, and if none of the four moved then the corpus
    is the only remaining term in the identity that could have.
    """

    if seen.content_fingerprint != content:
        return JudgedBecause.CONTENT
    if previous is None:
        return JudgedBecause.NEW
    if (
        previous.case_id != running.case_id
        or previous.case_revision != running.case_revision
    ):
        return JudgedBecause.CASE
    if previous.reasoning_model != running.reasoning_model:
        return JudgedBecause.MODEL
    if previous.prompt_identity != running.prompt_identity:
        return JudgedBecause.PROMPT
    return JudgedBecause.POLICIES


@dataclass(frozen=True)
class RevisionPartition:
    """The partition of one revision against the previous one, before verdicts exist.

    Computed from shapes and inputs alone, which is why it can be computed *before* the first
    model call: what a boundary is, what its code says, and what the previous revision said
    about the same fingerprint are all known at detection time. The verdicts then land on top
    of it, and the elicitation stage is handed exactly the subset this named.
    """

    previous_review_id: str | None
    #: Per `candidate_id`: where this boundary stands, and which input moved if one did.
    state: dict[str, BoundaryState]
    judged_because: dict[str, JudgedBecause]
    #: Per `candidate_id`: the fingerprint this boundary succeeded, where one was matched.
    succeeds: dict[str, str]
    #: Per `candidate_id`: the review that closed this fingerprint, where it has come back.
    resurfaced_from: dict[str, str]
    addressed: list[AddressedBoundary]

    @property
    def first_revision(self) -> bool:
        return self.previous_review_id is None

    def counted(self) -> RevisionDelta:
        """This partition as the number of boundaries in each state.

        Counted from the placement rather than from the verdicts that land on top of it,
        which is what lets the same arithmetic answer two questions: what a finished revision
        records, and what a revision that has not been created would have found. If those two
        were counted separately they could disagree, and the disagreement would show up as a
        run refused as changing nothing that would have gone on to judge four boundaries.
        """

        states = list(self.state.values())
        return RevisionDelta(
            previous_review_id=self.previous_review_id,
            first_revision=self.first_revision,
            carried=states.count(BoundaryState.CARRIED),
            judged=states.count(BoundaryState.JUDGED),
            succeeded=states.count(BoundaryState.SUCCEEDED),
            addressed=len(self.addressed),
            resurfaced=len(self.resurfaced_from),
            addressed_boundaries=self.addressed,
        )


def inputs_identities(
    running: BoundaryReview,
    *,
    candidates: Sequence[FindingCandidate],
    revision: CaseRevision,
    policies: list[PolicyDocument],
    repository_root: Path,
    source: ReviewSourceService,
) -> tuple[dict[str, str], dict[str, str]]:
    """Each candidate's content fingerprint and its inputs identity, by `candidate_id`.

    The corpus and the case are computed once rather than per candidate: they are the same
    question for every boundary in the run, and together they are most of what makes a
    stored verdict still apply.

    The content fingerprints are read before the first model call, because this is what
    decides whether there is one to make — the code under a boundary is half of its inputs
    identity. Which is also why the refusal is decided from these same keys: an answer
    about whether anything moved is only worth having if the key it compares is the key
    the run would have gone on to use.
    """

    corpus = policy_corpus_fingerprint(policies)
    stated_case = case_fingerprint(revision.snapshot)
    contents = source.content_fingerprints(candidates, root=repository_root)
    keys = {
        candidate.candidate_id: verdict_cache_key(
            boundary=boundary_fingerprint(candidate),
            content=contents[candidate.candidate_id],
            policy_corpus=corpus,
            case=stated_case,
            case_revision=revision.revision,
            model_identity=running.reasoning_model,
            prompt_identity=running.prompt_identity,
        )
        for candidate in candidates
    }
    return contents, keys


def partition_revision(
    running: BoundaryReview,
    *,
    candidates: Sequence[FindingCandidate],
    contents: dict[str, str],
    keys: dict[str, str],
    reviews: BoundaryReviewRepository,
    boundary_lines: BoundaryLineRepository,
) -> RevisionPartition:
    """Place every candidate against the branch's previous revision, before judging.

    The whole of the delta rule lives in this function, and it runs before the first model
    call because that is the point: a boundary placed as `carried` costs nothing, and one
    placed as `judged` is the only kind that may earn a question.

    Carrying turns on one equality — this revision's inputs identity for a fingerprint
    against the identity the previous revision recorded for it. Not on a cache hit, which
    is a weaker claim: the cache remembers every question ever answered, so a boundary
    that changed in revision 8 and changed back in revision 9 would hit on revision 7's
    row and be reported as untouched by a revision that did touch it. The comparison is
    against the revision immediately behind this one, and nothing else.

    A run with no branch lineage — an atlas indexed before lineages existed — partitions
    nothing and says so by leaving every state absent. That is honest: without a branch
    there is no previous revision to be the same as or different from, and reporting
    every boundary as `judged` would be a claim that a comparison was made.
    """

    branch_id = running.branch_id
    if branch_id is None:
        return RevisionPartition(None, {}, {}, {}, {}, [])
    previous = reviews.previous_revision_for_branch(
        branch_id, excluding_review_id=running.review_id
    )
    report = None if previous is None else previous.report
    before = (
        {}
        if report is None
        else {
            item.fingerprint: item
            for item in report.reviewed
            if item.fingerprint is not None
        }
    )

    now = {
        candidate.candidate_id: boundary_fingerprint(candidate) for candidate in candidates
    }
    state: dict[str, BoundaryState] = {}
    because: dict[str, JudgedBecause] = {}
    for candidate in candidates:
        fingerprint = now[candidate.candidate_id]
        seen = before.get(fingerprint)
        if seen is None:
            state[candidate.candidate_id] = BoundaryState.JUDGED
            because[candidate.candidate_id] = JudgedBecause.NEW
            continue
        if seen.inputs_identity == keys[candidate.candidate_id]:
            state[candidate.candidate_id] = BoundaryState.CARRIED
            continue
        state[candidate.candidate_id] = BoundaryState.JUDGED
        because[candidate.candidate_id] = _what_moved(
            seen, previous, contents[candidate.candidate_id], running
        )

    # Only shapes that are genuinely absent can be succeeded or addressed. A boundary
    # present in both revisions has not moved anywhere, whatever happened to its code.
    current_fingerprints = set(now.values())
    gone = [
        _shape_for_matching(item.fingerprint or "", item.candidate)
        for item in (report.reviewed if report is not None else [])
        if item.fingerprint is not None and item.fingerprint not in current_fingerprints
    ]
    appeared = [
        _shape_for_matching(now[candidate.candidate_id], candidate)
        for candidate in candidates
        if now[candidate.candidate_id] not in before
    ]
    successions = match_successions(gone=gone, appeared=appeared)
    succeeds: dict[str, str] = {}
    for candidate in candidates:
        predecessor = successions.get(now[candidate.candidate_id])
        if predecessor is None:
            continue
        succeeds[candidate.candidate_id] = predecessor
        state[candidate.candidate_id] = BoundaryState.SUCCEEDED
        because[candidate.candidate_id] = JudgedBecause.SHAPE

    # Everything that disappeared and was not claimed by a successor. Reported rather
    # than confirmed: succession matching has already run, and nothing is deleted, so
    # there is no loss to protect a reader from.
    claimed = set(successions.values())
    addressed = [
        AddressedBoundary(
            fingerprint=item.fingerprint or "",
            pattern=item.candidate.pattern,
            title=item.candidate.summary,
            material=item.material,
            verdict_label=item.verdict_label,
            last_seen_in_review=previous.review_id if previous is not None else "",
            last_reference=item.reference,
        )
        for item in (report.reviewed if report is not None else [])
        if item.fingerprint is not None
        and item.fingerprint not in current_fingerprints
        and item.fingerprint not in claimed
    ]

    resurfaced = _resurfaced(
        boundary_lines,
        branch_id,
        fingerprints=[
            now[candidate.candidate_id]
            for candidate in candidates
            if now[candidate.candidate_id] not in before
        ],
    )
    by_candidate = {
        candidate.candidate_id: resurfaced[now[candidate.candidate_id]]
        for candidate in candidates
        if now[candidate.candidate_id] in resurfaced
    }
    for candidate_id in by_candidate:
        # Named ahead of `new`, which is what it would otherwise read as. A boundary that
        # was addressed and is back is not news of the same kind, and the standing and
        # discussion waiting on its fingerprint are the difference.
        if state.get(candidate_id) is BoundaryState.JUDGED:
            because[candidate_id] = JudgedBecause.RESURFACED
    return RevisionPartition(
        previous_review_id=None if previous is None else previous.review_id,
        state=state,
        judged_because=because,
        succeeds=succeeds,
        resurfaced_from=by_candidate,
        addressed=addressed,
    )


def _resurfaced(
    boundary_lines: BoundaryLineRepository,
    branch_id: str,
    *,
    fingerprints: list[str],
) -> dict[str, str]:
    """Which of these fingerprints were closed as addressed on this branch, and by whom.

    A line's state is its latest event, so `addressed` on top means the boundary went and
    has now come back. Standings were never deleted — they key on `(branch_id,
    fingerprint)` and nothing removes them — which is what makes an automatic closure safe
    to take: resurrection restores nothing, because nothing was taken away.
    """

    latest = boundary_lines.latest_for(branch_id, fingerprints)
    return {
        fingerprint: event.review_id
        for fingerprint, event in latest.items()
        if event.event is BoundaryLineEventType.ADDRESSED
    }
