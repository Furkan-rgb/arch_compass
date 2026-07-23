from __future__ import annotations

import math
from pathlib import Path

import pytest
import yaml

from archcompass.adapters.models.ollama import OllamaEmbeddingProvider
from archcompass.bootstrap import build_runtime
from archcompass.configuration import AppConfig, load_config
from archcompass.domain.case import ArchitectureCase
from archcompass.domain.consultation import ConsultationStatus

pytestmark = pytest.mark.ollama


@pytest.fixture(scope="module")
def live_config_path() -> Path:
    return Path("config/models.yaml").resolve()


@pytest.fixture(scope="module")
def live_config(live_config_path: Path) -> AppConfig:
    config = load_config(live_config_path)
    assert config.models.reasoning.provider == "ollama"
    assert config.models.embedding.provider == "ollama"
    return config


def test_live_embedding_model_contract(live_config: AppConfig) -> None:
    provider = OllamaEmbeddingProvider(live_config.models.embedding)

    vectors = provider.embed(
        [
            "Keep provider-specific capabilities behind the provider boundary.",
            "Avoid an abstraction until credible variation exists.",
        ]
    )

    assert len(vectors) == 2
    assert all(len(vector) == live_config.models.embedding.dimensions for vector in vectors)
    assert all(math.isfinite(value) for vector in vectors for value in vector)
    assert all(any(value != 0 for value in vector) for vector in vectors)
    assert vectors[0] != vectors[1]


def test_live_audiobook_greenfield_consultation(
    tmp_path: Path,
    live_config_path: Path,
) -> None:
    runtime = build_runtime(tmp_path, models_config=live_config_path)
    assert runtime.policy_store.current_version() is None
    case_data = yaml.safe_load(
        Path("eval/cases/audiobook-greenfield/case.yaml").read_text(encoding="utf-8")
    )
    revision = runtime.case_service.create(ArchitectureCase.model_validate(case_data))

    run = runtime.workflow.advise(revision.case_id)
    policy_version = runtime.policy_store.current_version()

    assert run.status == ConsultationStatus.SUCCEEDED
    assert policy_version is not None
    assert run.reasoning_model == f"ollama:{runtime.config.models.reasoning.model}"
    assert run.embedding_model == policy_version.embedding_model
    assert run.policy_index_version_id == policy_version.version_id
    assert run.atlas_version_id is None
    assert run.query_plans == []
    assert run.design_forces
    assert run.focused_packets
    assert run.alternatives
    assert run.scenarios
    assert run.validation_errors == []
    assert run.report is not None
    assert run.report.decision_summary
    assert run.report.recommended_architecture
    assert run.report.alternatives_considered
    assert run.report.trade_offs
    assert run.report.implementation_sequence
    assert run.report.adr.decision
    assert run.markdown_report is not None
    assert run.report.adr.title in run.markdown_report
    assert {
        "policy_preflight",
        "discover_design_forces",
        "cluster_design_forces",
        "generate_alternatives",
        "evaluate_scenarios",
        "synthesize_recommendation",
        "rendering",
    } <= set(run.stage_timings)
    assert all(duration >= 0 for duration in run.stage_timings.values())
    assert runtime.case_service.show(revision.case_id).revision == 2
