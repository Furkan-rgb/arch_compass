"""Detect boundaries in a repository and judge what has changed since the last revision.

The MVP advisory path, end to end and deliberately short: the application decides what to
look at, the model decides what it means, and nothing the model writes is used as a key
(master plan 12.0).

Detection is deterministic and complete over the atlas, so what reaches the model is not a
sample or a ranking. Judgement runs once per candidate against the whole policy corpus,
which fits comfortably in one request, so there is no retrieval step to get wrong and no
threshold quietly deciding which policy the advisor was allowed to consider.

**Judgement, though, runs only over the delta.** Detection stays complete; what a revision
*judges* is what moved since the branch's previous revision. A boundary whose inputs identity
is unchanged carries — verdict, standing and silence together — with no model call, and it
may never be asked about again. A boundary that is new, or whose source, case, corpus, model
or prompt moved, is judged, and only such a boundary may earn an elicitation question. That
is what makes re-asking a settled question structurally impossible rather than merely cached
away, and it is why a run over an untouched repository concludes in one pass having called
nothing.

The rest of the partition is about the line a boundary keeps while the code moves under it.
A shape that disappeared and one that appeared with the same pattern and half its
participants are declared predecessor and successor, so a rename carries the standing across
with a visible mark rather than orphaning it silently. A shape that disappeared and matched
nothing closes as `addressed` — the loop closing, which is the best news the tool has to
deliver and which it used to throw away by simply not mentioning the boundary again. Nothing
is deleted, so a fingerprint that comes back resurfaces with its standing and its discussion
intact. All three are recorded as events on the branch's ledger, and the partition itself is
stored on the review: it is a fact about two immutable revisions, so recomputing it later
could only produce the same answer or a wrong one.

Because the partition is settled before the first model call, it can also be asked *instead*
of a run: `preflight` takes the same steps and stops there, so a revision that would move
nothing is reported rather than recorded. See `application.preflight` for why a branch's
history is better off without it.
"""

from __future__ import annotations

from collections.abc import Callable, Generator, Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from time import monotonic

from archcompass.application.investigation import RepositoryInvestigator
from archcompass.application.policies import PolicyService
from archcompass.application.review_rendering import render_report
from archcompass.application.review_source import ReviewSourceService
from archcompass.application.usage_evidence import UsageEvidenceService
from archcompass.domain.atlas import Atlas, FindingCandidate
from archcompass.domain.case import ArchitectureCase, CaseRevision
from archcompass.domain.delta import (
    AddressedBoundary,
    BoundaryLineEvent,
    BoundaryLineEventType,
    BoundaryShape,
    BoundaryState,
    JudgedBecause,
    RevisionDelta,
    match_successions,
)
from archcompass.domain.errors import (
    ArchCompassError,
    AtlasNotFoundError,
    NothingToReviewError,
    ReviewCancelledError,
)
from archcompass.domain.finding_detectors import detect_finding_candidates
from archcompass.domain.fingerprint import boundary_fingerprint
from archcompass.domain.policy import PolicyDocument
from archcompass.domain.review import (
    BoundaryReview,
    BoundaryReviewReport,
    CandidateVerdict,
    InvestigationLookup,
    JudgedBoundary,
    RecordedInvestigation,
    ReviewedBoundary,
    ReviewOverview,
    ReviewStatus,
    empty_review_overview,
    first_pass_overview,
    reviewed_boundaries,
)
from archcompass.domain.verdict_cache import (
    CachedVerdict,
    case_fingerprint,
    policy_corpus_fingerprint,
    verdict_cache_key,
)
from archcompass.ports.atlas import AtlasFreshnessChecker, SourceReader
from archcompass.ports.reasoning import FocusedReasoningProvider, ReasoningTask
from archcompass.ports.repositories import (
    AtlasRepository,
    BoundaryLineRepository,
    BoundaryReviewRepository,
    CaseRepository,
    VerdictCacheRepository,
)

#: What a report says the case was for when the case says nothing. A review may run against
#: a repository alone (master plan §6C.1), and the honest reading of that is not a blank
#: heading but a statement that nothing was asked for yet — which is also what the review's
#: own questions are about to address.
UNSTATED_CASE = (
    "No problem or desired outcome has been stated for this case yet. These boundaries "
    "were judged on the repository alone, so what the review could not weigh is recorded "
    "as the questions it asks below."
)


