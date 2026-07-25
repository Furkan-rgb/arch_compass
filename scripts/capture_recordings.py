"""Capture one live consultation as a replayable recording bundle.

A recording is the exact transcript of what a real model was asked and what it
answered, captured from the wire during a real consultation. Tests then replay those
answers through the real validation and composition code with no model running, so a
pipeline regression is caught in the default suite in milliseconds instead of needing
a live run.

Why record rather than reconstruct: a stage input could in principle be rebuilt from a
stored run's pins, but `atlas_overview()` carries its own caps and limitation prose, so
a rebuilt context would silently follow later edits to that code. A fixture that tracks
your changes cannot detect them. The recorded bytes are what the model actually saw.

Requires a running Ollama and a workspace configured to use it:

    make capture-recordings CASE=eval/cases/provider-leakage NAME=provider-leakage
"""

from __future__ import annotations

import argparse
import json
import shutil
import tempfile
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import yaml

from archcompass.adapters.models.ollama import OllamaReasoningProvider
from archcompass.bootstrap import build_runtime
from archcompass.domain.base import canonical_json
from archcompass.domain.case import ArchitectureCase
from archcompass.ports.reasoning import ReasoningTask
from archcompass.workflows.consultation import ConsultationWorkflow

RECORDING_ROOT = Path("tests/replay/recordings")
FORMAT_VERSION = 1


class _RecordingProvider(OllamaReasoningProvider):
    """A real Ollama provider that keeps every request and response it makes."""

    def __init__(self, config: Any) -> None:
        super().__init__(config)
        self.calls: list[dict[str, object]] = []

    def _chat(
        self,
        output_type: Any,
        messages: list[dict[str, str]],
        *,
        task: ReasoningTask,
        schema_override: Mapping[str, object] | None = None,
        think: bool | str | None = None,
        temperature: float | None = None,
    ) -> str:
        response = super()._chat(
            output_type,
            messages,
            task=task,
            schema_override=schema_override,
            think=think,
            temperature=temperature,
        )
        self.calls.append(
            {
                "ordinal": len(self.calls) + 1,
                "task": task.value,
                "prompt_identity": self.prompt_identity(task),
                "messages": messages,
                "response": response,
            }
        )
        return response


def _stage_input(calls: list[dict[str, object]], task: ReasoningTask) -> dict[str, object] | None:
    """The last request made for one stage, which is what a replay reproduces."""

    for call in reversed(calls):
        if call["task"] == task.value:
            return call
    return None


def capture(case_dir: Path, name: str, *, workspace: Path) -> Path:
    case_path = case_dir / "case.yaml"
    repository = case_dir / "repository"
    runtime = build_runtime(workspace)

    provider = runtime.config.models.reasoning
    if provider.provider != "ollama":
        raise SystemExit(
            "Capture needs a live model. Configure models.reasoning.provider: ollama "
            f"in the workspace configuration (found {provider.provider!r})."
        )

    recorder = _RecordingProvider(provider)
    runtime.workflow._reasoning = recorder

    data = yaml.safe_load(case_path.read_text(encoding="utf-8"))
    revision = runtime.case_service.create(ArchitectureCase.model_validate(data))
    atlas = None
    if repository.is_dir():
        atlas = runtime.analyzer.analyze(repository.resolve())
        runtime.atlas_repository.save(atlas)
        run = runtime.workflow.advise(
            revision.case_id, atlas_version_id=atlas.version.version_id
        )
    else:
        run = runtime.workflow.advise(revision.case_id)

    case = runtime.case_service.show(revision.case_id, run.input_case_revision).snapshot
    target = RECORDING_ROOT / name
    if target.exists():
        shutil.rmtree(target)
    (target / "responses").mkdir(parents=True)

    entries: list[dict[str, object]] = []
    for call in recorder.calls:
        filename = f"{call['ordinal']:02d}-{call['task']}.txt"
        (target / "responses" / filename).write_text(str(call["response"]), encoding="utf-8")
        entries.append(
            {
                "ordinal": call["ordinal"],
                "task": call["task"],
                "prompt_identity": call["prompt_identity"],
                "response_file": filename,
            }
        )

    synthesis = _stage_input(recorder.calls, ReasoningTask.SYNTHESIZE_RECOMMENDATION)
    if synthesis is None:
        raise SystemExit("The consultation made no synthesis call; nothing to replay.")

    (target / "manifest.json").write_text(
        json.dumps(
            {
                "format_version": FORMAT_VERSION,
                "case_name": case_dir.name,
                "run_id": run.run_id,
                "case_id": run.case_id,
                "case_revision": run.input_case_revision,
                "atlas_version_id": run.atlas_version_id,
                "policy_index_version_id": run.policy_index_version_id,
                "reasoning_model": run.reasoning_model,
                "config_hash": run.config_hash,
                "calls": entries,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    (target / "inputs.json").write_text(
        json.dumps(
            {
                "case": case.model_dump(mode="json"),
                "clusters": [item.model_dump(mode="json") for item in run.clusters],
                "concern_analyses": [
                    item.model_dump(mode="json") for item in run.concern_analyses
                ],
                "design_forces": [item.model_dump(mode="json") for item in run.design_forces],
                "alternatives": [item.model_dump(mode="json") for item in run.alternatives],
                "scenarios": [item.model_dump(mode="json") for item in run.scenarios],
                "focused_packets": [
                    item.model_dump(mode="json") for item in run.focused_packets
                ],
                # The exact node allowlist evidence validation used, so a replay
                # validates against what the run validated against rather than a
                # re-derivation that could drift from it.
                "allowed_nodes": [
                    node.model_dump(mode="json")
                    for node in ConsultationWorkflow._allowed_nodes(
                        atlas, run.focused_packets
                    ).values()
                ],
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return target


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case", required=True, help="Evaluation case directory")
    parser.add_argument("--name", required=True, help="Recording bundle name")
    parser.add_argument(
        "--workspace",
        default=None,
        help="Workspace to run in; a temporary one is used when omitted.",
    )
    args = parser.parse_args()

    workspace = Path(args.workspace) if args.workspace else Path(tempfile.mkdtemp())
    if args.workspace is None:
        config = workspace / "config"
        config.mkdir(parents=True, exist_ok=True)
        packaged = Path("config/models.yaml")
        if not packaged.is_file():
            raise SystemExit(
                "No workspace given and config/models.yaml is missing; "
                "pass --workspace pointing at a configured workspace."
            )
        (config / "models.yaml").write_text(
            packaged.read_text(encoding="utf-8"), encoding="utf-8"
        )

    target = capture(Path(args.case), args.name, workspace=workspace)
    manifest = json.loads((target / "manifest.json").read_text(encoding="utf-8"))
    print(f"Recorded {len(manifest['calls'])} model calls to {target}")
    print(f"Digest: {canonical_json(manifest)[:80]}…")


if __name__ == "__main__":
    main()
