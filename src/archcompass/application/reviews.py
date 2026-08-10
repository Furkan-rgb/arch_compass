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

The arithmetic that decides all of that lives next door, in `revision_partition`: this
module orchestrates a run, that one answers "which boundaries does this revision owe a
judgement, and why".

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

Because the partition is settled before the first model call, the run can also refuse
itself on it: `review()` counts the partition, and a first pass over a branch nothing has
moved on raises `NothingToReviewError` before anything is written, so a revision that would
change nothing is reported rather than recorded. `allow_unchanged` is the one exemption,
for a caller whose result *is* the delta.
"""

from __future__ import annotations

from collections.abc import Callable, Generator, Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from functools import partial
from pathlib import Path
from time import monotonic

from archcompass.application.investigation import (
    RepositoryInvestigator,
    recorded_investigation,
)
from archcompass.application.policies import PolicyService
from archcompass.application.review_rendering import render_report
from archcompass.application.review_source import ReviewSourceService
from archcompass.application.revision_partition import (
    RevisionPartition,
    inputs_identities,
    partition_revision,
)
from archcompass.application.usage_evidence import UsageEvidenceService
from archcompass.domain.atlas import Atlas, FindingCandidate
from archcompass.domain.case import ArchitectureCase, CaseRevision
from archcompass.domain.delta import (
    BoundaryLineEvent,
    BoundaryLineEventType,
    BoundaryState,
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
    JudgedBoundary,
    RecordedInvestigation,
    ReviewedBoundary,
    ReviewOverview,
    ReviewStatus,
    empty_review_overview,
    first_pass_overview,
    reviewed_boundaries,
)
from archcompass.domain.verdict_cache import CachedVerdict
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


class ReviewService:
    """Runs one review, start to finish, and is the only thing that writes its record.

    `review()` is the whole flow in one method: read the case, load the atlas, place every
    candidate, refuse the run if nothing moved, open the record, judge, and conclude or ask.
    Everything below it is a step of that sequence.
    """

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
        on_judging: Callable[[int, int], None] | None = None,
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
        the first model call, with every candidate the sweep found. `on_judging` is called
        with a position and the total at the moment that candidate is handed to the model —
        so it does not fire for a boundary whose verdict was carried or looked up, which
        never went anywhere and was never in flight. `on_verdict` is called as each verdict
        lands, with the position and the total. Exactly one of `on_eliciting` and
        `on_summarising` then fires, naming which last call this pass makes.

        The two per-boundary callbacks report two different things and only one of them is
        ordered. Verdicts land in the detected order whatever order they were produced in;
        announcements come from the worker threads as the handovers happen, so they arrive
        out of order and interleaved with verdicts on a provider that answers several at
        once. That is the truth being reported rather than a wrinkle to smooth over: a
        caller that assumed one boundary at a time would draw a run slower than the one it
        is watching. The only order guaranteed between them is the one that means anything —
        a boundary is announced before its verdict is reported.

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
        contents, keys = inputs_identities(
            running,
            candidates=candidates,
            revision=revision,
            policies=policies,
            repository_root=repository_root,
            source=self._source,
        )
        delta = partition_revision(
            running,
            candidates=candidates,
            contents=contents,
            keys=keys,
            reviews=self._reviews,
            boundary_lines=self._boundary_lines,
        )
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
                on_judging=on_judging,
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
            self._record_failure(running, str(error), started)
            raise
        except Exception:
            # Whatever this was, it is not something to quote back. The row still has to
            # stop saying "running", because a caller that crashed cannot come back to
            # correct it.
            self._record_failure(
                running, "The review failed unexpectedly, and nothing was judged.", started
            )
            raise

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
        delta: RevisionPartition,
        on_detected: Callable[[Sequence[FindingCandidate]], None] | None,
        on_judging: Callable[[int, int], None] | None,
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
            on_judging=on_judging,
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
        self._record_line_events(running, boundaries=boundaries, delta=delta)
        # Checked once more before the last call, which is the longest single wait in the
        # run: cancelling just as the verdicts land should not still cost a summarisation.
        self._stop_if_cancelled(running.review_id)
        status, overview, investigation = self._conclude_or_ask(
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

    def _record_line_events(
        self,
        running: BoundaryReview,
        *,
        boundaries: list[ReviewedBoundary],
        delta: RevisionPartition,
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
        on_judging: Callable[[int, int], None] | None,
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

        **One thing is reported out of order, and only because it is out of order.** A
        worker announces its candidate through `on_judging` as it hands it over, which is
        the one fact the ordered stream of verdicts cannot carry: up to `concurrent_requests`
        boundaries are under the model at any moment, and a reader given verdicts alone can
        only ever mark the next one. The announcement is bound to its position here, so the
        worker carries no counter and the callback is the caller's to make thread-safe —
        the streaming queue, which is what receives it, already is.

        Everything else that reports, records or reads the run's own record stays with the
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

        total = len(candidates)

        def announce(position: int) -> Callable[[], None] | None:
            """This position's announcement, or nothing where nobody is listening."""

            if on_judging is None:
                return None
            return partial(on_judging, position, total)

        concurrency = self._reasoner.concurrent_requests
        if concurrency <= 1 or len(candidates) <= 1:
            # Not an executor with one worker. Where nothing may overlap, the run should be
            # the loop it has always been, so there is no pool, no thread and no difference.
            # The announcement is made all the same: one boundary in flight is still the
            # answer to which boundary is in flight, and it is the true answer for Ollama.
            for position, candidate in enumerate(candidates, start=1):
                yield self._verdict_for(
                    candidate,
                    running=running,
                    revision=revision,
                    repository_root=repository_root,
                    policies=policies,
                    key=keys[candidate.candidate_id],
                    announce=announce(position),
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
                    announce=announce(position),
                )
                for position, candidate in enumerate(candidates, start=1)
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
        announce: Callable[[], None] | None = None,
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

        `announce` is called between the two — after the miss is known and before the
        request goes out — which is precisely the moment this boundary starts being in
        flight. A hit never calls it: nothing was handed over, and a run that said otherwise
        would be reporting a model call it did not make. It arrives already bound to this
        candidate's position, so a worker announces itself without holding a counter, and
        whatever is on the other end hears it from this thread.

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
        if announce is not None:
            announce()
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

    def _conclude_or_ask(
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
            investigation = recorded_investigation(
                investigator,
                self._reasoner.prompt_identity(ReasoningTask.INVESTIGATE_USAGE),
            )
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

    def _record_failure(self, running: BoundaryReview, reason: str, started: float) -> None:
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
