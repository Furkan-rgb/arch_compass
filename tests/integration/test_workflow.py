from __future__ import annotations

from pathlib import Path

from archcompass.domain.case import (
    ArchitectureCase,
    CaseStatement,
    StatementKind,
)
from archcompass.domain.consultation import ConsultationStatus


def _case(*, brownfield: bool = False) -> ArchitectureCase:
    return ArchitectureCase(
        title="Brownfield provider leakage" if brownfield else "Greenfield audiobook",
        problem_statement=(
            "Qwen-specific built-in voice logic is spread across modules."
            if brownfield
            else "Build an audiobook system with Qwen TTS and possible hosted providers."
        ),
        desired_outcome="Choose stable responsibilities without a universal plugin platform.",
        functional_requirements=["Book ingestion", "Narration", "Voice cloning"],
        quality_attributes=["Long-running resumable jobs"],
        technical_constraints=["One local GPU"],
        expected_future_changes=["Hosted providers may be added later"],
        confirmed_facts=[
            CaseStatement(
                text="Qwen is the initial provider",
                kind=StatementKind.FACT,
            )
        ],
    )


def test_greenfield_workflow_never_requires_atlas(runtime) -> None:
    runtime.policy_store.rebuild([Path("policies/general").resolve()])
    revision = runtime.case_service.create(_case())
    run = runtime.workflow.advise(revision.case_id)
    assert run.status == ConsultationStatus.SUCCEEDED
    assert run.atlas_version_id is None
    assert run.query_plans == []
    assert run.report is not None
    assert "provider" in run.report.recommended_architecture.casefold()
    assert runtime.case_service.show(revision.case_id).revision == 2


def test_brownfield_workflow_uses_focused_packets_not_raw_atlas(runtime) -> None:
    runtime.policy_store.rebuild([Path("policies/general").resolve()])
    atlas = runtime.analyzer.analyze(Path("tests/fixtures/provider_leakage").resolve())
    runtime.atlas_repository.save(atlas)
    revision = runtime.case_service.create(_case(brownfield=True))
    run = runtime.workflow.advise(revision.case_id, atlas=atlas)
    assert run.status == ConsultationStatus.SUCCEEDED
    assert run.focused_packets
    assert all(packet.query_results for packet in run.focused_packets)
    serialized = run.model_dump_json()
    assert '"nodes":' not in serialized
    assert run.report is not None
    assert run.report.repository_observations

