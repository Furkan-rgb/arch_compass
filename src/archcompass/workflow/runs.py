"""A review that outlives the request that asked for it.

A review used to be produced inside the HTTP response that streamed it, which made the
browser tab the thing keeping it alive: reloading the page closed the connection, the
generator was collected mid-iteration, and the run stopped somewhere between two stages
with nothing to return to. It also made batch judging impossible to contemplate, because a
batch is answered in minutes or hours rather than in a response body.

So a run is started, given an id, and watched. The id is the graph's own thread id, which
already exists from the first line of a review and is already what the execution store is
keyed by — there was never anything to invent, only something to return.

The stage is held in memory on purpose. Which node is executing right now is worth showing
while the process that is executing it is alive, and worth nothing afterwards; the durable
answer — running, awaiting answers, completed, failed — is the execution store's, and it
survives a restart because it was written down.
"""

from __future__ import annotations

import logging
import threading
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import datetime

from archcompass.domain._support import utc_now
from archcompass.domain.errors import ReviewStillRunningError

_log = logging.getLogger("archcompass.runs")

#: How many finished runs keep their stage list in memory.
#:
#: A convenience for the process, not an invariant of anything. A watcher polls a run it has
#: just started and wants the stages it has been through; nothing needs that a minute later,
#: and the durable answer — running, awaiting answers, completed, failed — is the execution
#: store's and survives a restart. Thirty-two is enough for every run a person is plausibly
#: watching at once and small enough that the number never has to be thought about again.
#:
#: Without a bound the map grew for the life of the process: measured at 2.4 KiB per finished
#: run, which a local run never notices and a long-lived deployment accumulates for ever.
_TERMINAL_HISTORY = 32


@dataclass(frozen=True, slots=True)
class RunState:
    """What a watcher of a run can be told."""

    run_id: str
    #: The execution store's word: running, awaiting_answers, completed, failed, cancelled.
    status: str
    #: Present as soon as the graph has filed a review, which is before the run finishes:
    #: a review that asks a question is recorded, and the run goes on to rejudge the
    #: answers under the same id.
    review_id: str | None = None
    #: The node that was last entered. Empty once the process that ran it has gone.
    stage: str = ""
    #: Every stage seen, in order, so a reload can redraw the progress already made.
    stages: tuple[str, ...] = ()
    #: How many candidates this round set out to judge, and how many now have a verdict.
    #: Carried apart from `stages` because judging is a loop and a stage list is a sequence:
    #: the loop entered fifteen times is one step that is fifteen deep, not fifteen steps,
    #: and only a count can say that. Reset whenever a round selects its candidates, so a
    #: second round counts its own work rather than continuing the first's.
    candidates_to_judge: int = 0
    candidates_judged: int = 0
    #: What the provider did with the batch this run asked for, once it has done it.
    #:
    #: Empty until then, and empty for every run that was never routed to a batch at all.
    #: Deliberately not set from the routing decision: `supports_batch` is a prediction, and
    #: a run that reported a queued batch on the strength of it went on saying so through
    #: the entire interactive fallback that followed the provider's refusal. `queued` means
    #: a submission was accepted; `unavailable` means it was refused and the candidates were
    #: judged one at a time instead.
    batch: str = ""
    failure: str = ""
    #: When this process started the run. `None` for a run it did not start — after a
    #: restart the durable half of the state survives and this does not, and a clock that
    #: began at the restart would read as an elapsed time and be one for the wrong thing.
    started_at: datetime | None = None


