"""Composition root: the only place that selects concrete adapters."""

from __future__ import annotations

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
    SQLiteDatabase,
    SQLiteRunRepository,
)
from archcompass.adapters.repository import (
    DeterministicAtlasQueryService,
    PythonAstRepositoryAnalyzer,
    SafeSourceReader,
)
from archcompass.adapters.retrieval import SQLitePolicyStore
from archcompass.application.cases import CaseService
from archcompass.configuration import AppConfig, load_config, resolve_config_path
from archcompass.domain.errors import ConfigurationError
from archcompass.ports.services import EmbeddingProvider, ReasoningProvider
from archcompass.workflows import ConsultationWorkflow


@dataclass(frozen=True)
class Runtime:
    workspace: Path
    config: AppConfig
    database: SQLiteDatabase
    case_repository: SQLiteCaseRepository
    run_repository: SQLiteRunRepository
    atlas_repository: SQLiteAtlasRepository
    analyzer: PythonAstRepositoryAnalyzer
    query_service: DeterministicAtlasQueryService
    policy_store: SQLitePolicyStore
    case_service: CaseService
    workflow: ConsultationWorkflow


def build_runtime(
    workspace: Path,
    *,
    models_config: Path | None = None,
    initialize: bool = True,
) -> Runtime:
    canonical_workspace = workspace.expanduser().resolve()
    config = load_config(resolve_config_path(canonical_workspace, models_config))
    database = SQLiteDatabase(canonical_workspace / ".archcompass" / "archcompass.db")
    if initialize:
        database.initialize()
    embeddings = _embedding_provider(config)
    reasoning = _reasoning_provider(config)
    cases = SQLiteCaseRepository(database)
    runs = SQLiteRunRepository(database)
    atlases = SQLiteAtlasRepository(database)
    source_reader = SafeSourceReader()
    queries = DeterministicAtlasQueryService(source_reader)
    policies = SQLitePolicyStore(database, embeddings)
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
    )
    return Runtime(
        workspace=canonical_workspace,
        config=config,
        database=database,
        case_repository=cases,
        run_repository=runs,
        atlas_repository=atlases,
        analyzer=PythonAstRepositoryAnalyzer(),
        query_service=queries,
        policy_store=policies,
        case_service=CaseService(cases),
        workflow=workflow,
    )


def _embedding_provider(config: AppConfig) -> EmbeddingProvider:
    model = config.models.embedding
    if model.provider == "ollama":
        return OllamaEmbeddingProvider(model)
    if model.provider == "fake":
        return DeterministicEmbeddingProvider(model.dimensions)
    raise ConfigurationError(f"Unsupported embedding provider: {model.provider}")


def _reasoning_provider(config: AppConfig) -> ReasoningProvider:
    model = config.models.reasoning
    if model.provider == "ollama":
        return OllamaReasoningProvider(model)
    if model.provider == "fake":
        return DeterministicReasoningProvider()
    raise ConfigurationError(f"Unsupported reasoning provider: {model.provider}")
