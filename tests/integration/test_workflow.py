from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from archcompass.bootstrap import BUNDLED_POLICY_SOURCE, build_runtime
from archcompass.domain.case import (
    ArchitectureCase,
    CaseStatement,
    StatementKind,
)
from archcompass.domain.consultation import ConsultationStatus
from archcompass.domain.errors import PolicyFormatError


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
    assert runtime.policy_store.current_version() is None
    revision = runtime.case_service.create(_case())
    run = runtime.workflow.advise(revision.case_id)
    assert run.status == ConsultationStatus.SUCCEEDED
    assert run.atlas_version_id is None
    assert run.query_plans == []
    assert run.policy_index_version_id is not None
    assert run.execution_metadata["retrieved_policies"] == 6
    assert run.report is not None
    assert "provider" in run.report.recommended_architecture.casefold()
    assert runtime.case_service.show(revision.case_id).revision == 2


def test_brownfield_workflow_uses_focused_packets_not_raw_atlas(runtime) -> None:
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


def test_brownfield_preflight_includes_repository_policies(
    runtime,
    tmp_path: Path,
) -> None:
    repository = tmp_path / "repository"
    shutil.copytree(Path("tests/fixtures/provider_leakage"), repository)
    local_policies = repository / ".archcompass" / "policies"
    local_policies.mkdir(parents=True)
    bundled = (BUNDLED_POLICY_SOURCE / "contain-dependencies.md").read_text(
        encoding="utf-8"
    )
    (local_policies / "repository-dependency-policy.md").write_text(
        bundled.replace(
            "id: contain-dependencies",
            "id: repository-dependency-policy",
            1,
        ).replace("scope: general", "scope: repository", 1),
        encoding="utf-8",
    )
    atlas = runtime.analyzer.analyze(repository)
    revision = runtime.case_service.create(_case(brownfield=True))

    run = runtime.workflow.advise(revision.case_id, atlas=atlas)

    assert run.policy_index_version_id is not None
    policies = runtime.policy_store.list_policies(run.policy_index_version_id)
    assert len(policies) == 16
    assert any(policy.id == "repository-dependency-policy" for policy in policies)


def test_policy_preflight_fails_before_reasoning(
    tmp_path: Path,
    fake_config_text: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workspace = tmp_path / "workspace"
    config_path = workspace / "config" / "models.yaml"
    config_path.parent.mkdir(parents=True)
    config_path.write_text(fake_config_text, encoding="utf-8")
    runtime = build_runtime(
        workspace,
        policy_sources=[tmp_path / "missing-policies"],
    )
    revision = runtime.case_service.create(_case())

    def unexpected_reasoning(*args: object, **kwargs: object) -> None:
        pytest.fail("reasoning must not start before policy preflight succeeds")

    monkeypatch.setattr(
        runtime.workflow._reasoning,
        "discover_design_forces",
        unexpected_reasoning,
    )

    with pytest.raises(PolicyFormatError, match="found no policy documents"):
        runtime.workflow.advise(revision.case_id)
