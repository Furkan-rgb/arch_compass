"""Stage sequencing and progress reporting for the consultation workflow.

The workflow announces each stage, publishes the artifact it produced, and marks the
stage complete. Written inline that is four statements per stage wrapped around one
line of actual work, which buries the pipeline in its own instrumentation, and the
"which stage is running" marker used by failure reporting has to be kept in step by
hand at every step.

This keeps the three events and the marker together, so a stage reads as one block and
cannot announce one stage while recording a failure against another.
"""

from __future__ import annotations

from typing import cast

from pydantic import JsonValue

from archcompass.domain.consultation import ConsultationFailureStage
from archcompass.domain.execution import ProgressEventType
from archcompass.ports.progress import ConsultationProgressSink


class StageProgress:
    """Emits one consultation's progress events and tracks the running stage."""

    def __init__(self, sink: ConsultationProgressSink | None) -> None:
        self._sink = sink
        #: The stage a failure would be attributed to. Advanced by `stage()` only, so
        #: it cannot drift from what was announced.
        self.current = ConsultationFailureStage.ATLAS_RESOLUTION

    def begin(self, stage: ConsultationFailureStage, title: str) -> None:
        """Enter a stage. A later failure is attributed here until the next `begin`."""

        self.current = stage
        self._emit(ProgressEventType.STAGE_STARTED, stage, title)

    def finish(self, title: str) -> None:
        """Mark the running stage complete."""

        self._emit(ProgressEventType.STAGE_COMPLETED, self.current, title)

    def artifact(
        self,
        title: str,
        summary: str,
        data: dict[str, object] | None = None,
    ) -> None:
        """Publish what the running stage produced."""

        self._emit(
            ProgressEventType.ARTIFACT_AVAILABLE,
            self.current,
            title,
            summary=summary,
            data=cast("dict[str, JsonValue]", data or {}),
        )

    def completed(
        self,
        title: str,
        summary: str,
        data: dict[str, object] | None = None,
    ) -> None:
        """Announce that the consultation itself finished."""

        self._emit(
            ProgressEventType.COMPLETED,
            self.current,
            title,
            summary=summary,
            data=cast("dict[str, JsonValue]", data or {}),
        )

    def failed(self, summary: str, data: dict[str, object] | None = None) -> None:
        """Announce that the consultation failed in the running stage."""

        self._emit(
            ProgressEventType.FAILED,
            self.current,
            "Consultation failed",
            summary=summary,
            data=cast("dict[str, JsonValue]", data or {}),
        )

    def _emit(
        self,
        event_type: ProgressEventType,
        stage: ConsultationFailureStage,
        title: str,
        *,
        summary: str = "",
        data: dict[str, JsonValue] | None = None,
    ) -> None:
        if self._sink is None:
            return
        self._sink.emit(
            event_type=event_type,
            stage=stage,
            title=title,
            summary=summary,
            data=data,
        )
