"""Composition root: the only place that selects concrete adapters."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from archcompass.adapters.models import (
    DeterministicEmbeddingProvider,
    DeterministicReasoningProvider,
    OllamaEmbeddingProvider,
    OllamaReasoningProvider,
)
from archcompass.adapters.persistence import (
    SQLiteAtlasRepository,
    SQLiteCaseRepository,
    SQLiteConsultationCommitRepository,
    SQLiteConsultationJobRepository,
    SQLiteDatabase,
    SQLitePolicySourceRepository,
    SQLiteRunRepository,
)
from archcompass.adapters.reporting import SafeWorkspaceReportWriter
from archcompass.adapters.repository import (
    DeterministicAtlasQueryService,
    PythonAstRepositoryAnalyzer,
    SafeSourceReader,
)
from archcompass.adapters.retrieval import (
    MarkdownPolicySourceInspector,
    SQLitePolicyStore,
)
from archcompass.application.advice import AdviceService
from archcompass.application.atlas import AtlasFreshnessService
from archcompass.application.atlas_queries import AtlasService
from archcompass.application.cases import CaseService
from archcompass.application.jobs import ConsultationJobService
from archcompass.application.policies import PolicyService
from archcompass.application.reports import ReportService
from archcompass.application.repositories import RepositoryIndexService
from archcompass.application.runs import RunService
from archcompass.application.safety import (
    validate_workspace_repository_separation,
)
from archcompass.application.workspace import WorkspaceConfigurationService
from archcompass.configuration import AppConfig, load_config, resolve_config_path
from archcompass.domain.errors import ConfigurationError
from archcompass.ports.models import EmbeddingProvider
from archcompass.ports.reasoning import FocusedReasoningProvider
from archcompass.workflows import ConsultationWorkflow

BUNDLED_POLICY_SOURCE = Path(__file__).resolve().parent / "policies" / "general"


@dataclass(frozen=True)
class Runtime:
    workspace: Path
    config: AppConfig
    database: SQLiteDatabase
    case_repository: SQLiteCaseRepository
    run_repository: SQLiteRunRepository
    job_repository: SQLiteConsultationJobRepository
    atlas_repository: SQLiteAtlasRepository
    analyzer: PythonAstRepositoryAnalyzer
    query_service: DeterministicAtlasQueryService
    policy_store: SQLitePolicyStore
    policy_sources: tuple[Path, ...]
    case_service: CaseService
    workflow: ConsultationWorkflow
    policy_service: PolicyService
    repository_service: RepositoryIndexService
    atlas_service: AtlasService
    advice_service: AdviceService
    report_service: ReportService
    run_service: RunService
    job_service: ConsultationJobService
    freshness_service: AtlasFreshnessService


@dataclass(frozen=True)
class WorkspaceInitialization:
    runtime: Runtime
    created_paths: tuple[Path, ...]


def build_runtime(
    workspace: Path,
    *,
    models_config: Path | None = None,
    policy_sources: list[Path] | None = None,
    repository: Path | None = None,
    initialize: bool = True,
) -> Runtime:
    canonical_workspace = workspace.expanduser().resolve()
    if repository is not None:
        validate_workspace_repository_separation(canonical_workspace, repository)
    config = load_config(resolve_config_path(canonical_workspace, models_config))
    canonical_workspace.mkdir(parents=True, exist_ok=True)
    database = SQLiteDatabase(
        canonical_workspace / ".archcompass" / "archcompass.db",
        workspace=canonical_workspace,
    )
    if initialize:
        database.initialize()
    embeddings = _embedding_provider(config)
    reasoning = _reasoning_provider(config)
    cases = SQLiteCaseRepository(database)
    runs = SQLiteRunRepository(database)
    jobs = SQLiteConsultationJobRepository(database)
    atlases = SQLiteAtlasRepository(database)
    analyzer = PythonAstRepositoryAnalyzer()
    freshness = AtlasFreshnessService(analyzer)
    source_reader = SafeSourceReader()
    queries = DeterministicAtlasQueryService(source_reader, freshness)
    policies = SQLitePolicyStore(
        database,
        embeddings,
        max_sections_per_policy=config.retrieval.max_sections_per_policy,
    )
    configured_policy_sources = tuple(
        source.expanduser().resolve(strict=False)
        for source in (
            policy_sources
            if policy_sources is not None
            else [BUNDLED_POLICY_SOURCE]
        )
    )
    policy_service = PolicyService(
        index=policies,
        source_repository=SQLitePolicySourceRepository(database),
        source_inspector=MarkdownPolicySourceInspector(),
        bundled_sources=configured_policy_sources,
    )
    commits = SQLiteConsultationCommitRepository(database)
    workflow = ConsultationWorkflow(
        config=config,
        cases=cases,
        runs=runs,
        commits=commits,
        atlases=atlases,
        queries=queries,
        policy_index=policies,
        policies=policies,
        reasoning=reasoning,
        policy_sources=configured_policy_sources,
        policy_source_resolver=lambda root: policy_service.effective_sources(
            repository_root=root
        ),
        repository_validator=lambda root: validate_workspace_repository_separation(
            canonical_workspace,
            root,
        ),
        freshness=freshness,
    )
    case_service = CaseService(cases)
    report_service = ReportService(SafeWorkspaceReportWriter(canonical_workspace))
    repository_service = RepositoryIndexService(
        workspace=canonical_workspace,
        analyzer=analyzer,
        atlases=atlases,
    )
    atlas_service = AtlasService(
        atlases=atlases,
        queries=queries,
        freshness=freshness,
    )
    advice_service = AdviceService(
        consultation=workflow,
        reports=report_service,
    )
    job_service = ConsultationJobService(
        cases=cases,
        runs=runs,
        jobs=jobs,
        advice=advice_service,
    )
    return Runtime(
        workspace=canonical_workspace,
        config=config,
        database=database,
        case_repository=cases,
        run_repository=runs,
        job_repository=jobs,
        atlas_repository=atlases,
        analyzer=analyzer,
        query_service=queries,
        policy_store=policies,
        policy_sources=configured_policy_sources,
        case_service=case_service,
        workflow=workflow,
        policy_service=policy_service,
        repository_service=repository_service,
        atlas_service=atlas_service,
        advice_service=advice_service,
        report_service=report_service,
        run_service=RunService(runs),
        job_service=job_service,
        freshness_service=freshness,
    )


def initialize_workspace(
    workspace: Path,
    *,
    models_config: Path | None = None,
) -> WorkspaceInitialization:
    canonical_workspace = workspace.expanduser().resolve()
    config_path = resolve_config_path(canonical_workspace, models_config)
    external_config = models_config is not None or bool(
        os.environ.get("ARCHCOMPASS_MODELS_CONFIG")
    )
    initialization_target = (
        config_path
        if external_config
        else canonical_workspace / "config" / "models.yaml"
    )
    created = WorkspaceConfigurationService().initialize(
        canonical_workspace,
        initialization_target,
        allow_external_config=external_config,
    )
    runtime = build_runtime(
        canonical_workspace,
        models_config=config_path,
    )
    return WorkspaceInitialization(runtime=runtime, created_paths=tuple(created))


def _embedding_provider(config: AppConfig) -> EmbeddingProvider:
    model = config.models.embedding
    if model.provider == "ollama":
        return OllamaEmbeddingProvider(model)
    if model.provider == "fake":
        return DeterministicEmbeddingProvider(model.dimensions)
    raise ConfigurationError(f"Unsupported embedding provider: {model.provider}")


def _reasoning_provider(config: AppConfig) -> FocusedReasoningProvider:
    model = config.models.reasoning
    if model.provider == "ollama":
        return OllamaReasoningProvider(model)
    if model.provider == "fake":
        return DeterministicReasoningProvider()
    raise ConfigurationError(f"Unsupported reasoning provider: {model.provider}")
