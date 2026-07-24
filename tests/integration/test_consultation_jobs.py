from __future__ import annotations

from pathlib import Path
from time import monotonic, sleep

import yaml

from archcompass.bootstrap import Runtime
from archcompass.domain.case import ArchitectureCase
from archcompass.domain.execution import (
    ConsultationJob,
    ConsultationJobStatus,
    ProgressEventType,
)


def test_consultation_job_persists_replayable_structured_progress(
    runtime: Runtime,
) -> None:
    source = yaml.safe_load(
        Path("eval/cases/audiobook-greenfield/case.yaml").read_text(encoding="utf-8")
    )
    revision = runtime.case_service.create(ArchitectureCase.model_validate(source))

    try:
        queued = runtime.job_service.start(revision.case_id)
        deadline = monotonic() + 5
        job = queued
        while (
            job.status in {ConsultationJobStatus.QUEUED, ConsultationJobStatus.RUNNING}
            and monotonic() < deadline
        ):
            sleep(0.01)
            job = runtime.job_service.get(queued.run_id)

        events = runtime.job_service.events(queued.run_id)

        assert job.status == ConsultationJobStatus.SUCCEEDED
        assert events[0].event_type == ProgressEventType.QUEUED
        assert events[-1].event_type == ProgressEventType.COMPLETED
        assert [event.sequence for event in events] == list(
            range(1, len(events) + 1)
        )
        force_event = next(
            event
            for event in events
            if event.event_type == ProgressEventType.ARTIFACT_AVAILABLE
            and event.stage == "design_forces"
        )
        assert force_event.data["design_forces"]
        assert "prompt" not in force_event.data
        assert runtime.run_service.show(queued.run_id).report is not None
    finally:
        runtime.job_service.close()


def test_unfinished_jobs_are_marked_interrupted_after_restart(
    runtime: Runtime,
) -> None:
    source = yaml.safe_load(
        Path("eval/cases/audiobook-greenfield/case.yaml").read_text(encoding="utf-8")
    )
    revision = runtime.case_service.create(ArchitectureCase.model_validate(source))
    job = runtime.job_repository.create(
        ConsultationJob(
            run_id="run_unfinished_fixture",
            case_id=revision.case_id,
            input_case_revision=revision.revision,
        )
    )

    interrupted = runtime.job_repository.interrupt_unfinished()

    assert interrupted >= 1
    assert (
        runtime.job_repository.get(job.run_id).status
        == ConsultationJobStatus.INTERRUPTED
    )
    runtime.job_service.close()