class ReviewRunner:
    """Starts review runs on their own threads and reports on them by id.

    Threads rather than an async task group because the graph, its SQLite stores and the
    batch poller are all synchronous, and wrapping them would buy nothing but a second way
    to be wrong about cancellation.
    """

    def __init__(self, *, now: Callable[[], datetime] = utc_now) -> None:
        self._now = now
        self._lock = threading.Lock()
        self._runs: dict[str, RunState] = {}
        self._threads: dict[str, threading.Thread] = {}
        self._cancelled: set[str] = set()
        #: Finished run ids, oldest first, each appearing once. The eviction order for
        #: `_runs`; an id that starts again is moved to the back rather than counted twice.
        self._terminal: deque[str] = deque()

    def start(
        self,
        *,
        run_id: str,
        work: Callable[[Callable[[str], None]], None],
    ) -> RunState:
        """Run `work` on a thread, handing it a callback to report each stage.

        The state is registered before the thread starts, so a watcher that asks
        immediately — which is what the browser does, one redirect later — is never told
        the run does not exist.
        """

        state = RunState(run_id=run_id, status="running", started_at=self._now())
        with self._lock:
            if run_id in self._threads and self._threads[run_id].is_alive():
                # A refusal a caller can act on, not a crash. Two tabs answering the same
                # clarification round is the ordinary way to reach this, and the honest
                # answer is that the work they are asking for is already happening.
                raise ReviewStillRunningError(f"Review run {run_id} is already in flight")
            self._runs[run_id] = state
            # A thread that was cancelled and has ended is a finished run, and the same id
            # is what the next round of the same review is started under. Clearing it here
            # means yesterday's cancellation cannot stop today's work on its first stage.
            self._cancelled.discard(run_id)
            thread = threading.Thread(
                target=self._run,
                args=(run_id, work),
                name=f"archcompass-review-{run_id}",
                daemon=True,
            )
            self._threads[run_id] = thread
        thread.start()
        return state

    def _run(self, run_id: str, work: Callable[[Callable[[str], None]], None]) -> None:
        def report(stage: str) -> None:
            self._update(run_id, stage=stage)

        try:
            try:
                work(report)
            except Exception as error:  # A failed run is a state to read, not a lost thread.
                _log.exception("review run %s failed", run_id)
                self._update(run_id, status="failed", failure=str(error))
            else:
                # `cancelled` rather than `finished` where somebody asked it to stop, because
                # the work stopped short and a reader is owed that. The durable answer is the
                # execution store's; this is the in-memory half, and the two have to agree.
                self._update(
                    run_id, status="cancelled" if self.is_cancelled(run_id) else "finished"
                )
            # Reached only where a terminal status was actually recorded. If recording it
            # raised, the run is not terminal as far as this process knows, and evicting it
            # would delete the state a watcher is about to ask for.
            self._retire(run_id)
        except Exception:
            # Logged rather than raised, for the reason the whole module gives: a thread
            # that dies with an exception nobody catches reports it to nothing. The run
            # keeps whatever state it reached, and the durable store is still the answer.
            _log.exception("review run %s could not record how it ended", run_id)
        finally:
            # Unconditional, and the one thing that is: a thread that has left `_run` is
            # never coming back, whatever happened inside it. `is_running` reads this map and
            # answers `False` for a missing entry, which is already the right answer.
            self._release(run_id, threading.current_thread())

    def _release(self, run_id: str, thread: threading.Thread) -> None:
        with self._lock:
            # Identity-checked because the id is reused: the next round of the same review
            # runs under it, and a late release must not drop the thread that replaced this
            # one. `start` refuses while the previous thread is alive, so this cannot happen
            # today — it is one comparison against it ever starting to.
            if self._threads.get(run_id) is thread:
                del self._threads[run_id]

    def _retire(self, run_id: str) -> None:
        """Add a finished run to the terminal tail, and drop whatever falls off the front."""

        with self._lock:
            if run_id in self._terminal:
                self._terminal.remove(run_id)
            self._terminal.append(run_id)
            while len(self._terminal) > _TERMINAL_HISTORY:
                oldest = self._terminal.popleft()
                thread = self._threads.get(oldest)
                # An id that has started again is live state, not history. It leaves the tail
                # and keeps its entry; finishing again puts it back on the end.
                if thread is None or not thread.is_alive():
                    self._runs.pop(oldest, None)

    def _update(self, run_id: str, **changes: object) -> None:
        with self._lock:
            current = self._runs.get(run_id)
            if current is None:
                return
            stage = changes.pop("stage", None)
            if isinstance(stage, str):
                changes["stage"] = stage
                if not current.stages or current.stages[-1] != stage:
                    changes["stages"] = (*current.stages, stage)
            self._runs[run_id] = replace(current, **changes)  # type: ignore[arg-type]

    def bind_review(self, run_id: str, review_id: str) -> None:
        """Record the review the run has produced, as soon as there is one to open."""

        self._update(run_id, review_id=review_id)

    def report_judgements(self, run_id: str, *, judged: int, to_judge: int) -> None:
        """How far through its candidates this round is."""

        self._update(run_id, candidates_judged=judged, candidates_to_judge=to_judge)

    def report_batch(self, run_id: str, outcome: str) -> None:
        """What the provider did with the batch, as soon as it has done it."""

        self._update(run_id, batch=outcome)

    def cancel(self, run_id: str) -> None:
        """Ask a run to stop at its next stage boundary.

        Cooperative, because there is nothing here that could safely be stronger. The work
        is a graph driving SQLite stores and a provider client on a thread, and killing a
        thread part way through a node would leave a checkpoint written by half a step. So
        the flag is set and the loop reads it between stages: the node in flight finishes,
        and no further one starts.

        Which means the run keeps running for as long as the current stage takes — a batch
        judgement, at worst, is minutes. The intention is recorded immediately anyway, so a
        reader is told the run is stopping rather than left pressing the button again.
        """

        with self._lock:
            self._cancelled.add(run_id)

    def is_cancelled(self, run_id: str) -> bool:
        """Whether somebody has asked this run to stop. Read between stages, by the work."""

        with self._lock:
            return run_id in self._cancelled

    def state(self, run_id: str) -> RunState | None:
        with self._lock:
            return self._runs.get(run_id)

    def is_running(self, run_id: str) -> bool:
        with self._lock:
            thread = self._threads.get(run_id)
        return thread is not None and thread.is_alive()
