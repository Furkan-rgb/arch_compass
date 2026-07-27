"""Composition root: the only place that selects concrete adapters."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from archcompass.adapters.analysis import (
    DeterministicAtlasQueryService,
    PythonAstRepositoryAnalyzer,
    SafeSourceReader,
)
from archcompass.adapters.models import (
    DeterministicEmbeddingProvider,
    DeterministicReasoningProvider,
    GoogleEmbeddingProvider,
    GoogleReasoningProvider,
    OllamaEmbeddingProvider,
    OllamaReasoningProvider,
)
from archcompass.adapters.persistence import (
    SQLiteAtlasRepository,
    SQLiteBoundaryReviewRepository,
    SQLiteCaseRepository,
    SQLiteDatabase,
    SQLitePolicySourceRepository,
    SQLiteReviewConversationRepository,
)
from archcompass.adapters.retrieval import (
    MarkdownPolicySourceInspector,
    SQLitePolicyStore,
    load_method_primer,
)
from archcompass.application.atlas_freshness import AtlasFreshnessService
from archcompass.application.atlas_queries import AtlasService
from archcompass.application.bundled_cases import BundledCaseService
from archcompass.application.cases import CaseService
from archcompass.application.policies import PolicyService
from archcompass.application.repository_index import RepositoryIndexService
from archcompass.application.review_conversations import ReviewConversationService
from archcompass.application.reviews import ReviewService
from archcompass.application.safety import (
    validate_workspace_repository_separation,
)
from archcompass.application.workspace import WorkspaceConfigurationService
from archcompass.configuration import (
    AppConfig,
    load_config,
    load_provider_environment,
    resolve_config_path,
)
from archcompass.domain.errors import ConfigurationError
from archcompass.ports.atlas import AtlasQueryService, RepositoryAnalyzer
from archcompass.ports.models import EmbeddingProvider
from archcompass.ports.policies import PolicyIndex
from archcompass.ports.reasoning import FocusedReasoningProvider
from archcompass.ports.repositories import (
    AtlasRepository,
    BoundaryReviewRepository,
    CaseRepository,
)

BUNDLED_POLICY_SOURCE = Path(__file__).resolve().parent / "policies" / "general"


@dataclass(frozen=True)
class Runtime:
    """The composed application surface.

    Dependencies are named by their port, not their adapter, so nothing outside this
    module can depend on a concrete SQLite, AST, or vector-store type. `database` is
    the exception: it is this module's own infrastructure handle rather than a
    swappable dependency, and structural tests keep presentation away from it.
    """

    workspace: Path
    config: AppConfig
    database: SQLiteDatabase
    case_repository: CaseRepository
    atlas_repository: AtlasRepository
    review_repository: BoundaryReviewRepository
    review_conversation_service: ReviewConversationService
    bundled_case_service: BundledCaseService
    analyzer: RepositoryAnalyzer
    query_service: AtlasQueryService
    policy_store: PolicyIndex
    policy_sources: tuple[Path, ...]
    case_service: CaseService
    policy_service: PolicyService
    repository_service: RepositoryIndexService
    atlas_service: AtlasService
    review_service: ReviewService
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
    # Before any provider is constructed: a hosted provider reads its credential from
    # the environment, and a `.env` file is where an interactive run keeps it.
    load_provider_environment(canonical_workspace)
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
    atlases = SQLiteAtlasRepository(database)
    reviews = SQLiteBoundaryReviewRepository(database)
    review_conversations = SQLiteReviewConversationRepository(database)
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
    case_service = CaseService(cases)
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
    bundled_case_service = BundledCaseService(
        cases=cases,
        repositories=repository_service,
        atlases=atlases,
    )
    review_conversation_service = ReviewConversationService(
        reviews=reviews,
        cases=cases,
        conversations=review_conversations,
        reasoner=reasoning,
        policies=policy_service,
        method_primer=load_method_primer(),
    )
    review_service = ReviewService(
        cases=cases,
        atlases=atlases,
        reviews=reviews,
        freshness=freshness,
        policies=policy_service,
        reasoner=reasoning,
    )
    return Runtime(
        workspace=canonical_workspace,
        config=config,
        database=database,
        case_repository=cases,
        atlas_repository=atlases,
        review_repository=reviews,
        review_conversation_service=review_conversation_service,
        bundled_case_service=bundled_case_service,
        analyzer=analyzer,
        query_service=queries,
        policy_store=policies,
        policy_sources=configured_policy_sources,
        case_service=case_service,
        policy_service=policy_service,
        repository_service=repository_service,
        atlas_service=atlas_service,
        review_service=review_service,
        freshness_service=freshness,
    )


def initialize_workspace(
    workspace: Path,
    *,
    models_config: Path | None = None,
) -> WorkspaceInitialization:
    canonical_workspace = workspace.expanduser().resolve()
    # Before resolving anything: the workspace's `.env` is one of the places that says which
    # configuration to use, and reading it afterwards would mean `archcompass init` and
    # `archcompass web` never saw it. `build_runtime` loads it in this order too; loading it
    # twice is free, because a variable already set is never overwritten.
    load_provider_environment(canonical_workspace)
    config_path = resolve_config_path(canonical_workspace, models_config)
    external_config = models_config is not None or bool(
        os.environ.get("ARCHCOMPASS_MODELS_CONFIG")
    )
    # The resolved path is the initialization target, so a workspace that already keeps
    # provider-named configurations does not get an unnamed one written beside them.
    # Creating is still conditional on the file being absent.
    created = WorkspaceConfigurationService().initialize(
        canonical_workspace,
        config_path,
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
    if model.provider == "google":
        return GoogleEmbeddingProvider(model)
    if model.provider == "fake":
        return DeterministicEmbeddingProvider(model.dimensions)
    raise ConfigurationError(f"Unsupported embedding provider: {model.provider}")


def _reasoning_provider(config: AppConfig) -> FocusedReasoningProvider:
    model = config.models.reasoning
    if model.provider == "ollama":
        return OllamaReasoningProvider(model)
    if model.provider == "google":
        return GoogleReasoningProvider(model)
    if model.provider == "fake":
        return DeterministicReasoningProvider()
    raise ConfigurationError(f"Unsupported reasoning provider: {model.provider}")
