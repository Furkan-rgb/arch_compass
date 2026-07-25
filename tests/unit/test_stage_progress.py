from __future__ import annotations

from pydantic import JsonValue

from archcompass.domain.consultation import ConsultationFailureStage
from archcompass.domain.execution import ConsultationProgressEvent, ProgressEventType
from archcompass.workflows.stage_progress import StageProgress


class _RecordingSink:
    def __init__(self) -> None:
        self.events: list[tuple[ProgressEventType, str | None, str]] = []

    def emit(
        self,
        *,
        event_type: ProgressEventType,
        stage: str | None,
        title: str,
        summary: str = "",
        data: dict[str, JsonValue] | None = None,
    ) -> ConsultationProgressEvent:
        del summary, data
        self.events.append((event_type, stage, title))
        return ConsultationProgressEvent(
            run_id="run-test",
            sequence=len(self.events),
            event_type=event_type,
            stage=stage,
            title=title,
        )


def test_a_failure_is_attributed_to_the_stage_that_was_announced() -> None:
    """The marker advances only with the announcement, so the two cannot diverge.

    Keeping a separate `current_stage` local in step with each progress call was
    manual, and a missed update would report a failure against the previous stage.
    """

    sink = _RecordingSink()
    progress = StageProgress(sink)

    progress.begin(ConsultationFailureStage.POLICY, "Preparing policies")
    progress.finish("Policies prepared")
    progress.begin(ConsultationFailureStage.SYNTHESIS, "Synthesizing")
    progress.failed("Synthesis failed")

    assert progress.current is ConsultationFailureStage.SYNTHESIS
    assert sink.events == [
        (ProgressEventType.STAGE_STARTED, ConsultationFailureStage.POLICY, "Preparing policies"),
        (ProgressEventType.STAGE_COMPLETED, ConsultationFailureStage.POLICY, "Policies prepared"),
        (ProgressEventType.STAGE_STARTED, ConsultationFailureStage.SYNTHESIS, "Synthesizing"),
        (ProgressEventType.FAILED, ConsultationFailureStage.SYNTHESIS, "Consultation failed"),
    ]


def test_an_artifact_belongs_to_the_running_stage() -> None:
    sink = _RecordingSink()
    progress = StageProgress(sink)

    progress.begin(ConsultationFailureStage.ALTERNATIVES, "Generating alternatives")
    progress.artifact("Alternatives generated", "Two options.", {"count": 2})

    assert sink.events[-1] == (
        ProgressEventType.ARTIFACT_AVAILABLE,
        ConsultationFailureStage.ALTERNATIVES,
        "Alternatives generated",
    )


def test_progress_without_a_sink_is_still_tracked() -> None:
    """A run with no progress sink must still attribute its failure correctly."""

    progress = StageProgress(None)

    progress.begin(ConsultationFailureStage.VALIDATION, "Validating")
    progress.artifact("ignored", "ignored")
    progress.failed("no sink attached")

    assert progress.current is ConsultationFailureStage.VALIDATION
