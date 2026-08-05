"""Detect boundaries in a repository and judge each against one case.

The MVP advisory path, end to end and deliberately short: the application decides what to
look at, the model decides what it means, and nothing the model writes is used as a key
(master plan 12.0).

Detection is deterministic and complete over the atlas, so what reaches the model is not a
sample or a ranking. Judgement runs once per candidate against the whole policy corpus,
which fits comfortably in one request, so there is no retrieval step to get wrong and no
threshold quietly deciding which policy the advisor was allowed to consider.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from time import monotonic

from archcompass.application.policies import PolicyService
from archcompass.application.review_rendering import render_report
from archcompass.application.review_source import ReviewSourceService
from archcompass.domain.atlas import Atlas, FindingCandidate
from archcompass.domain.case import ArchitectureCase, CaseRevision
from archcompass.domain.errors import (
    ArchCompassError,
    AtlasNotFoundError,
    ReviewCancelledError,
)
from archcompass.domain.finding_detectors import detect_finding_candidates
from archcompass.domain.fingerprint import boundary_fingerprint
from archcompass.domain.policy import PolicyDocument
from archcompass.domain.review import (
    BoundaryReview,
    BoundaryReviewReport,
    CandidateVerdict,
    ReviewedBoundary,
    ReviewOverview,
    ReviewStatus,
    empty_review_overview,
    first_pass_overview,
    reviewed_boundaries,
)
from archcompass.domain.verdict_cache import (
    CachedVerdict,
    policy_corpus_fingerprint,
    verdict_cache_key,
)
from archcompass.ports.atlas import AtlasFreshnessChecker
from archcompass.ports.reasoning import FocusedReasoningProvider, ReasoningTask
from archcompass.ports.repositories import (
    AtlasRepository,
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
        verdict_cache: VerdictCacheRepository,
    ) -> None:
        self._cases = cases
        self._atlases = atlases
        self._reviews = reviews
        self._freshness = freshness
        self._policies = policies
        self._reasoner = reasoner
        self._source = source
        self._verdict_cache = verdict_cache

    def review(
        self,
        case_id: str,
        *,
        repository_root: Path,
        elicited_from: str | None = None,
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
        # The run becomes a record here, before the first model call and after everything
        # that could refuse it. Earlier would store runs that never began; later is the
        # minutes-long gap this exists to close — a review nobody can find while it is being
        # produced looks the same as one that was never started.
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
        self._reviews.begin(running)
        if on_started is not None:
            on_started(running)
        try:
            return self._judge(
                running,
                revision=revision,
                atlas=atlas,
                repository_root=repository_root,
                started=started,
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

    def _judge(
        self,
        running: BoundaryReview,
        *,
        revision: CaseRevision,
        atlas: Atlas,
        repository_root: Path,
        started: float,
        on_detected: Callable[[Sequence[FindingCandidate]], None] | None,
        on_verdict: Callable[[JudgedCandidate, int, int], None] | None,
        on_eliciting: Callable[[], None] | None,
        on_summarising: Callable[[], None] | None,
    ) -> BoundaryReview:
        # Ordered once, here, and passed to every judgement unchanged. The response binds
        # to policies by position, so the order is part of the contract rather than a
        # presentation detail: re-sorting between the request and the result would
        # re-attribute every answer.
        policies = sorted(
            self._policies.catalog(repository_root=repository_root),
            key=lambda policy: policy.id,
        )
        candidates = detect_finding_candidates(atlas)
        # Now the run has a length, which is the one number a reader watching it needs.
        self._reviews.record_progress(running.review_id, detected=len(candidates))
        if on_detected is not None:
            on_detected(candidates)
        # Computed once, outside the loop: the corpus is the same question for every
        # candidate in the run, and it is half of what makes a cached verdict still apply.
        corpus = policy_corpus_fingerprint(policies)
        judged: list[JudgedCandidate] = []
        reused_from: dict[str, str] = {}
        material = 0
        carried = 0
        for position, candidate in enumerate(candidates, start=1):
            self._stop_if_cancelled(running.review_id)
            item = self._verdict_for(
                candidate,
                running=running,
                revision=revision,
                policies=policies,
                corpus=corpus,
            )
            if item.reused_from is not None:
                reused_from[candidate.candidate_id] = item.reused_from
                carried += 1
            judged.append(item)
            material += 1 if item.verdict.material else 0
            # Reported in the same events and the same order as a fresh verdict, and said to
            # be what it is. A cached run is not a quieter run — every boundary still lands,
            # one at a time, in the detected order — but it is a faster one, and a stream
            # that only counted them would have the run claim minutes of judgement it spent
            # looking things up. The count travels with the record too, so a second tab or a
            # reload, which has the columns and not the stream, can say the same thing.
            self._reviews.record_progress(
                running.review_id,
                reviewed=position,
                material=material,
                carried=carried,
            )
            if on_verdict is not None:
                on_verdict(item, position, len(candidates))
        boundaries = reviewed_boundaries(
            [(item.candidate, item.verdict) for item in judged],
            reused_from=reused_from,
        )
        # Checked once more before the last call, which is the longest single wait in the
        # run: cancelling just as the verdicts land should not still cost a summarisation.
        self._stop_if_cancelled(running.review_id)
        status, overview = self._read_the_set(
            revision=revision,
            boundaries=boundaries,
            first_pass=running.elicited_from is None,
            on_eliciting=on_eliciting,
            on_summarising=on_summarising,
        )
        report = BoundaryReviewReport(
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

    def _verdict_for(
        self,
        candidate: FindingCandidate,
        *,
        running: BoundaryReview,
        revision: CaseRevision,
        policies: list[PolicyDocument],
        corpus: str,
    ) -> JudgedCandidate:
        """This candidate's verdict, saying whether it was reached here or carried forward.

        The lookup is unconditional. Every component of the key is a value this run already
        holds before it calls anything — the candidate's own structure, the corpus it is
        about to present, the case revision it loaded, and the model and prompt identities
        the record was opened with — so there is no half-determined key and no case where
        the cache has to be stepped around. Notably absent: the repository and branch ids,
        which may be `None` on an atlas indexed before lineages existed. They are not in the
        key, so that absence changes nothing here.

        A miss writes through under *this* review's id, so the next run can say where the
        verdict came from. The write is not conditional on the run finishing: the verdict
        was genuinely reached, and a cancelled or failed run that already paid for a model
        call should not make the next run pay for it again.
        """

        key = verdict_cache_key(
            boundary=boundary_fingerprint(candidate),
            policy_corpus=corpus,
            case_id=revision.case_id,
            case_revision=revision.revision,
            model_identity=running.reasoning_model,
            prompt_identity=running.prompt_identity,
        )
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
        boundaries: list[ReviewedBoundary],
        first_pass: bool,
        on_eliciting: Callable[[], None] | None,
        on_summarising: Callable[[], None] | None,
    ) -> tuple[ReviewStatus, ReviewOverview]:
        """The one call that sees every verdict at once, and what it makes the run.

        Which call that is depends on the pass, and the whole two-pass flow turns on this
        branch. A first pass asks; a second concludes. Neither does both — a first pass
        composing a conclusion would be drawing one out of a case that usually says nothing,
        and a second pass able to ask would leave the loop with no way to end.

        A first pass with nothing to ask is a finished review, so the two are not fixed to
        the two passes: where every verdict stood on what the case already said, this falls
        straight through to the summary and the reader never sees a question. That is the
        good outcome and the common one for a case someone actually wrote.

        Neither call is made when there are no verdicts. A sweep that found nothing has
        nothing to ask about and nothing to synthesise, and either call would be asking a
        model to invent the content of its own input.

        Neither call consults the verdict cache, which has one visible consequence worth
        naming: a first pass re-run over a wholly unchanged case reuses every verdict and
        then asks the same questions again, because the questions are composed from the
        verdict set rather than looked up. That is left alone here. It is one call rather
        than one per boundary, and caching an elicitation is a different decision from
        caching a verdict — an unanswered question is not a settled answer, and a run that
        skipped asking would have to decide what it means to still be awaiting answers to
        questions it did not put.
        """

        if not boundaries:
            return ReviewStatus.SUCCEEDED, empty_review_overview()
        if first_pass:
            if on_eliciting is not None:
                on_eliciting()
            questions = self._reasoner.elicit_questions(revision.snapshot, boundaries)
            if questions:
                # The run stops here, and the record says so. Nothing further is worth
                # composing: these verdicts are what the case supports so far, and four of
                # five of them moved on the bundled example once the questions were answered
                # (ADR 0010). A conclusion drawn over them would be a conclusion about a case
                # that has not been written yet.
                return (
                    ReviewStatus.AWAITING_ANSWERS,
                    first_pass_overview(boundaries, questions),
                )
        if on_summarising is not None:
            on_summarising()
        return (
            ReviewStatus.SUCCEEDED,
            self._reasoner.summarise_review(revision.snapshot, boundaries),
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
