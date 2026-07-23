from pathlib import Path

import pytest
import yaml

from archcompass.domain.case import ArchitectureCase


@pytest.mark.evaluation
@pytest.mark.parametrize(
    ("case_path", "expected"),
    [
        ("eval/cases/audiobook-greenfield/case.yaml", "provider"),
        ("eval/cases/provider-leakage/case.yaml", "provider"),
        ("eval/cases/premature-abstraction/case.yaml", "local"),
    ],
)
def test_deterministic_evaluation_cases(runtime, case_path: str, expected: str) -> None:
    data = yaml.safe_load(Path(case_path).read_text(encoding="utf-8"))
    revision = runtime.case_service.create(ArchitectureCase.model_validate(data))
    atlas = None
    if "provider-leakage" in case_path:
        atlas = runtime.analyzer.analyze(Path("tests/fixtures/provider_leakage").resolve())
    run = runtime.workflow.advise(revision.case_id, atlas=atlas)
    assert run.report is not None
    assert expected in run.report.recommended_architecture.casefold()
    assert all(
        reference.node_id
        for claim in run.report.evidence_appendix
        for reference in claim.atlas_references
    )
