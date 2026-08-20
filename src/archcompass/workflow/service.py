"""Application entry point for starting and resuming the explicit review graph."""

from __future__ import annotations

from collections.abc import Callable, Iterator, Mapping
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
from archcompass.domain.errors import ReviewNotCancellableError
from archcompass.persistence.executions import InFlightExecution
from archcompass.workflow.runs import ReviewRunner, RunState
from archcompass.workflow.state import ReviewInput, ReviewState


class ReviewSnapshotStore(Protocol):
    def record(self, review: Review) -> Review: ...

    def get(self, review_id: str) -> Review: ...

    def list(self, *, limit: int = 100) -> tuple[Review, ...]: ...

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

    def in_flight(self, *, limit: int = 50) -> tuple[InFlightExecution, ...]: ...

    def fail(self, thread_id: str) -> None: ...

    def abandon_running(self) -> None: ...


@dataclass(frozen=True, slots=True)
class SubmittedAnswer:
    question_id: str
    status: AnswerStatus
    value: str | None = None
    actor: str = "user"


@dataclass(frozen=True, slots=True)
class ReviewProgress:
    stage: str
    review: Review | None = None


class ReviewWorkflowService:
    """One invocation per attempt; graph checkpoints are never domain lineage."""

    def __init__(
        self,
        graph: CompiledStateGraph[ReviewState, None, ReviewInput, ReviewState],
        *,
        reviews: ReviewSnapshotStore,
        executions: ReviewExecutionStore,
        runner: ReviewRunner | None = None,
    ) -> None:
        self._graph = graph
        self._reviews = reviews
        self._executions = executions
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
        return self._bind(thread_id, state["review"])

    def start_stream(
        self,
        *,
        repository_id: str,
        branch_id: str,
        case_id: str,
        case_revision: int | None = None,
        ci: bool = False,
    ) -> Iterator[ReviewProgress]:
        """Expose graph stages as they happen without inventing presentation events."""

        thread_id = self._begin(repository_id, branch_id, case_id)
        source = ReviewInput(
            repository_id=repository_id,
            branch_id=branch_id,
            case_id=case_id,
            case_revision=case_revision,
            ci=ci,
        )
        latest: Review | None = None
        try:
            for raw in self._graph.stream(
                source,
                self._config(thread_id),
                stream_mode="updates",
                subgraphs=True,
            ):
                stage, update = self._progress_update(raw)
                review = update.get("review") if update is not None else None
                typed_review = review if isinstance(review, Review) else None
                if typed_review is not None:
                    latest = self._bind(thread_id, typed_review)
                yield ReviewProgress(stage, typed_review)
        except Exception as error:
            self._record_failure(thread_id, error)
            raise
        if latest is None:
            snapshot = self._graph.get_state(self._config(thread_id)).values
            review = snapshot.get("review")
            if not isinstance(review, Review):
                raise RuntimeError("Review graph ended without a review snapshot")
            latest = self._bind(thread_id, review)
        yield ReviewProgress(latest.status.value, latest)

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

        def work(report: Callable[[str], None]) -> None:
            try:
                for raw in self._graph.stream(
                    source,
                    self._config(thread_id),
                    stream_mode="updates",
                    subgraphs=True,
                ):
                    stage, update = self._progress_update(raw)
                    report(stage)
                    review = update.get("review") if update is not None else None
                    if isinstance(review, Review):
                        bound = self._bind(thread_id, review)
                        self._runner.bind_review(thread_id, bound.id)
            except Exception as error:
                self._record_failure(thread_id, error)
                raise
            current = self._executions.current_review_id(thread_id)
            if current is not None:
                self._runner.bind_review(thread_id, current)

        return self._runner.start(run_id=thread_id, work=work)

    def run_state(self, run_id: str) -> RunState:
        """What a watcher is told, whether or not this process started the run.

        The in-memory state is the richer answer and the execution store is the durable
        one, so the store decides the status and memory fills in the stages. After a
        restart that leaves a run with no stages and an honest status, which beats a
        progress list that claims to be live and is not.
        """

        live = self._runner.state(run_id)
        status = self._executions.status(run_id)
        review_id = self._executions.current_review_id(run_id)
        if live is None:
            return RunState(run_id=run_id, status=status, review_id=review_id)
        return replace(live, status=status, review_id=review_id or live.review_id)

    def resume(
        self,
        review_id: str,
        submissions: tuple[SubmittedAnswer, ...],
        *,
        stop: bool = False,
    ) -> Review:
        thread_id = self._executions.thread_for_review(review_id)
        if self._executions.status(thread_id) != ReviewStatus.AWAITING_ANSWERS.value:
            current_id = self._executions.current_review_id(thread_id)
            if current_id is None:
                raise ValueError(f"Review execution for {review_id} has no snapshot")
            return self._reviews.get(current_id)
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
        try:
            state = self._graph.invoke(
                Command(resume={"answers": answers, "stop": stop}),
                self._config(thread_id),
            )
        except Exception as error:
            self._record_failure(thread_id, error)
            raise
        return self._bind(thread_id, state["review"])

    def cancel(self, review_id: str) -> Review:
        waiting = self._reviews.get(review_id)
        if waiting.status is not ReviewStatus.AWAITING_ANSWERS:
            raise ReviewNotCancellableError(
                f"Review {review_id} is {waiting.status.value}, not awaiting answers"
            )
        cancelled = replace(
            waiting,
            id=stable_id("review", waiting.id, ReviewStatus.CANCELLED.value),
            sequence=waiting.sequence + 1,
            status=ReviewStatus.CANCELLED,
            finished_at=utc_now(),
            previous_review_id=waiting.id,
        )
        recorded = self._reviews.record(cancelled)
        thread_id = self._executions.thread_for_review(review_id)
        self._executions.bind(thread_id, recorded)
        return recorded

    def get(self, review_id: str) -> Review:
        return self._reviews.get(review_id)

    def list(
        self, *, case_id: str | None = None, limit: int = 100
    ) -> tuple[Review, ...]:
        reviews = self._reviews.list(limit=limit)
        if case_id is None:
            return reviews
        return tuple(review for review in reviews if review.case.id == case_id)

    def delete(self, review_id: str) -> None:
        self._reviews.delete(review_id)

    def latest_for_branch(self, branch_id: str) -> Review | None:
        return self._reviews.latest_for_branch(branch_id)

    def in_flight(self, *, limit: int = 50) -> tuple[InFlightExecution, ...]:
        """Runs that have begun and have no review yet.

        Listed beside the reviews rather than instead of them: a run becomes a review the
        moment the graph composes one, and until then there is no review to list — the
        atlas it would have to carry has not been built.
        """

        return self._executions.in_flight(limit=limit)

    def abandon_running(self) -> None:
        self._executions.abandon_running()

    def _bind(self, thread_id: str, review: Review) -> Review:
        self._executions.bind(thread_id, review)
        return review

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
        """Persist the richest immutable failure snapshot the completed stages permit."""

        self._executions.fail(thread_id)
        try:
            values = cast(
                "Mapping[str, object]",
                self._graph.get_state(self._config(thread_id)).values,
            )
        except Exception:
            return None
        repository = values.get("repository")
        atlas = values.get("atlas")
        case = values.get("case")
        if not isinstance(repository, RepositoryRef):
            return None
        if not isinstance(atlas, RepositoryAtlas):
            return None
        if not isinstance(case, ArchitectureCase):
            return None
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
        failure = Review(
            id=stable_id("review", thread_id, ReviewStatus.FAILED.value),
            sequence=1 if previous is None else previous.sequence + 1,
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
        return recorded

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
