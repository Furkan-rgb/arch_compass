"""Application entry point for starting and resuming the explicit review graph."""

from __future__ import annotations

import logging
import sqlite3
from collections.abc import Callable, Mapping, Sized
from contextlib import AbstractContextManager
from dataclasses import dataclass, replace
from typing import Protocol, cast

from langchain_core.runnables import RunnableConfig
from langgraph.graph.state import CompiledStateGraph
from langgraph.types import Command

from archcompass.domain import (
    Answer,
    AnswerStatus,
    ArchitectureCase,
    Finding,
    RepositoryAtlas,
    RepositoryRef,
    RetrievalProvenance,
    Review,
    ReviewDelta,
    ReviewStatus,
)
from archcompass.domain._support import new_id, stable_id, utc_now
from archcompass.domain.errors import (
    NothingToReviewError,
    ReviewNotCancellableError,
    ReviewSupersededError,
)
from archcompass.persistence.executions import ExecutionRecord
from archcompass.persistence.ports import CaseSnapshots
from archcompass.persistence.reviews import ReviewSummary
from archcompass.workflow.runs import ReviewRunner, RunState
from archcompass.workflow.state import ReviewInput, ReviewState

_log = logging.getLogger(__name__)


class ReviewSnapshotStore(Protocol):
    def record(self, review: Review) -> Review: ...

    def sequence_of(self, review_id: str) -> int | None: ...

    def get(self, review_id: str) -> Review: ...

    def list(self, *, limit: int = 100) -> tuple[Review, ...]: ...

    def list_summaries(self, *, limit: int = 100) -> tuple[ReviewSummary, ...]: ...

    def delete(self, review_id: str) -> None: ...

    def latest_for_branch(self, branch_id: str) -> Review | None: ...


class ReviewExecutionStore(Protocol):
    def begin(
        self,
        *,
        thread_id: str,
        repository_id: str,
        branch_id: str,
        case_id: str,
    ) -> None: ...

    def bind(self, thread_id: str, review: Review) -> None: ...

    def thread_for_review(self, review_id: str) -> str: ...

    def status(self, thread_id: str) -> str: ...

    def current_review_id(self, thread_id: str) -> str | None: ...

    def record(self, thread_id: str) -> ExecutionRecord | None: ...

    def in_flight(self, *, limit: int = 50) -> tuple[ExecutionRecord, ...]: ...

    def resume(self, thread_id: str) -> None: ...

    def fail(self, thread_id: str) -> None: ...

    def cancel(self, thread_id: str) -> None: ...

    def abandon_running(self) -> None: ...


@dataclass(frozen=True, slots=True)
class SubmittedAnswer:
    question_id: str
    status: AnswerStatus
    value: str | None = None
    actor: str = "user"


#: The nodes that produce a verdict. `judge_candidate` is one candidate's turn through the
#: per-candidate subgraph; `review_candidates` is the whole selection judged in one batch.
#: Both answer the same question a watcher is asking — how many are done — so both count.
_JUDGING_STAGES = frozenset({"judge_candidate", "review_candidates"})

#: The nodes that file a snapshot, and therefore the only updates whose review is on disk.
#:
#: `compose_final_review` and `compose_waiting_review` also put a `Review` in the state, and
#: binding one of those published an id that nothing could open yet: the recorder had not
#: run, so the run had left every "still working" listing and the review it named answered
#: 404 for as long as the recording took. A run says it has a review when there is one.
_RECORDING_STAGES = frozenset({"record_review", "record_waiting_review"})

#: Execution statuses that describe a review rather than the run that produced it.
#:
#: They are written when a snapshot is filed, which is before the run stops, so they are
#: only the whole truth once there is no thread on the run any more.
_REVIEW_STATUSES = frozenset(
    {ReviewStatus.AWAITING_ANSWERS.value, ReviewStatus.COMPLETED.value}
)


