from pathlib import Path

import pytest
import yaml

from archcompass.bootstrap import Runtime
from archcompass.domain.case import ArchitectureCase
from archcompass.domain.consultation import (
    ConsultationRun,
    RecommendationDisposition,
)


def _advise_case(
    runtime: Runtime,
    case_path: str,
    *,
    repository_path: str | None = None,
) -> ConsultationRun:
    data = yaml.safe_load(Path(case_path).read_text(encoding="utf-8"))
    revision = runtime.case_service.create(ArchitectureCase.model_validate(data))
    if repository_path is None:
        return runtime.workflow.advise(revision.case_id)
    atlas = runtime.analyzer.analyze(Path(repository_path).resolve())
    runtime.atlas_repository.save(atlas)
    return runtime.workflow.advise(
        revision.case_id,
        atlas_version_id=atlas.version.version_id,
    )


@pytest.mark.evaluation
def test_audiobook_stays_greenfield_and_provider_owned(runtime: Runtime) -> None:
    run = _advise_case(runtime, "eval/cases/audiobook-greenfield/case.yaml")

    assert run.atlas_version_id is None
    assert run.query_plans == []
    assert run.execution_metadata["atlas_queries"] == 0
    assert run.report is not None
    report = run.report
    assert report.disposition == RecommendationDisposition.MOVE_RESPONSIBILITY
    architecture = report.recommended_architecture.text.casefold()
    assert "stable workflow boundaries" in architecture
    assert "each provider owns" in architecture
    assert "do not build a universal plugin platform" in architecture
    assert any(
        "provider adapter owns voice discovery" in item.text.casefold()
        for item in report.responsibility_allocation
    )


@pytest.mark.evaluation
def test_provider_leakage_moves_discovery_with_located_evidence(
    runtime: Runtime,
) -> None:
    run = _advise_case(
        runtime,
        "eval/cases/provider-leakage/case.yaml",
        repository_path="eval/cases/provider-leakage/repository",
    )

    assert run.report is not None
    report = run.report
    assert report.disposition == RecommendationDisposition.MOVE_RESPONSIBILITY
    assert report.repository_observations
    assert all(
        reference.location is not None
        for claim in report.repository_observations
        for reference in claim.atlas_references
    )
    assert any(
        "duplicated ownership" in claim.text.casefold()
        and "coordinated provider changes" in claim.text.casefold()
        for claim in report.repository_observations
    )
    assert "provider changes remain within one adapter" in (
        report.change_amplification_analysis.text.casefold()
    )
    assert any(
        "provider adapter owns voice discovery" in item.text.casefold()
        for item in report.responsibility_allocation
    )
    cited_policy_ids = {
        policy_id for claim in report.relevant_policies for policy_id in claim.policy_ids
    }
    assert cited_policy_ids
    assert cited_policy_ids <= {item.id for item in report.policy_evidence}


@pytest.mark.evaluation
def test_premature_abstraction_keeps_the_single_implementation_local(
    runtime: Runtime,
) -> None:
    run = _advise_case(
        runtime,
        "eval/cases/premature-abstraction/case.yaml",
        repository_path="eval/cases/premature-abstraction/repository",
    )

    assert run.report is not None
    report = run.report
    assert report.disposition == RecommendationDisposition.KEEP_LOCAL
    assert "keep the implementation local" in report.recommended_architecture.text.casefold()
    assert "without containing credible variation" in (
        report.recommended_architecture.text.casefold()
    )
    assert report.conceptual_interfaces == []
    implementation = " ".join(
        item.text.casefold() for item in report.implementation_sequence
    )
    assert "retain the direct local formatter" in implementation
    assert "do not add an interface, factory, registry, or configuration key" in implementation
    assert report.repository_observations
    assert all(
        reference.location is not None
        for claim in report.repository_observations
        for reference in claim.atlas_references
    )
