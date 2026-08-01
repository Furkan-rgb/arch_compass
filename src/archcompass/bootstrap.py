"""Composition root: the only place that selects concrete adapters."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Final, NamedTuple

from archcompass.adapters.analysis import (
    DeterministicAtlasQueryService,
    PythonAstRepositoryAnalyzer,
    SafeSourceReader,
)
from archcompass.adapters.models import (
    DeterministicReasoningProvider,
    GoogleReasoningProvider,
    OllamaReasoningProvider,
    SelectedModelReasoner,
    probe_deterministic,
    probe_google,
    probe_ollama,
)
from archcompass.adapters.persistence import (
    SQLiteAtlasRepository,
    SQLiteBoundaryReviewRepository,
    SQLiteCaseRepository,
    SQLiteDatabase,
    SQLitePolicySourceRepository,
    SQLiteReasoningModelSelectionRepository,
    SQLiteReviewConversationRepository,
)
from archcompass.adapters.retrieval import (
    MarkdownPolicySourceInspector,
    MarkdownPolicyStore,
    load_method_primer,
)
from archcompass.application.atlas_freshness import AtlasFreshnessService
from archcompass.application.atlas_queries import AtlasService
from archcompass.application.bundled_cases import BundledCaseService
from archcompass.application.cases import CaseService
from archcompass.application.model_catalog import ModelCatalogService
from archcompass.application.policies import PolicyService
from archcompass.application.repository_index import RepositoryIndexService
from archcompass.application.review_conversations import ReviewConversationService
from archcompass.application.review_source import ReviewSourceService
from archcompass.application.reviews import ReviewService
from archcompass.application.safety import (
    validate_workspace_repository_separation,
)
from archcompass.application.workspace import WorkspaceConfigurationService
from archcompass.configuration import (
    AppConfig,
    ReasoningModelConfig,
    load_config,
    load_provider_environment,
    resolve_config_path,
    run_is_pinned,
)
from archcompass.domain.errors import ConfigurationError
from archcompass.domain.model_catalog import ProbeResult
from archcompass.ports.atlas import AtlasQueryService, RepositoryAnalyzer
from archcompass.ports.model_catalog import (
    ReasoningModelProbe,
    ReasoningProviderFactory,
)
from archcompass.ports.reasoning import FocusedReasoningProvider
from archcompass.ports.repositories import (
    AtlasRepository,
    BoundaryReviewRepository,
    CaseRepository,
)

BUNDLED_POLICY_SOURCE = Path(__file__).resolve().parent / "policies" / "general"

#: Where a workspace keeps the policies written in it, beside the database it already keeps
#: there. The one policy directory Arch Compass owns the files in: everything else in the
#: corpus is somebody else's Markdown, read where it lies.
AUTHORED_POLICY_DIRECTORY = Path(".archcompass") / "policies"


@dataclass(frozen=True)
class Runtime:
    """The composed application surface.

    Dependencies are named by their port, not their adapter, so nothing outside this
    module can depend on a concrete SQLite, AST, or vector-store type. `database` is
    the exception: it is this module's own infrastructure handle rather than a
    swappable dependency, and structural tests keep presentation away from it.
    """

    workspace: Path
    #: What this run was pointed at, where it was pointed at anything usable. Absent for a
    #: workspace holding several configurations and no instruction about which to use — the
    #: case the model chooser exists to settle, and no longer a reason to refuse to start.
    config: AppConfig | None
    database: SQLiteDatabase
    case_repository: CaseRepository
    atlas_repository: AtlasRepository
    review_repository: BoundaryReviewRepository
    review_conversation_service: ReviewConversationService
    review_source_service: ReviewSourceService
    bundled_case_service: BundledCaseService
    analyzer: RepositoryAnalyzer
    query_service: AtlasQueryService
    policy_sources: tuple[Path, ...]
    case_service: CaseService
    policy_service: PolicyService
    repository_service: RepositoryIndexService
    atlas_service: AtlasService
    review_service: ReviewService
    freshness_service: AtlasFreshnessService
    model_catalog_service: ModelCatalogService


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
    canonical_workspace.mkdir(parents=True, exist_ok=True)
    # The database comes before the configuration now, because which model this workspace
    # reasons with is a row in it. Nothing here needs the configuration to open the file.
    database = SQLiteDatabase(
        canonical_workspace / ".archcompass" / "archcompass.db",
        workspace=canonical_workspace,
    )
    if initialize:
        database.initialize()
    config = _configured(canonical_workspace, models_config)
    model_catalog_service = ModelCatalogService(
        workspace=canonical_workspace,
        explicit_config=models_config,
        pinned=run_is_pinned(models_config),
        selections=SQLiteReasoningModelSelectionRepository(database),
        probe=_probe_provider,
        configured=config,
    )
    # Resolved per call rather than built here: the choice can change while this process
    # runs, and a workspace that has not made one yet still has to start.
    reasoning = SelectedModelReasoner(model_catalog_service, _build_reasoner)
    cases = SQLiteCaseRepository(database)
    atlases = SQLiteAtlasRepository(database)
    reviews = SQLiteBoundaryReviewRepository(database)
    review_conversations = SQLiteReviewConversationRepository(database)
    analyzer = PythonAstRepositoryAnalyzer()
    freshness = AtlasFreshnessService(analyzer)
    source_reader = SafeSourceReader()
    queries = DeterministicAtlasQueryService(source_reader, freshness)
    configured_policy_sources = tuple(
        source.expanduser().resolve(strict=False)
        for source in (
            policy_sources
            if policy_sources is not None
            else [BUNDLED_POLICY_SOURCE]
        )
    )
    policy_service = PolicyService(
        source_repository=SQLitePolicySourceRepository(database),
        source_inspector=MarkdownPolicySourceInspector(),
        bundled_sources=configured_policy_sources,
        authored_source=canonical_workspace / AUTHORED_POLICY_DIRECTORY,
        policy_store=MarkdownPolicyStore(),
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
    )
    review_source_service = ReviewSourceService(
        atlases=atlases,
        source_reader=source_reader,
        freshness=freshness,
    )
    review_conversation_service = ReviewConversationService(
        reviews=reviews,
        cases=cases,
        conversations=review_conversations,
        reasoner=reasoning,
        policies=policy_service,
        source=review_source_service,
        method_primer=load_method_primer(),
    )
    review_service = ReviewService(
        cases=cases,
        atlases=atlases,
        reviews=reviews,
        freshness=freshness,
        policies=policy_service,
        reasoner=reasoning,
        source=review_source_service,
    )
    return Runtime(
        workspace=canonical_workspace,
        config=config,
        database=database,
        case_repository=cases,
        atlas_repository=atlases,
        review_repository=reviews,
        review_conversation_service=review_conversation_service,
        review_source_service=review_source_service,
        bundled_case_service=bundled_case_service,
        analyzer=analyzer,
        query_service=queries,
        policy_sources=configured_policy_sources,
        case_service=case_service,
        policy_service=policy_service,
        repository_service=repository_service,
        atlas_service=atlas_service,
        review_service=review_service,
        freshness_service=freshness,
        model_catalog_service=model_catalog_service,
    )


def initialize_workspace(
    workspace: Path,
    *,
    models_config: Path | None = None,
    write_default_config: bool = True,
) -> WorkspaceInitialization:
    """Open a workspace, creating what it is missing.

    `write_default_config` is what separates the two commands that call this. `init` exists
    to create missing configuration, so it writes one. The web workspace does not: a
    workspace with nothing configured is now a state it can display and offer to settle, and
    seeding an Ollama configuration into a hosted deployment that has no Ollama would replace
    "choose a model" with a provider that is there in name and unreachable in fact.
    """

    canonical_workspace = workspace.expanduser().resolve()
    # Before resolving anything: the workspace's `.env` is one of the places that says which
    # configuration to use, and reading it afterwards would mean `archcompass init` and
    # `archcompass web` never saw it. `build_runtime` loads it in this order too; loading it
    # twice is free, because a variable already set is never overwritten.
    load_provider_environment(canonical_workspace)
    created: list[Path] = []
    if write_default_config:
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
        models_config = config_path
    runtime = build_runtime(canonical_workspace, models_config=models_config)
    return WorkspaceInitialization(runtime=runtime, created_paths=tuple(created))


def _configured(workspace: Path, models_config: Path | None) -> AppConfig | None:
    """The configuration this run was pointed at, where it was pointed at a usable one.

    `resolve_config_path` refuses to guess between several configurations, and that refusal
    is right for a command whose whole cost turns on the answer. It is not a reason for a
    workspace to fail to open: choosing between them is what the interface now does. So the
    refusal becomes an absence here, and the absence becomes a required field on screen
    rather than a traceback before anything has loaded.
    """

    try:
        return load_config(resolve_config_path(workspace, models_config))
    except ConfigurationError:
        return None


class ProviderEntry(NamedTuple):
    """How to reach one provider, and how to ask whether it is there."""

    build: ReasoningProviderFactory
    probe: ReasoningModelProbe


def _deterministic(config: ReasoningModelConfig) -> FocusedReasoningProvider:
    del config
    return DeterministicReasoningProvider()


#: Every provider this application knows, paired with its own availability check.
#:
#: One table rather than two dispatches on the same strings. Building and probing are asked
#: for at different moments — one when a review runs, one when someone opens the chooser —
#: and a pair of parallel if-chains over `"ollama" | "google" | "fake"` is a pair that
#: drifts. It is also where the probes are type-checked: they are plain functions passed by
#: name, so this dict is the one place their signatures have to agree with the port.
_PROVIDERS: Final[dict[str, ProviderEntry]] = {
    "ollama": ProviderEntry(OllamaReasoningProvider, probe_ollama),
    "google": ProviderEntry(GoogleReasoningProvider, probe_google),
    "fake": ProviderEntry(_deterministic, probe_deterministic),
}


def _build_reasoner(model: ReasoningModelConfig) -> FocusedReasoningProvider:
    entry = _PROVIDERS.get(model.provider)
    if entry is None:
        raise ConfigurationError(f"Unsupported reasoning provider: {model.provider}")
    return entry.build(model)


def _probe_provider(model: ReasoningModelConfig) -> ProbeResult:
    """Ask one profile's provider what it has, answering for an unknown one rather than raising.

    The asymmetry with `_build_reasoner` is deliberate. Running a review against a provider
    nothing can build has to stop; listing what a workspace could run against does not, and
    a single stray `models.experimental.yaml` naming a typo must not be able to empty a
    chooser of the providers that do work.
    """

    entry = _PROVIDERS.get(model.provider)
    if entry is None:
        return ProbeResult(
            available=False,
            detail=f"{model.provider} is not a provider this version knows how to reach",
        )
    return entry.probe(model)
