"""Single-worker local queue for auditable consultations."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from pydantic import JsonValue

from archcompass.application.advice import AdviceService
from archcompass.domain.consultation import ConsultationStatus
from archcompass.domain.execution import (
    ConsultationJob,
    ConsultationJobStatus,
    ConsultationProgressEvent,
    ProgressEventType,
)
from archcompass.ports.progress import (
    ConsultationJobRepository,
    ConsultationProgressSink,
)
from archcompass.ports.repositories import CaseRepository, ConsultationRunRepository


class RepositoryProgressSink(ConsultationProgressSink):
    def __init__(
        self,
        *,
        run_id: str,
        jobs: ConsultationJobRepository,
    ) -> None:
        self._run_id = run_id
        self._jobs = jobs

    def emit(
        self,
        *,
        event_type: ProgressEventType,
        stage: str | None,
        title: str,
        summary: str = "",
        data: dict[str, JsonValue] | None = None,
    ) -> ConsultationProgressEvent:
        if event_type == ProgressEventType.STAGE_STARTED:
            self._jobs.update(
                self._run_id,
                status=ConsultationJobStatus.RUNNING,
                current_stage=stage,
            )
        return self._jobs.append_event(
            self._run_id,
            event_type=event_type,
            stage=stage,
            title=title,
            summary=summary,
            data=data,
        )


class ConsultationJobService:
    def __init__(
        self,
        *,
        cases: CaseRepository,
        runs: ConsultationRunRepository,
        jobs: ConsultationJobRepository,
        advice: AdviceService,
    ) -> None:
        self._cases = cases
        self._runs = runs
        self._jobs = jobs
        self._advice = advice
        self._executor = ThreadPoolExecutor(
            max_workers=1,
            thread_name_prefix="archcompass-consultation",
        )

    def start(
        self,
        case_id: str,
        *,
        repository_root: Path | None = None,
    ) -> ConsultationJob:
        revision = self._cases.get(case_id)
        job = self._jobs.create(
            ConsultationJob(
                case_id=case_id,
                input_case_revision=revision.revision,
                repository_root=(
                    str(repository_root.expanduser().resolve(strict=False))
                    if repository_root is not None
                    else None
                ),
            )
        )
        self._jobs.append_event(
            job.run_id,
            event_type=ProgressEventType.QUEUED,
            stage=None,
            title="Consultation queued",
            summary=f"Case revision {job.input_case_revision} is ready for analysis.",
        )
        self._executor.submit(self._execute, job)
        return job

    def get(self, run_id: str) -> ConsultationJob:
        return self._jobs.get(run_id)

    def list(self, *, limit: int = 50) -> list[ConsultationJob]:
        return self._jobs.list(limit=limit)

    def events(
        self,
        run_id: str,
        *,
        after_sequence: int = 0,
    ) -> list[ConsultationProgressEvent]:
        return self._jobs.events(run_id, after_sequence=after_sequence)

    def recover_interrupted(self) -> int:
        return self._jobs.interrupt_unfinished()

    def close(self) -> None:
        self._executor.shutdown(wait=False, cancel_futures=False)

    def _execute(self, job: ConsultationJob) -> None:
        sink = RepositoryProgressSink(run_id=job.run_id, jobs=self._jobs)
        self._jobs.update(
            job.run_id,
            status=ConsultationJobStatus.RUNNING,
            current_stage="atlas_resolution",
        )
        try:
            self._advice.advise(
                job.case_id,
                repository_root=(
                    Path(job.repository_root) if job.repository_root is not None else None
                ),
                run_id=job.run_id,
                input_case_revision=job.input_case_revision,
                progress=sink,
            )
        except Exception as error:
            message = self._safe_error(error)
            try:
                run = self._runs.get(job.run_id)
            except Exception:
                run = None
            if run is not None and run.status == ConsultationStatus.SUCCEEDED:
                self._jobs.update(
                    job.run_id,
                    status=ConsultationJobStatus.SUCCEEDED_WITH_WARNINGS,
                    current_stage="report_writing",
                    warning=message,
                )
                self._jobs.append_event(
                    job.run_id,
                    event_type=ProgressEventType.WARNING,
                    stage="report_writing",
                    title="Report file export failed",
                    summary=(
                        "The validated report remains available from the local database. "
                        f"{message}"
                    ),
                )
                return
            if run is not None and run.sanitized_errors:
                message = run.sanitized_errors[0]
            self._jobs.update(
                job.run_id,
                status=ConsultationJobStatus.FAILED,
                current_stage=self._jobs.get(job.run_id).current_stage,
                error=message,
            )
            events = self._jobs.events(job.run_id)
            if not events or events[-1].event_type != ProgressEventType.FAILED:
                self._jobs.append_event(
                    job.run_id,
                    event_type=ProgressEventType.FAILED,
                    stage=self._jobs.get(job.run_id).current_stage,
                    title="Consultation failed",
                    summary=message,
                )
            return
        self._jobs.update(
            job.run_id,
            status=ConsultationJobStatus.SUCCEEDED,
            current_stage="commit",
        )

    @staticmethod
    def _safe_error(error: Exception) -> str:
        message = " ".join(str(error).split())
        return f"{type(error).__name__}: {message or 'operation failed'}"
