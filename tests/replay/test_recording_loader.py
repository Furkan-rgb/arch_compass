"""The recording harness must work before any recording exists.

`test_recorded_synthesis.py` skips until someone captures against a live model, which
would leave the loader and its staleness check unexercised — the "green suite, dead
coverage" shape this project has already been bitten by. These tests build synthetic
bundles on disk so the machinery is proven deterministically.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from archcompass.adapters.models.prompt_contracts import OLLAMA_STAGE_PROMPTS
from archcompass.ports.reasoning import ReasoningTask
from tests.replay.recorded import FORMAT_VERSION, Recording

_SYNTHESIS = ReasoningTask.SYNTHESIZE_RECOMMENDATION


def _bundle(
    root: Path,
    *,
    prompt_identity: str | None = None,
    format_version: int = FORMAT_VERSION,
) -> Path:
    directory = root / "sample"
    (directory / "responses").mkdir(parents=True)
    (directory / "responses" / "01-synthesize_recommendation.txt").write_text(
        '{"disposition": "keep_local"}', encoding="utf-8"
    )
    (directory / "manifest.json").write_text(
        json.dumps(
            {
                "format_version": format_version,
                "case_name": "sample-case",
                "run_id": "run-1",
                "case_id": "case-1",
                "case_revision": 1,
                "atlas_version_id": None,
                "policy_index_version_id": "policy-1",
                "reasoning_model": "ollama:test-model",
                "config_hash": "cfg-1",
                "calls": [
                    {
                        "ordinal": 1,
                        "task": _SYNTHESIS.value,
                        "prompt_identity": (
                            prompt_identity or OLLAMA_STAGE_PROMPTS[_SYNTHESIS].identity
                        ),
                        "response_file": "01-synthesize_recommendation.txt",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    (directory / "inputs.json").write_text(
        json.dumps(
            {
                "case": {
                    "schema_version": 2,
                    "case_id": "case-1",
                    "title": "Sample",
                    "problem_statement": "A problem",
                    "desired_outcome": "An outcome",
                },
                "clusters": [],
                "concern_analyses": [],
                "design_forces": [],
                "alternatives": [],
                "scenarios": [],
                "focused_packets": [],
                "allowed_nodes": [],
            }
        ),
        encoding="utf-8",
    )
    return directory


def test_a_current_recording_reports_no_stale_prompts(tmp_path: Path) -> None:
    recording = Recording(_bundle(tmp_path))

    assert recording.stale_prompts() == []
    assert recording.response(_SYNTHESIS) == '{"disposition": "keep_local"}'
    assert recording.case().title == "Sample"


def test_a_changed_prompt_makes_its_recording_stale(tmp_path: Path) -> None:
    """The staleness mechanism, proven without needing a real prompt edit.

    A recording captured under a different prompt identity must be reported, because
    the answer it holds was produced under wording that no longer exists.
    """

    recording = Recording(
        _bundle(tmp_path, prompt_identity="synthesize-recommendation:v1:deadbeef1234")
    )

    stale = recording.stale_prompts()

    assert len(stale) == 1
    assert "synthesize_recommendation" in stale[0]
    assert "deadbeef1234" in stale[0]


def test_an_unknown_bundle_format_refuses_to_load(tmp_path: Path) -> None:
    """A bundle from a future or past layout fails loudly rather than half-decoding."""

    with pytest.raises(ValueError, match="format version"):
        Recording(_bundle(tmp_path, format_version=FORMAT_VERSION + 1))


def test_a_manifest_with_unknown_fields_is_rejected(tmp_path: Path) -> None:
    directory = _bundle(tmp_path)
    manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
    manifest["invented_field"] = "value"
    (directory / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")

    with pytest.raises(ValueError):
        Recording(directory)


def test_asking_for_an_unrecorded_stage_raises(tmp_path: Path) -> None:
    recording = Recording(_bundle(tmp_path))

    with pytest.raises(LookupError, match="analyze_concern_cluster"):
        recording.response(ReasoningTask.ANALYZE_CONCERN_CLUSTER)
