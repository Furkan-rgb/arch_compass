from __future__ import annotations

import math
from pathlib import Path

import pytest
import yaml

from archcompass.adapters.models.ollama import (
    OllamaEmbeddingProvider,
    OllamaReasoningProvider,
)
from archcompass.bootstrap import build_runtime
from archcompass.configuration import AppConfig, load_config
from archcompass.domain.case import ArchitectureCase
from archcompass.domain.consultation import (
    ConsultationStatus,
    DesignForce,
    GlobalContext,
    cluster_partition_errors,
)

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


def test_live_clustering_maps_closed_set_references_to_canonical_ids(
    live_config: AppConfig,
) -> None:
    provider = OllamaReasoningProvider(live_config.models.reasoning)
    context = GlobalContext(
        case_id="case-live-clustering-contract",
        revision=1,
        title="Brownfield provider leakage",
        problem="Provider-specific voice knowledge is spread across several responsibilities.",
        desired_outcome="Give capability discovery one owner and contain provider changes.",
        goals=["Clear responsibility ownership", "Localized provider changes"],
        constraints=["Keep existing behavior"],
        future_changes=["A second provider may be added"],
        non_goals=["A universal plugin marketplace"],
        confirmed_facts=["A provider interface exists without capability discovery"],
        assumptions=[],
    )
    forces = [
        DesignForce(
            force_id="force_adea9fa4455d4439a3b215860cb0eec3",
            title="Provider-neutral ownership",
            description="Provider capability knowledge needs one clear owner.",
            importance="high",
        ),
        DesignForce(
            force_id="force_382d88fef7894aa39b2df88461652109",
            title="Resource lifecycle",
            description="Provider resources need explicit acquisition and cleanup ownership.",
            importance="high",
        ),
        DesignForce(
            force_id="force_9abd553fc67f4851b1619cebd450c8c8",
            title="Change locality",
            description="Adding a provider should not require coordinated changes everywhere.",
            importance="high",
        ),
        DesignForce(
            force_id="force_9bfef0aed0a441f7ac8b6ce77727f67a",
            title="Dependency spread",
            description="Existing provider knowledge crosses several application layers.",
            importance="high",
        ),
        DesignForce(
            force_id="force_e2a09841996a425c83787838ff8d20a1",
            title="Bounded extensibility",
            description="A credible second provider does not justify a universal plugin system.",
            importance="medium",
        ),
    ]

    clusters = provider.cluster_design_forces(context, forces)

    assert cluster_partition_errors(forces, clusters) == []
    assert {
        force_id
        for cluster in clusters
        for force_id in cluster.design_force_ids
    } == {force.force_id for force in forces}
    assert all(cluster.cluster_id.startswith("cluster_") for cluster in clusters)


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
