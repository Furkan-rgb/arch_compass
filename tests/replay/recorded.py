"""Load recording bundles captured from live consultations.

A bundle is the transcript of one real consultation: the inputs each reasoning stage
received and the raw text the model answered with. Replaying an answer through the real
validation and composition code proves that code still accepts what a real model
actually produces — which hand-authored fixtures cannot, because they are written by
someone who already knows what the code expects.

Loading is strict, for the same reason stored records are: a bundle that no longer
matches the current models must fail loudly rather than decode into something plausible.
"""

from __future__ import annotations

import json
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from archcompass.adapters.models.prompt_contracts import OLLAMA_STAGE_PROMPTS
from archcompass.domain.atlas import AtlasNode
from archcompass.domain.case import ArchitectureCase, CaseAlternative
from archcompass.domain.consultation import (
    ConcernAnalysis,
    ConcernCluster,
    DesignForce,
    FocusedAnalysisPacket,
    ScenarioEvaluation,
)
from archcompass.ports.reasoning import ReasoningTask

RECORDING_ROOT = Path(__file__).parent / "recordings"
FORMAT_VERSION = 1


class RecordedCall(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    ordinal: int = Field(ge=1)
    task: ReasoningTask
    prompt_identity: str = Field(min_length=1)
    response_file: str = Field(min_length=1)


class RecordingManifest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    format_version: int
    case_name: str
    run_id: str
    case_id: str
    case_revision: int = Field(ge=1)
    atlas_version_id: str | None = None
    policy_index_version_id: str | None = None
    reasoning_model: str
    config_hash: str
    calls: list[RecordedCall] = Field(min_length=1)


class Recording:
    """One captured consultation, replayable without a model."""

    def __init__(self, directory: Path) -> None:
        self.directory = directory
        self.manifest = RecordingManifest.model_validate_json(
            (directory / "manifest.json").read_text(encoding="utf-8")
        )
        if self.manifest.format_version != FORMAT_VERSION:
            raise ValueError(
                f"Recording {directory.name} uses format version "
                f"{self.manifest.format_version}; this checkout expects {FORMAT_VERSION}. "
                "Re-capture it with `make capture-recordings`."
            )
        self._inputs = json.loads((directory / "inputs.json").read_text(encoding="utf-8"))

    @property
    def name(self) -> str:
        return self.directory.name

    def stale_prompts(self) -> list[str]:
        """Stages whose prompt has changed since this recording was captured.

        Prompt identities embed a content fingerprint, so any edit to a stage's system
        prompt or request text changes its identity. A recorded answer was produced
        under the old wording and is no longer evidence about the current one.
        """

        stale: list[str] = []
        for call in self.manifest.calls:
            current = OLLAMA_STAGE_PROMPTS[call.task].identity
            if current != call.prompt_identity:
                stale.append(
                    f"{call.task.value}: recorded under {call.prompt_identity}, "
                    f"now {current}"
                )
        return sorted(set(stale))

    def response(self, task: ReasoningTask) -> str:
        """The last raw answer the model gave for one stage."""

        for call in reversed(self.manifest.calls):
            if call.task is task:
                return (self.directory / "responses" / call.response_file).read_text(
                    encoding="utf-8"
                )
        raise LookupError(f"Recording {self.name} has no {task.value} call")

    def case(self) -> ArchitectureCase:
        return ArchitectureCase.model_validate(self._inputs["case"])

    def clusters(self) -> list[ConcernCluster]:
        return [ConcernCluster.model_validate(item) for item in self._inputs["clusters"]]

    def analyses(self) -> list[ConcernAnalysis]:
        return [
            ConcernAnalysis.model_validate(item) for item in self._inputs["concern_analyses"]
        ]

    def design_forces(self) -> list[DesignForce]:
        return [DesignForce.model_validate(item) for item in self._inputs["design_forces"]]

    def alternatives(self) -> list[CaseAlternative]:
        return [CaseAlternative.model_validate(item) for item in self._inputs["alternatives"]]

    def scenarios(self) -> list[ScenarioEvaluation]:
        return [ScenarioEvaluation.model_validate(item) for item in self._inputs["scenarios"]]

    def allowed_nodes(self) -> dict[str, AtlasNode]:
        """The node allowlist evidence validation used during the recorded run."""

        return {
            node.atlas_id: node
            for node in (
                AtlasNode.model_validate(item)
                for item in self._inputs.get("allowed_nodes", [])
            )
        }

    def packets(self) -> list[FocusedAnalysisPacket]:
        return [
            FocusedAnalysisPacket.model_validate(item)
            for item in self._inputs["focused_packets"]
        ]


def available_recordings() -> list[Recording]:
    """Every committed recording bundle, or an empty list when none are captured."""

    if not RECORDING_ROOT.is_dir():
        return []
    return [
        Recording(entry)
        for entry in sorted(RECORDING_ROOT.iterdir())
        if entry.is_dir() and (entry / "manifest.json").is_file()
    ]