@dataclass
class _JudgingProgress:
    """How far through its candidates a round is, read off the graph's own updates.

    Nothing here is invented for the progress display: the total is the selection a round
    made, and the count is the findings its judging nodes returned. A round that selects
    again — a second round, after answers — starts over, because the reader is watching this
    round rather than the run's whole history.
    """

    to_judge: int = 0
    judged: int = 0

    def observe(self, stage: str, update: Mapping[str, object] | None) -> bool:
        """Take in one graph update. True where the counts moved and are worth reporting."""

        if update is None:
            return False
        selected = update.get("selected_candidates")
        if isinstance(selected, Sized):
            self.to_judge = len(selected)
            self.judged = 0
            return True
        if stage not in _JUDGING_STAGES:
            return False
        findings = update.get("findings")
        if not isinstance(findings, Sized):
            return False
        self.judged = min(self.judged + len(findings), self.to_judge)
        return True


class ReviewWorkflowService:
    """One invocation per attempt; graph checkpoints are never domain lineage."""

    def __init__(
        self,
        graph: CompiledStateGraph[ReviewState, None, ReviewInput, ReviewState],
        *,
        reviews: ReviewSnapshotStore,
        executions: ReviewExecutionStore,
        cases: CaseSnapshots | None = None,
        runner: ReviewRunner | None = None,
    ) -> None:
        self._graph = graph
        self._reviews = reviews
        self._executions = executions
        # Only the failure path writes through this, which is why it is optional: a graph
        # that reaches its end seals its own case through `seal_case`, and a test driving
        # one needs nothing here.
        self._cases = cases
        self._runner = runner or ReviewRunner()

    def start(
        self,
        *,
        repository_id: str,
        branch_id: str,
        case_id: str,
        case_revision: int | None = None,
        ci: bool = False,
    ) -> Review:
        thread_id = self._begin(repository_id, branch_id, case_id)
        try:
            state = self._graph.invoke(
                ReviewInput(
                    repository_id=repository_id,
                    branch_id=branch_id,
                    case_id=case_id,
                    case_revision=case_revision,
                    ci=ci,
                ),
                self._config(thread_id),
            )
        except Exception as error:
            self._record_failure(thread_id, error)
            raise
        bound = self._bind(thread_id, state["review"])
        self._release(thread_id)
        return bound

    def start_background(
        self,
        *,
        repository_id: str,
        branch_id: str,
        case_id: str,
        case_revision: int | None = None,
        ci: bool = False,
    ) -> RunState:
        """Start a review that is not held open by whoever asked for it.

        Returns the moment the run has an id, which is before it has a review — that is
        the whole point. The caller is handed something to come back to, so a reload lands
        on the run rather than on nothing, and a judgement that takes an hour in a batch
        costs nobody a connection.
        """

        thread_id = self._begin(repository_id, branch_id, case_id)
        source = ReviewInput(
            repository_id=repository_id,
            branch_id=branch_id,
            case_id=case_id,
            case_revision=case_revision,
            ci=ci,
        )
        return self._runner.start(run_id=thread_id, work=self._driver(thread_id, source))

    def resume_background(
        self,
        review_id: str,
        submissions: tuple[SubmittedAnswer, ...],
        *,
        stop: bool = False,
    ) -> RunState:
        """Record the answers and rejudge on a run, rather than inside the request.

        Answering a clarification round rejudges every extant candidate, which is the same
        minutes of model work the first review spent — and it used to be spent inside one
        POST, so a reload, a closed laptop or a proxy's idle timeout left the person unable
        to tell whether their answers had been recorded at all. That is the failure
        `start_background` exists to prevent, and this is the same fix on the other half of
        the review: the answers are validated here, where a bad one can still be refused
        properly, and the judging goes on a run somebody can come back to.

        The run is the thread the review has always been on, so its id is the one the first
        run carried and `/api/reviews/runs/{id}` keeps working across the whole review.
        """

        thread_id, command = self._resume_command(review_id, submissions, stop=stop)
        if command is None:
            # Already answered, by a retry or a second tab. There is nothing to start, and
            # the run this would have been is the one that took the first submission.
            return self.run_state(thread_id)
        # The row said `awaiting_answers`, which stops being true the moment these answers
        # are accepted. Written before the thread starts, so a listing asked immediately
        # afterwards sees a run rather than a review that is still waiting.
        self._executions.resume(thread_id)
        return self._runner.start(
            run_id=thread_id, work=self._driver(thread_id, command)
        )

    def _driver(
        self, thread_id: str, source: ReviewInput | Command[str]
    ) -> Callable[[Callable[[str], None]], None]:
        """The work of one run: drive the graph, report on it, and stop when asked to.

        Shared by starting a review and by rejudging one after a clarification round,
        because a watcher of either is asking the same questions — which stage, how many
        candidates, what the provider did with the batch — and two copies of this loop would
        answer them differently the first time one of them changed.
        """

        def work(report: Callable[[str], None]) -> None:
            judging = _JudgingProgress()
            cancelled = False
            try:
                for raw in self._graph.stream(
                    source,
                    self._config(thread_id),
                    # `custom` alongside `updates` because one thing a watcher needs to know
                    # arrives while a node is still running rather than when it returns:
                    # whether the provider took the batch. A node's return value cannot say
                    # so — it arrives an hour later, when the answer no longer matters.
                    stream_mode=["updates", "custom"],
                    subgraphs=True,
                ):
                    mode, payload = self._streamed(raw)
                    if mode == "custom":
                        outcome = self._batch_outcome(payload)
                        if outcome:
                            self._runner.report_batch(thread_id, outcome)
                        continue
                    stage, update = self._progress_update(payload)
                    report(stage)
                    if judging.observe(stage, update):
                        self._runner.report_judgements(
                            thread_id,
                            judged=judging.judged,
                            to_judge=judging.to_judge,
                        )
                    review = update.get("review") if update is not None else None
                    if stage in _RECORDING_STAGES and isinstance(review, Review):
                        bound = self._bind(thread_id, review)
                        self._runner.bind_review(thread_id, bound.id)
                    # Between stages, never inside one: the node that just returned wrote a
                    # checkpoint, so the graph stops at a boundary rather than half way
                    # through a step.
                    if self._runner.is_cancelled(thread_id):
                        cancelled = True
                        break
            except Exception as error:
                self._record_failure(thread_id, error)
                raise
            current = self._executions.current_review_id(thread_id)
            if current is not None and not cancelled:
                self._runner.bind_review(thread_id, current)
            # After the loop and never inside it: the stream is reading from the checkpoints
            # this deletes. A cancelled run reaches here too, because a cancelled run is
            # over — `_resume_command` refuses any execution that is not awaiting answers,
            # so nothing in this product can start one again, and the comment that used to
            # say the graph was "left resumable from the last completed stage" was
            # describing a resume that does not exist. Those are the largest checkpoints a
            # workspace ever holds; leaving them was a leak rather than a decision.
            self._release(thread_id)

        return work

    def run_state(self, run_id: str) -> RunState:
        """What a watcher is told, whether or not this process started the run.

        The in-memory state is the richer answer and the execution store is the durable
        one, so the store decides the status and memory fills in the stages. After a
        restart that leaves a run with no stages and an honest status, which beats a
        progress list that claims to be live and is not.

        With one correction, which is what `_REVIEW_STATUSES` is for. `awaiting_answers`
        and `completed` are written the moment the graph files a snapshot, and the run goes
        on for a little longer after that — so a watcher was told the run had ended while
        this process still had a thread on it, and a client acting on that answer got a
        refusal for work it had just been told was finished. A run this process is still
        working on says `running`.

        A run somebody cancelled is not corrected: that status is about the run rather than
        about a review it filed, and it is the answer to "what did my button do".
        """

        live = self._runner.state(run_id)
        status = self._executions.status(run_id)
        review_id = self._executions.current_review_id(run_id)
        if live is None:
            return RunState(run_id=run_id, status=status, review_id=review_id)
        if status in _REVIEW_STATUSES and self._runner.is_running(run_id):
            status = "running"
        return replace(live, status=status, review_id=review_id or live.review_id)

    def resume(
        self,
        review_id: str,
        submissions: tuple[SubmittedAnswer, ...],
        *,
        stop: bool = False,
    ) -> Review:
        thread_id, command = self._resume_command(review_id, submissions, stop=stop)
        if command is None:
            return self._recorded_for(thread_id, review_id)
        # Marked in flight before the graph runs, exactly as `resume_background` does. This
        # is minutes of judging, and while the row went on saying `awaiting_answers` a second
        # post of the same answers passed the guard above and produced a *second* round-two
        # snapshot under one sequence — with the caller of the first holding an id that reads
        # fine and refuses every later answer.
        self._executions.resume(thread_id)
        try:
            state = self._graph.invoke(command, self._config(thread_id))
        except Exception as error:
            self._record_failure(thread_id, error)
            raise
        bound = self._bind(thread_id, state["review"])
        self._release(thread_id)
        return bound

    def _recorded_for(self, thread_id: str, review_id: str) -> Review:
        current_id = self._executions.current_review_id(thread_id)
        if current_id is None:
            raise ValueError(f"Review execution for {review_id} has no snapshot")
        return self._reviews.get(current_id)

    def _resume_command(
        self,
        review_id: str,
        submissions: tuple[SubmittedAnswer, ...],
        *,
        stop: bool = False,
    ) -> tuple[str, Command[str] | None]:
        """Check one round of answers and turn them into the graph's resume command.

        `None` where there is nothing left to resume. The same answers arriving twice — a
        retry, a second tab, a run that already took them — is a question about work that
        has been done rather than a conflict, so the caller is handed what was recorded.

        That forgiveness has one edge, and it is sharp. A review that asks twice files two
        waiting snapshots under one sequence, and a snapshot is immutable: round one's copy
        says `awaiting_answers` for ever, and while round two is open so does the execution.
        Both of the checks below therefore answered yes for a submission written against a
        round that had already been taken — so round one's answers resumed round two's
        interrupt, `with_answers` found five equivalence keys it already held and raised,
        and the round failed against a case revision `seal_case` never got to write. The
        answers a person typed survived nowhere but inside a review blob.

        Which snapshot the execution currently stands on is the one fact that separates the
        two, so it is asked here, and only while the review is still waiting: once it has
        reached an end there is nothing to replay into and handing back what was recorded is
        the right answer again.
        """

        thread_id = self._executions.thread_for_review(review_id)
        if self._executions.status(thread_id) != ReviewStatus.AWAITING_ANSWERS.value:
            return thread_id, None
        current_id = self._executions.current_review_id(thread_id)
        if current_id is not None and current_id != review_id:
            raise ReviewSupersededError(
                f"Review {review_id} has already been answered; this review is now waiting "
                f"on {current_id}. Read it again before answering — the questions it is "
                "waiting for are not the ones these answers were written against."
            )
        waiting = self._reviews.get(review_id)
        if waiting.status is not ReviewStatus.AWAITING_ANSWERS:
            raise ValueError(f"Review {review_id} is not awaiting answers")
        by_id = {item.question_id: item for item in submissions}
        unknown = set(by_id) - {item.id for item in waiting.questions}
        if unknown:
            raise ValueError(f"Answers name unknown questions: {', '.join(sorted(unknown))}")
        # Every pending question receives an explicit outcome. Omitted entries are skips,
        # which makes partial responses auditable rather than indistinguishable from loss.
        answers = tuple(
            Answer(
                question=question,
                status=(
                    by_id[question.id].status
                    if question.id in by_id
                    else AnswerStatus.SKIPPED
                ),
                value=by_id[question.id].value if question.id in by_id else None,
                actor=by_id[question.id].actor if question.id in by_id else "user",
                answered_at=utc_now(),
            )
            for question in waiting.questions
        )
        return thread_id, Command(resume={"answers": answers, "stop": stop})

    def cancel(self, review_id: str) -> Review:
        """Stop a review that is waiting for an answer nobody is going to give.

        Guarded the same way answering is, and for the same reason. A snapshot is immutable,
        so round one's copy says `awaiting_answers` for ever — asking it, as this used to,
        let a stale tab cancel a round that had already been answered and superseded. That
        was merely confusing until a cancelled thread began releasing its checkpoints, at
        which point it deleted the live interrupt round two was waiting on and there was no
        way back.
        """

        waiting = self._reviews.get(review_id)
        if waiting.status is not ReviewStatus.AWAITING_ANSWERS:
            raise ReviewNotCancellableError(
                f"Review {review_id} is {waiting.status.value}, not awaiting answers"
            )
        thread_id = self._executions.thread_for_review(review_id)
        current_id = self._executions.current_review_id(thread_id)
        if current_id is not None and current_id != review_id:
            raise ReviewSupersededError(
                f"Review {review_id} has already been answered; this review is now waiting "
                f"on {current_id}. Read it again — cancelling this snapshot would stop a "
                "round that is not the one you are looking at."
            )
        # The same revision, cancelled — not the one after it. Cancelling is how this
        # review ended, and a review that ended does not become its own successor.
        cancelled = replace(
            waiting,
            id=stable_id("review", waiting.id, ReviewStatus.CANCELLED.value),
            status=ReviewStatus.CANCELLED,
            finished_at=utc_now(),
        )
        recorded = self._reviews.record(cancelled)
        self._executions.bind(thread_id, recorded)
        self._release(thread_id)
        return recorded

    def cancel_run(self, run_id: str) -> RunState:
        """Stop a run somebody no longer wants, and say so where the run is read.

        The run keeps its id and its stages and takes the status `cancelled` — the same
        word the domain already uses for a review a person stopped, and deliberately not
        `failed`, which would send a reader looking for a defect that is not there. It is
        also not a deletion: a run that vanished would leave whoever pressed the button
        unable to tell that it had, and the address they were given answering nothing.

        Where the graph had already recorded a snapshot, that review is untouched and stays
        exactly what it was — cancelling stops the work that had not been done, and never
        rewrites what had.

        Answered before the thread has noticed, because the flag is read between stages and
        the stage in flight may be a batch. The status is what was decided; the stages a
        watcher keeps polling are what has happened.
        """

        self._runner.cancel(run_id)
        self._executions.cancel(run_id)
        return self.run_state(run_id)

    def get(self, review_id: str) -> Review:
        return self._reviews.get(review_id)

    def sequence_of(self, review_id: str) -> int | None:
        """Which review this is, without decoding the review to find out.

        Here rather than on the store because a route asking the store directly is a route
        that has reached past every seam this service exists to be — and the run endpoint,
        which is the only caller, is already asking this service for everything else it
        knows about a review.
        """

        return self._reviews.sequence_of(review_id)

    def list(
        self, *, case_id: str | None = None, limit: int = 100
    ) -> tuple[Review, ...]:
        reviews = self._reviews.list(limit=limit)
        if case_id is None:
            return reviews
        return tuple(review for review in reviews if review.case.id == case_id)

    def list_summaries(self, *, limit: int = 100) -> tuple[ReviewSummary, ...]:
        """The listing every screen but the workbench actually reads.

        A review carries its atlas, and eight surfaces show a name, a number and a count
        off it. Kept beside `list` rather than replacing it because the review page needs
        the whole record and asking it to assemble one out of summaries would be the same
        download in more requests.
        """

        return self._reviews.list_summaries(limit=limit)

    def delete(self, review_id: str) -> None:
        self._reviews.delete(review_id)

    def latest_for_branch(self, branch_id: str) -> Review | None:
        return self._reviews.latest_for_branch(branch_id)

    def in_flight(self, *, limit: int = 50) -> tuple[ExecutionRecord, ...]:
        """Runs that have begun and are not finished.

        Listed beside the reviews rather than instead of them. Most of these have no review
        yet — the atlas one would have to carry has not been built — and a rejudgement after
        a clarification round has one, because it is judging answers against the snapshot
        the reader is holding. A listing that drops a run the moment a review is attached
        drops it several minutes before it ends, which is what made a finished run and a
        run that never existed look identical.
        """

        return self._executions.in_flight(limit=limit)

    def lineage_of(self, run_id: str) -> ExecutionRecord | None:
        """Which repository, branch and case a run belongs to."""

        return self._executions.record(run_id)

    def abandon_running(self) -> None:
        """Mark runs a departed process left behind as failed, and free what they held.

        The thread ids are read before the row is rewritten, because afterwards nothing says
        which runs were abandoned. They are the largest checkpoints a workspace ever holds —
        a run that died mid-review died with the whole state checkpointed — and nothing else
        will ever come back for them: an abandoned thread is `failed`, and a failed thread
        cannot be resumed.
        """

        abandoned = [record.thread_id for record in self._executions.in_flight(limit=1000)]
        self._executions.abandon_running()
        for thread_id in abandoned:
            self._release(thread_id)

    def _bind(self, thread_id: str, review: Review) -> Review:
        self._executions.bind(thread_id, review)
        return review

    def _seal_after_failure(
        self, case: ArchitectureCase, *, opened: bool
    ) -> ArchitectureCase:
        """Write the case revision a failed round opened, or leave it exactly as it is.

        `opened` is the graph's own `case_opened`, and it is the only honest question. The
        guard was "does this case carry answers", which is true of every case any earlier
        review ever answered — so a run that failed before asking anything re-recorded a
        revision already on disk, on every failure, and would have swallowed a genuine
        conflict the day those bytes differed.
        """

        if self._cases is None or not opened:
            return case
        try:
            return self._cases.record(case)
        except Exception:
            _log.warning(
                "Case %s revision %d could not be written after a failed round",
                case.id,
                case.revision,
                exc_info=True,
            )
            return case

    def _release(self, thread_id: str) -> None:
        """Drop the execution checkpoints of a review that has reached an end.

        A checkpoint exists to resume from, and a review that completed, failed or was
        cancelled is never resumed: `_resume_command` answers with what was recorded, and
        every surface that reads a finished review reads the immutable snapshot. So once a
        thread reaches a terminal status its checkpoints are the working notes of work that
        is over, and keeping them is not caution — it is a leak with a durable name.

        And it is a large one. LangGraph writes the whole `ReviewState` at every superstep,
        and that state carries the atlas, the policy corpus, the retrieved policy sets and
        every finding so far. One review of a six-file example repository left a **131 MB**
        checkpoint database beside a 948 KB workspace; a development machine reached 56 GB,
        with individual writes of 8 to 78 MB, and those writes are what made a thirty-second
        POST miss its deadline and get retried into the double-submission that destroyed a
        case. The bound is not a nicety.

        A review still `awaiting_answers` keeps everything, and it is the only status that
        does: it is the one whose whole purpose is to be resumed from, possibly days later.
        Everything else — completed, failed, cancelled — is over, and `_resume_command`
        refuses all three.

        The status is read off the execution row rather than passed in, because every caller
        has already written it there and reading it back is a column. The alternative was
        handing this the review, which meant decoding a stored document that can run to
        megabytes in order to look at one word.

        Nothing here may raise. A checkpointer that cannot delete, or a file somebody has
        made read-only, is a disk that fills more slowly than it should — not a review that
        fails after it has already been recorded.
        """

        try:
            if self._executions.status(thread_id) == ReviewStatus.AWAITING_ANSWERS.value:
                return
            saver = cast("object", getattr(self._graph, "checkpointer", None))
            delete = cast(
                "Callable[[str], None] | None", getattr(saver, "delete_thread", None)
            )
            if delete is None:
                return
            delete(thread_id)
            self._reclaim(saver)
        except Exception:
            _log.warning(
                "The checkpoints for %s could not be released", thread_id, exc_info=True
            )

    @staticmethod
    def _reclaim(saver: object) -> None:
        """Hand the freed pages back to the filesystem, under the saver's own lock.

        Two statements and both are needed: `incremental_vacuum` moves the freed pages off
        the end of the database — a no-op unless it was opened with
        `auto_vacuum = INCREMENTAL`, which `build_runtime` asks for — and the WAL checkpoint
        is what lets the file on disk actually shrink, because until the write-ahead log is
        folded back in, the smaller database exists only in the log. Without the second one
        the first measures as having done nothing at all.

        **The lock is not optional.** One SQLite connection serves every review in a
        workspace, and `SqliteSaver` guards every one of its own uses of it. Running these
        two statements beside that, unlocked, left a statement in progress across the
        saver's next `commit()` and raised `OperationalError: cannot commit transaction`
        *inside another thread's graph* — so a review finishing normally could fail an
        unrelated review that happened to be running at the time, and this method's own
        `except` could not see it. Taken after `delete_thread` rather than around it,
        because that method takes the same non-reentrant lock itself.

        A saver that exposes neither a lock nor a connection is left alone: the pages are
        still reusable, and `_reclaim_checkpoint_space` returns them at the next open.
        """

        connection = cast("sqlite3.Connection | None", getattr(saver, "conn", None))
        lock = cast("AbstractContextManager[object] | None", getattr(saver, "lock", None))
        if connection is None or lock is None:
            return
        with lock:
            connection.execute("PRAGMA incremental_vacuum").fetchall()
            # Yields rather than waits where another review is mid-write: SQLite answers
            # busy, the file keeps its high-water mark for now, and the next review to end
            # alone reclaims it.
            connection.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchall()

    def _begin(self, repository_id: str, branch_id: str, case_id: str) -> str:
        thread_id = new_id("thread")
        self._executions.begin(
            thread_id=thread_id,
            repository_id=repository_id,
            branch_id=branch_id,
            case_id=case_id,
        )
        return thread_id

    def _record_failure(self, thread_id: str, error: Exception) -> Review | None:
        """Persist the richest immutable failure snapshot the completed stages permit.

        With one exception, which is the whole of `NothingToReviewError`. That is not a
        review that failed; it is the answer that there was no review to run, and its own
        docstring says it is raised before anything is written. It was not: by the time
        `select_initial_candidates` raises it the repository, atlas and case are all in
        state, so this method built a snapshot from them and filed it — and a person who
        pressed "Run review" on unchanged code, was correctly told nothing had changed, then
        found a failed "Review 2" on the rail that they had not asked to keep and could not
        get rid of. The run is still marked failed, so nothing dangles; nothing is recorded,
        so the branch's line stays a history of what happened to the code.
        """

        self._executions.fail(thread_id)
        if isinstance(error, NothingToReviewError):
            self._release(thread_id)
            return None
        try:
            values = cast(
                "Mapping[str, object]",
                self._graph.get_state(self._config(thread_id)).values,
            )
        except Exception:
            self._release(thread_id)
            return None
        repository = values.get("repository")
        atlas = values.get("atlas")
        case = values.get("case")
        # A run that failed before the context was loaded has no snapshot worth writing —
        # but it still has checkpoints, and these three exits used to walk past them. A
        # review that fails early is exactly the one somebody runs again immediately.
        if (
            not isinstance(repository, RepositoryRef)
            or not isinstance(atlas, RepositoryAtlas)
            or not isinstance(case, ArchitectureCase)
        ):
            self._release(thread_id)
            return None
        # The revision this round opened, written before a review is filed naming it.
        #
        # `seal_case` is the only node that writes one and a failed run never reaches it, so
        # a failed snapshot used to point at a revision `core_case_snapshots` did not hold:
        # the answers a person typed survived nowhere but inside a review blob, every later
        # review was judged against the revision before them, and opening the one the
        # interface named answered 404. Sealing here is the honest repair — the answers were
        # given, and a round failing to rejudge on them is not a reason to lose them.
        #
        # Guarded, because it must not turn a failure into a different failure. A conflict
        # here means somebody else took the number, which is worth knowing and is not worth
        # replacing the exception the caller is already about to see.
        case = self._seal_after_failure(case, opened=bool(values.get("case_opened")))
        previous_value = values.get("previous_review")
        previous = previous_value if isinstance(previous_value, Review) else None
        raw_findings = values.get("findings")
        findings = (
            tuple(
                sorted(
                    (
                        item
                        for item in cast("Mapping[object, object]", raw_findings).values()
                        if isinstance(item, Finding)
                    ),
                    key=lambda item: str(item.candidate.id),
                )
            )
            if isinstance(raw_findings, Mapping)
            else ()
        )
        delta_value = values.get("delta")
        delta = delta_value if isinstance(delta_value, ReviewDelta) else ReviewDelta()
        raw_retrievals = values.get("retrievals")
        provenance: list[RetrievalProvenance] = []
        if isinstance(raw_retrievals, Mapping):
            for retrieval in cast("Mapping[object, object]", raw_retrievals).values():
                item = getattr(retrieval, "provenance", None)
                if isinstance(item, RetrievalProvenance):
                    provenance.append(item)
        now = utc_now()
        # `previous` is the review this run was judged against and never this run itself,
        # so the number after it is this run's own — including where the run had already
        # filed a waiting snapshot under it.
        round_value = values.get("round")
        failure = Review(
            id=stable_id("review", thread_id, ReviewStatus.FAILED.value),
            sequence=1 if previous is None else previous.sequence + 1,
            round=round_value if isinstance(round_value, int) and round_value >= 1 else 1,
            repository=repository,
            atlas=atlas,
            case=case,
            findings=findings,
            questions=(),
            status=ReviewStatus.FAILED,
            delta=delta,
            started_at=now,
            finished_at=now,
            previous_review_id=None if previous is None else previous.id,
            retrieval_manifest=tuple(
                sorted(provenance, key=lambda item: str(item.candidate_id))
            ),
            failure=f"{type(error).__name__}: {error}",
        )
        recorded = self._reviews.record(failure)
        self._executions.bind(thread_id, recorded)
        self._release(thread_id)
        return recorded

    @staticmethod
    def _batch_outcome(payload: object) -> str:
        """What a `custom` event says about the batch, or nothing if it says something else."""

        if not isinstance(payload, Mapping):
            return ""
        emitted = cast("Mapping[object, object]", payload).get("batch")
        return emitted if isinstance(emitted, str) else ""

    @staticmethod
    def _streamed(raw: object) -> tuple[str, object]:
        """One streamed item as `(mode, payload)`, however the graph wrapped it.

        Asking for more than one stream mode changes the shape of every item — `(namespace,
        mode, payload)` rather than `(namespace, payload)` — so the unwrapping is here and
        the loop reads modes rather than guessing from the payload. An item that arrives in
        neither shape is treated as an update, which is what it was before this existed.
        """

        if isinstance(raw, tuple):
            parts = cast("tuple[object, ...]", raw)
            if len(parts) == 3:
                return str(parts[1]), parts[2]
            if len(parts) == 2:
                return "updates", parts[1]
        return "updates", cast("object", raw)

    @staticmethod
    def _progress_update(raw: object) -> tuple[str, Mapping[str, object] | None]:
        value = raw
        if isinstance(value, tuple):
            pair = cast("tuple[object, ...]", value)
            if len(pair) == 2:
                value = pair[1]
        if not isinstance(value, Mapping) or not value:
            return "graph", None
        mapping = cast("Mapping[object, object]", value)
        key = next(iter(mapping))
        stage = str(key)
        update = mapping[key]
        return (
            stage,
            cast(
                "Mapping[str, object] | None",
                update if isinstance(update, Mapping) else None,
            ),
        )

    @staticmethod
    def _config(thread_id: str) -> RunnableConfig:
        return RunnableConfig(configurable={"thread_id": thread_id})