def _stated_case(case: ArchitectureCase) -> str:
    """The case's own words, or a sentence saying it has none."""

    stated = "\n\n".join(
        part for part in (case.problem_statement.strip(), case.desired_outcome.strip()) if part
    )
    return stated or UNSTATED_CASE


@dataclass(frozen=True)
class JudgedCandidate:
    """One detected pattern and what the model made of it."""

    candidate: FindingCandidate
    verdict: CandidateVerdict
    #: The earlier review this verdict was carried forward from, where it was not reached
    #: here. Carried on the judgement itself rather than kept in a map beside it, because
    #: everyone who is told about a verdict as it lands — the run, the record, the stream —
    #: needs to be able to say whether it was reached or looked up, and a watcher told only
    #: that a boundary was judged would be watching the run claim work it did not do.
    reused_from: str | None = None


def _shape(fingerprint: str, candidate: FindingCandidate) -> BoundaryShape:
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
class _Delta:
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
        pre-flight promising a quiet run that then reported four judged boundaries.
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


class ReviewService:
    def __init__(
        self,
        *,
        cases: CaseRepository,
        atlases: AtlasRepository,
        reviews: BoundaryReviewRepository,
        freshness: AtlasFreshnessChecker,
        policies: PolicyService,
        reasoner: FocusedReasoningProvider,
        source: ReviewSourceService,
        usage: UsageEvidenceService,
        source_reader: SourceReader,
        verdict_cache: VerdictCacheRepository,
        boundary_lines: BoundaryLineRepository,
    ) -> None:
        self._cases = cases
        self._atlases = atlases
        self._reviews = reviews
        self._freshness = freshness
        self._policies = policies
        self._reasoner = reasoner
        self._source = source
        self._usage = usage
        # The reader itself, as well as the service built on it. `ReviewSourceService` reads
        # spans a detector chose; the elicitation stage's toolbox reads spans the model asks
        # for, and both go through this one object for the reason there is only one of it:
        # it is the single path that cannot leave the analysed repository.
        self._source_reader = source_reader
        self._verdict_cache = verdict_cache
        self._boundary_lines = boundary_lines

    def review(
        self,
        case_id: str,
        *,
        repository_root: Path,
        elicited_from: str | None = None,
        allow_unchanged: bool = False,
        on_started: Callable[[BoundaryReview], None] | None = None,
        on_detected: Callable[[Sequence[FindingCandidate]], None] | None = None,
        on_verdict: Callable[[JudgedCandidate, int, int], None] | None = None,
        on_eliciting: Callable[[], None] | None = None,
        on_summarising: Callable[[], None] | None = None,
    ) -> BoundaryReview:
        """Judge every candidate in the repository against this case.

        Which of the two passes this is, is decided by `elicited_from` and by nothing else.
        Absent, this is a first pass: it judges, then asks for what would settle the verdicts
        that could not settle themselves, and stops there if it has anything to ask. Present,
        it names the first pass whose questions produced this case revision, and this run
        judges and concludes without asking again — which is what makes the loop terminate.

        A first pass over a branch nothing has moved on is refused with
        `NothingToReviewError` before anything is written: a revision that would change
        nothing is reported, not recorded, and the refusal happens here so every caller —
        either page, the CLI, the API — gets the same answer from the same arithmetic.
        `allow_unchanged` is the stated exemption for a caller whose result *is* the delta:
        a CI re-run over untouched code needs the carried partition to say nothing new
        blocks, and has nothing to compute that from if the run refuses itself.

        `on_started` is called once the run has a record, which is the first moment it has
        an identity: everything that could refuse the run has passed, and the review can be
        opened and watched from anywhere from here on. `on_detected` is called once, before
        the first model call, with every candidate the sweep found. `on_verdict` is called
        as each verdict lands, with the position and the total. Exactly one of `on_eliciting`
        and `on_summarising` then fires, naming which last call this pass makes.

        A review is one model call per candidate and takes minutes, so a caller that reports
        nothing until the last one has finished is the difference between a tool that looks
        stuck and one that does not — and detection is where the length of the sequence
        becomes known, which is what makes the wait countable rather than unexplained.
        """

        started = monotonic()
        revision = self._cases.get(case_id)
        atlas = self._load_atlas(repository_root)
        self._freshness.ensure_fresh(atlas)
        running = BoundaryReview(
            status=ReviewStatus.RUNNING,
            case_id=revision.case_id,
            case_revision=revision.revision,
            atlas_version_id=atlas.version.version_id,
            # Copied from the atlas rather than resolved again. The atlas is what was judged,
            # and asking git a second time here could file the run under a different branch
            # than the one its evidence was built on — someone switching branch mid-run is
            # unusual, and a run that lied about which line of work it was about would be
            # worse than unusual. An atlas indexed before lineages existed carries neither,
            # and the review says so by carrying neither too.
            repo_id=atlas.version.repo_id,
            branch_id=atlas.version.branch_id,
            elicited_from=elicited_from,
            reasoning_model=self._reasoner.model_identity,
            prompt_identity=self._reasoner.prompt_identity(
                ReasoningTask.JUDGE_FINDING_CANDIDATE
            ),
        )
        # Everything deterministic and local happens before the run has a record: the
        # policies are read, the candidates detected, the code under them hashed, and the
        # partition computed. This is the same arithmetic the run itself goes on to use —
        # one computation, so a refusal and a run can never disagree about whether anything
        # moved.
        #
        # Ordered once, here, and passed to every judgement unchanged. The response binds
        # to policies by position, so the order is part of the contract rather than a
        # presentation detail: re-sorting between the request and the result would
        # re-attribute every answer.
        policies = sorted(
            self._policies.catalog(repository_root=repository_root),
            key=lambda policy: policy.id,
        )
        # Augmented before anything is fingerprinted, so a boundary's identity includes how
        # its code is used: a verdict cached against usage has to die when usage changes.
        candidates = self._usage.augment(
            detect_finding_candidates(atlas), atlas, repository_root
        )
        contents, keys = self._inputs_identities(
            running,
            candidates=candidates,
            revision=revision,
            policies=policies,
            repository_root=repository_root,
        )
        delta = self._partition(running, candidates=candidates, contents=contents, keys=keys)
        # A revision that would change nothing is reported, not recorded — refused here,
        # before anything is written, so every caller gets the same answer whichever button
        # or client asked. Only a first pass refuses: a second pass whose reader answered
        # nothing is quiet by the same arithmetic, and it must still run, because
        # concluding without asking again is what terminates the loop. A first revision is
        # never quiet whatever the counts say — a repository with no boundaries at all
        # would otherwise be told nothing had changed since a revision that does not exist.
        counted = delta.counted()
        if (
            not allow_unchanged
            and elicited_from is None
            and not counted.first_revision
            and counted.quiet
        ):
            assert counted.previous_review_id is not None
            raise NothingToReviewError(
                "Nothing has changed since this branch's latest revision — the code, the "
                "case and the policies are the same, so a new revision would repeat it. "
                "Nothing was recorded.",
                current_against=counted.previous_review_id,
            )
        # The run becomes a record here, before the first model call and after everything
        # that could refuse it. Earlier would store runs that never began; later is the
        # minutes-long gap this exists to close — a review nobody can find while it is being
        # produced looks the same as one that was never started.
        self._reviews.begin(running)
        if on_started is not None:
            on_started(running)
        try:
            return self._judge(
                running,
                revision=revision,
                repository_root=repository_root,
                started=started,
                policies=policies,
                candidates=candidates,
                contents=contents,
                keys=keys,
                delta=delta,
                on_detected=on_detected,
                on_verdict=on_verdict,
                on_eliciting=on_eliciting,
                on_summarising=on_summarising,
            )
        except ReviewCancelledError:
            # Nothing is written back. The record already says cancelled — that write is
            # what stopped the run — and a failure recorded over it would replace a choice
            # with a breakage. It also leaves the row safe to delete straight away.
            raise
        except ArchCompassError as error:
            # The run's own message: it was raised by ArchCompass and is written for a
            # person to read, which is the same rule the web layer applies before putting
            # one in a response.
            self._fail(running, str(error), started)
            raise
        except Exception:
            # Whatever this was, it is not something to quote back. The row still has to
            # stop saying "running", because a caller that crashed cannot come back to
            # correct it.
            self._fail(running, "The review failed unexpectedly, and nothing was judged.", started)
            raise

    def _inputs_identities(
        self,
        running: BoundaryReview,
        *,
        candidates: Sequence[FindingCandidate],
        revision: CaseRevision,
        policies: list[PolicyDocument],
        repository_root: Path,
    ) -> tuple[dict[str, str], dict[str, str]]:
        """Each candidate's content fingerprint and its inputs identity, by `candidate_id`.

        The corpus and the case are computed once rather than per candidate: they are the same
        question for every boundary in the run, and together they are most of what makes a
        stored verdict still apply.

        The content fingerprints are read before the first model call, because this is what
        decides whether there is one to make — the code under a boundary is half of its inputs
        identity. Which is also why the pre-flight computes them through this same method: an
        answer about whether anything moved is only worth having if the key it compares is the
        key the run would have gone on to use.
        """

        corpus = policy_corpus_fingerprint(policies)
        stated_case = case_fingerprint(revision.snapshot)
        contents = self._source.content_fingerprints(candidates, root=repository_root)
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

    def _judge(
        self,
        running: BoundaryReview,
        *,
        revision: CaseRevision,
        repository_root: Path,
        started: float,
        policies: list[PolicyDocument],
        candidates: Sequence[FindingCandidate],
        contents: dict[str, str],
        keys: dict[str, str],
        delta: _Delta,
        on_detected: Callable[[Sequence[FindingCandidate]], None] | None,
        on_verdict: Callable[[JudgedCandidate, int, int], None] | None,
        on_eliciting: Callable[[], None] | None,
        on_summarising: Callable[[], None] | None,
    ) -> BoundaryReview:
        # Detection, hashing and the partition happened in `review`, before the run had a
        # record — they are what decides whether there is a run to record. What happens
        # here is everything that costs or writes.
        #
        # Now the run has a length, which is the one number a reader watching it needs.
        self._reviews.record_progress(running.review_id, detected=len(candidates))
        if on_detected is not None:
            on_detected(candidates)
        judged: list[JudgedCandidate] = []
        reused_from: dict[str, str] = {}
        material = 0
        carried = 0
        # Reached in the detected order whether or not they were *produced* in it: see
        # `_judgements`. Closed however this loop ends, which is what stops a cancelled or
        # failed run leaving a pool of workers behind it.
        verdicts = self._judgements(
            running=running,
            revision=revision,
            repository_root=repository_root,
            policies=policies,
            candidates=candidates,
            keys=keys,
        )
        try:
            for position, candidate in enumerate(candidates, start=1):
                # Before waiting on this position rather than after it, so a run cancelled
                # while judgements are in flight stops at the next boundary instead of
                # waiting out the ones already started. Only the main thread ever asks.
                self._stop_if_cancelled(running.review_id)
                item = next(verdicts)
                if item.reused_from is not None:
                    reused_from[candidate.candidate_id] = item.reused_from
                    carried += 1
                judged.append(item)
                material += 1 if item.verdict.material else 0
                # Reported in the same events and the same order as a fresh verdict, and
                # said to be what it is. A cached run is not a quieter run — every boundary
                # still lands, one at a time, in the detected order, and that stays true
                # when several are being judged at once: judging may overlap, reporting
                # never does — but it is a faster one, and a stream that only counted them
                # would have the run claim minutes of judgement it spent looking things up.
                # The count travels with the record too, so a second tab or a reload, which
                # has the columns and not the stream, can say the same thing.
                self._reviews.record_progress(
                    running.review_id,
                    reviewed=position,
                    material=material,
                    carried=carried,
                )
                if on_verdict is not None:
                    on_verdict(item, position, len(candidates))
        finally:
            verdicts.close()
        boundaries = reviewed_boundaries(
            [
                JudgedBoundary(
                    candidate=item.candidate,
                    verdict=item.verdict,
                    content_fingerprint=contents[item.candidate.candidate_id],
                    inputs_identity=keys[item.candidate.candidate_id],
                    verdict_reused_from=reused_from.get(item.candidate.candidate_id),
                    delta_state=delta.state.get(item.candidate.candidate_id),
                    judged_because=delta.judged_because.get(item.candidate.candidate_id),
                    succeeds=delta.succeeds.get(item.candidate.candidate_id),
                    resurfaced_from_review=delta.resurfaced_from.get(
                        item.candidate.candidate_id
                    ),
                )
                for item in judged
            ]
        )
        # Written before the last model call rather than after it, so a run cancelled while
        # summarising still leaves the branch's ledger saying what this revision observed.
        # The events are about the code, not about whether anyone read the conclusion.
        self._record_the_line(running, boundaries=boundaries, delta=delta)
        # Checked once more before the last call, which is the longest single wait in the
        # run: cancelling just as the verdicts land should not still cost a summarisation.
        self._stop_if_cancelled(running.review_id)
        status, overview, investigation = self._read_the_set(
            revision=revision,
            repository_root=repository_root,
            boundaries=boundaries,
            # `None` belongs with the judged, not with the carried: a run that could not
            # partition itself — no branch lineage, so no previous revision to compare with —
            # has every boundary on the table, exactly as every run did before the delta.
            judged=[
                item
                for item in boundaries
                if item.delta_state is not BoundaryState.CARRIED
            ],
            first_pass=running.elicited_from is None,
            on_eliciting=on_eliciting,
            on_summarising=on_summarising,
        )
        report = BoundaryReviewReport(
            delta=delta.counted(),
            case_title=revision.snapshot.title,
            problem_and_desired_outcome=_stated_case(revision.snapshot),
            reviewed=boundaries,
            overview=overview,
            policies_presented=[policy.id for policy in policies],
            # Read here, at the one moment the repository is known to be exactly what was
            # judged: freshness was checked before the first model call and nothing has been
            # re-indexed since. Pinning it costs about 4,000 characters and buys a review
            # that can still show its evidence after someone starts acting on it — the
            # alternative expired on the first unrelated edit (ADR 0013).
            excerpts=self._source.for_boundaries(boundaries, root=repository_root),
        )
        review = running.model_copy(
            update={
                "status": status,
                # Kept whichever way the pass ended, and `None` where nothing looked. It is
                # a fact about the run rather than about the verdicts, so it sits on the
                # review beside them rather than inside the report.
                "investigation": investigation,
                "report": report,
                "markdown_report": render_report(
                    report,
                    awaiting_answers=status is ReviewStatus.AWAITING_ANSWERS,
                ),
                "duration_seconds": round(monotonic() - started, 3),
            }
        )
        self._reviews.complete(review)
        return review

    def _partition(
        self,
        running: BoundaryReview,
        *,
        candidates: Sequence[FindingCandidate],
        contents: dict[str, str],
        keys: dict[str, str],
    ) -> _Delta:
        """Place every candidate against the branch's previous revision, before judging.

        The whole of the delta rule lives in this method, and it runs before the first model
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
            return _Delta(None, {}, {}, {}, {}, [])
        previous = self._reviews.previous_revision_for_branch(
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
            _shape(item.fingerprint or "", item.candidate)
            for item in (report.reviewed if report is not None else [])
            if item.fingerprint is not None and item.fingerprint not in current_fingerprints
        ]
        appeared = [
            _shape(now[candidate.candidate_id], candidate)
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

        resurfaced = self._resurfaced(
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
        return _Delta(
            previous_review_id=None if previous is None else previous.review_id,
            state=state,
            judged_because=because,
            succeeds=succeeds,
            resurfaced_from=by_candidate,
            addressed=addressed,
        )

    def _resurfaced(self, branch_id: str, *, fingerprints: list[str]) -> dict[str, str]:
        """Which of these fingerprints were closed as addressed on this branch, and by whom.

        A line's state is its latest event, so `addressed` on top means the boundary went and
        has now come back. Standings were never deleted — they key on `(branch_id,
        fingerprint)` and nothing removes them — which is what makes an automatic closure safe
        to take: resurrection restores nothing, because nothing was taken away.
        """

        latest = self._boundary_lines.latest_for(branch_id, fingerprints)
        return {
            fingerprint: event.review_id
            for fingerprint, event in latest.items()
            if event.event is BoundaryLineEventType.ADDRESSED
        }

    def _record_the_line(
        self,
        running: BoundaryReview,
        *,
        boundaries: list[ReviewedBoundary],
        delta: _Delta,
    ) -> None:
        """Append what this revision observed about the lines to the branch's ledger.

        Three kinds of event and one write. A succession is recorded on the *predecessor*,
        naming what it became, because that is the fingerprint a standing decision and a
        discussion thread are filed under and therefore the one a later reader will look up.
        A closure and a resurrection are recorded on the fingerprint itself.

        Nothing is recorded on a run with no branch lineage: the ledger keys on the branch,
        and filing an event under a guess would attribute a closure to a line of work that
        never had one.
        """

        branch_id = running.branch_id
        if branch_id is None:
            return
        events = [
            BoundaryLineEvent(
                branch_id=branch_id,
                boundary_fingerprint=item.succeeds or "",
                event=BoundaryLineEventType.SUCCEEDED,
                review_id=running.review_id,
                successor_fingerprint=item.fingerprint,
            )
            for item in boundaries
            if item.succeeds is not None and item.fingerprint is not None
        ]
        events.extend(
            BoundaryLineEvent(
                branch_id=branch_id,
                boundary_fingerprint=item.fingerprint,
                event=BoundaryLineEventType.ADDRESSED,
                review_id=running.review_id,
            )
            for item in delta.addressed
        )
        events.extend(
            BoundaryLineEvent(
                branch_id=branch_id,
                boundary_fingerprint=item.fingerprint,
                event=BoundaryLineEventType.RESURFACED,
                review_id=running.review_id,
            )
            for item in boundaries
            if item.resurfaced_from_review is not None and item.fingerprint is not None
        )
        self._boundary_lines.append_all(events)

    def _judgements(
        self,
        *,
        running: BoundaryReview,
        revision: CaseRevision,
        repository_root: Path,
        policies: list[PolicyDocument],
        candidates: Sequence[FindingCandidate],
        keys: dict[str, str],
    ) -> Generator[JudgedCandidate]:
        """Every candidate's verdict, always in the detected order, sometimes overlapping.

        A judgement is one HTTP request and a long wait, and a review is one per boundary,
        so a run against a provider that answers several at once spent most of its minutes
        waiting in sequence for no reason. How many may be in flight is the provider's own
        answer and nothing this service decides — a hosted API has a fleet, a local Ollama
        has one GPU and would only queue.

        **Produced in parallel, yielded in submission order.** The caller records progress
        and calls back per position, and those are what a reader watching the run sees; a
        boundary that finished third arriving second would have the stream disagree with
        the report. So this waits on position one, then position two, rather than taking
        whatever completes first — the run is as fast as its slowest judgement plus the
        tail, and every event is still in the order the sweep detected them.

        Everything that reports, records or reads the run's own record stays with the
        caller. A worker does exactly `_verdict_for`, whose only shared state is a SQLite
        repository that opens a connection per call (WAL, with a busy timeout) and a
        reasoner that builds its transport once under a lock. Nothing here holds a cursor,
        a session or a counter across calls.

        Closing this — which the caller does however its loop ends — shuts the pool down
        without waiting. Judgements not yet started never run; one already in flight
        finishes into the verdict cache, which is the same policy `_verdict_for` documents:
        a cancelled run that already paid for a call should not make the next run pay again.

        A worker's exception surfaces from the position that raised, exactly where the
        sequential loop would have raised it, and closing cancels the rest.
        """

        concurrency = self._reasoner.concurrent_requests
        if concurrency <= 1 or len(candidates) <= 1:
            # Not an executor with one worker. Where nothing may overlap, the run should be
            # the loop it has always been, so there is no pool, no thread and no difference.
            for candidate in candidates:
                yield self._verdict_for(
                    candidate,
                    running=running,
                    revision=revision,
                    repository_root=repository_root,
                    policies=policies,
                    key=keys[candidate.candidate_id],
                )
            return
        executor = ThreadPoolExecutor(
            max_workers=concurrency,
            thread_name_prefix=f"judge-{running.review_id}",
        )
        try:
            pending = [
                executor.submit(
                    self._verdict_for,
                    candidate,
                    running=running,
                    revision=revision,
                    repository_root=repository_root,
                    policies=policies,
                    key=keys[candidate.candidate_id],
                )
                for candidate in candidates
            ]
            for future in pending:
                yield future.result()
        finally:
            executor.shutdown(wait=False, cancel_futures=True)

    def _verdict_for(
        self,
        candidate: FindingCandidate,
        *,
        running: BoundaryReview,
        revision: CaseRevision,
        repository_root: Path,
        policies: list[PolicyDocument],
        key: str,
    ) -> JudgedCandidate:
        """This candidate's verdict, saying whether it was reached here or carried forward.

        The lookup is unconditional. Every component of the key is a value this run already
        holds before it calls anything — the candidate's structure, the code under it, the
        corpus it is about to present, what the case says and at which revision, and the model
        and prompt identities the record was opened with — so there is no half-determined key
        and no case where the cache has to be stepped around. Notably absent: the repository
        and branch ids, which may be `None` on an atlas indexed before lineages existed. They
        are not in the key, so that absence changes nothing here.

        The key is computed by the caller and passed in, because it is the boundary's inputs
        identity and the run needs it twice: once to look a verdict up, and once to store on
        the reviewed boundary so the *next* revision can decide in one comparison whether this
        boundary carried.

        A miss writes through under *this* review's id, so the next run can say where the
        verdict came from. The write is not conditional on the run finishing: the verdict
        was genuinely reached, and a cancelled or failed run that already paid for a model
        call should not make the next run pay for it again.

        **This is the whole of what a worker thread runs** (see `_judgements`), and it is
        safe to run several of at once. The cache's `get` and `put` each open their own
        SQLite connection — WAL, with a busy timeout — and hold nothing between calls, and
        `put` is an `INSERT OR IGNORE` on the key, so two runs racing to store the same
        verdict store one of them and neither fails. Everything else read here is a value
        the run already holds. Nothing here reports, records progress or reads the review's
        own record; the consuming loop does all three, from the thread that owns the run.
        """

        cached = self._verdict_cache.get(key)
        if cached is not None:
            # Re-pointed at this run's candidate. A verdict names the candidate it was about
            # by `candidate_id`, and that id is minted fresh at every detection — carrying
            # the stored one forward would leave this review's boundary citing a candidate
            # that only ever existed in an earlier run.
            carried = cached.verdict.model_copy(
                update={"candidate_id": candidate.candidate_id}
            )
            return JudgedCandidate(
                candidate=candidate,
                verdict=carried,
                reused_from=cached.review_id,
            )
        verdict = self._reasoner.judge_finding_candidate(
            revision.snapshot,
            candidate,
            policies,
            # Read here rather than up in `review`, so a run whose verdicts all carry pays
            # for nothing: a cache hit needs no evidence, because nothing is being judged.
            # The repository is known fresh — `review` checked before anything was recorded
            # and nothing has been indexed since — which is the same reason the elicitation
            # toolbox is built without freshness logic of its own.
            self._source.for_candidate(candidate, root=repository_root),
        )
        self._verdict_cache.put(
            CachedVerdict(
                cache_key=key,
                boundary_fingerprint=boundary_fingerprint(candidate),
                verdict=verdict,
                review_id=running.review_id,
            )
        )
        return JudgedCandidate(candidate=candidate, verdict=verdict)

    def _read_the_set(
        self,
        *,
        revision: CaseRevision,
        repository_root: Path,
        boundaries: list[ReviewedBoundary],
        judged: list[ReviewedBoundary],
        first_pass: bool,
        on_eliciting: Callable[[], None] | None,
        on_summarising: Callable[[], None] | None,
    ) -> tuple[ReviewStatus, ReviewOverview, RecordedInvestigation | None]:
        """The one call that sees every verdict at once, and what it makes the run.

        Which call that is depends on the pass, and the whole two-pass flow turns on this
        branch. A first pass asks; a second concludes. Neither does both — a first pass
        composing a conclusion would be drawing one out of a case that usually says nothing,
        and a second pass able to ask would leave the loop with no way to end.

        A first pass with nothing to ask is a finished review, so the two are not fixed to
        the two passes: where every verdict stood on what the case already said, this falls
        straight through to the summary and the reader never sees a question. That is the
        good outcome and the common one for a case someone actually wrote.

        **Elicitation sees only what this revision judged.** The summary sees everything,
        because a conclusion is about the repository and a boundary that carried is still part
        of it; a question is about what moved, and a question about a boundary nothing touched
        is one the reader has already been asked or has already had answered. That is the
        structural version of a guarantee the cache could only approximate: this run does not
        *have* the settled boundaries to compose a question from, rather than composing one
        and finding it familiar. It also means a revision whose judged subset is empty asks
        nothing at all and concludes in one pass, which is what an untouched repository
        deserves.

        Neither call is made when there are no verdicts. A sweep that found nothing has
        nothing to ask about and nothing to synthesise, and either call would be asking a
        model to invent the content of its own input.

        Only the asking half is given a toolbox. It is built here, per elicitation, because
        this is the point where the repository is known to be exactly the one the verdicts
        were reached in — freshness was checked before the first model call and nothing has
        been indexed since — which is why the investigator needs no freshness logic of its
        own. The summary is given none, deliberately: it says what verdicts already reached
        amount to, and a lookup there would be new evidence entering a conclusion after every
        judgement that could have weighed it had finished.

        What the toolbox was asked comes back with the status and the overview, because the
        caller is what writes the review and this belongs on it. It travels out of both
        outcomes: a pass that looked and then had nothing left to ask is the record most
        worth keeping, since it is the one where nothing else on the document shows that the
        silence was checked rather than assumed.
        """

        if not boundaries:
            return ReviewStatus.SUCCEEDED, empty_review_overview(), None
        investigation: RecordedInvestigation | None = None
        if first_pass and judged:
            if on_eliciting is not None:
                on_eliciting()
            investigator = RepositoryInvestigator(
                root=repository_root, source_reader=self._source_reader
            )
            questions = self._reasoner.elicit_questions(
                revision.snapshot,
                judged,
                investigator,
            )
            investigation = self._recorded(investigator)
            if questions:
                # The run stops here, and the record says so. Nothing further is worth
                # composing: these verdicts are what the case supports so far, and four of
                # five of them moved on the bundled example once the questions were answered
                # (ADR 0010). A conclusion drawn over them would be a conclusion about a case
                # that has not been written yet.
                return (
                    ReviewStatus.AWAITING_ANSWERS,
                    first_pass_overview(boundaries, questions),
                    investigation,
                )
        if on_summarising is not None:
            on_summarising()
        return (
            ReviewStatus.SUCCEEDED,
            self._reasoner.summarise_review(revision.snapshot, boundaries),
            investigation,
        )

    def _recorded(
        self, investigator: RepositoryInvestigator
    ) -> RecordedInvestigation | None:
        """The toolbox's transcript as a stored record, or nothing worth storing.

        Nothing worth storing is the common case and it is `None` rather than an empty
        record: most providers cannot offer tools, so their investigator is handed over and
        never touched, and a document saying "no lookups, no reason" would tell every later
        reader that this repository was checked and had nothing to say. An abandonment with
        no lookups is the opposite — it is exactly the state worth keeping — so it is the
        second thing that makes a record.

        The identity is read here rather than carried through the loop because it is the
        application's fact about the run, not the model's: it says which investigate-usage
        contract this transcript can be compared against.
        """

        if not investigator.transcript and not investigator.abandoned:
            return None
        return RecordedInvestigation(
            lookups=[
                InvestigationLookup(
                    tool=item.tool,
                    arguments=dict(item.arguments),
                    result=item.result,
                )
                for item in investigator.transcript
            ],
            closing=investigator.closing,
            abandoned=investigator.abandoned,
            prompt_identity=self._reasoner.prompt_identity(
                ReasoningTask.INVESTIGATE_USAGE
            ),
        )

    def _stop_if_cancelled(self, review_id: str) -> None:
        """Read the run's own record, between model calls, to see whether to go on.

        The record is the channel. A flag shared with whoever started the run would be
        state living outside the request that owns the work — and the row has to say
        cancelled anyway, for the listing to show it. Cancelling therefore takes effect
        within one model call rather than at once, which is the bound worth stating: on a
        local model that is up to a few minutes.
        """

        if not self._reviews.is_running(review_id):
            raise ReviewCancelledError(f"Boundary review {review_id} was cancelled.")

    def _fail(self, running: BoundaryReview, reason: str, started: float) -> None:
        self._reviews.complete(
            running.model_copy(
                update={
                    "status": ReviewStatus.FAILED,
                    "sanitized_errors": [reason],
                    "duration_seconds": round(monotonic() - started, 3),
                }
            )
        )

    def _load_atlas(self, repository_root: Path) -> Atlas:
        atlas = self._atlases.latest_for_path(repository_root.expanduser().resolve())
        if atlas is None:
            raise AtlasNotFoundError(
                f"No indexed atlas for {repository_root}; "
                f"run `archcompass repo index {repository_root}` first."
            )
        return atlas
