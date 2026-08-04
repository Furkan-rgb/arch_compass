"""Composition root: the only place that selects concrete adapters."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from archcompass.adapters.analysis import (
    DeterministicAtlasQueryService,
    PythonAstRepositoryAnalyzer,
    SafeSourceReader,
)
from archcompass.adapters.models import SelectedModelReasoner
from archcompass.adapters.models import (
    deterministic as deterministic_models,
)
from archcompass.adapters.models import (
    google as google_models,
)
from archcompass.adapters.models import (
    ollama as ollama_models,
)
from archcompass.adapters.persistence import (
    SQLiteAtlasRepository,
    SQLiteBoundaryReviewRepository,
    SQLiteCaseRepository,
    SQLiteDatabase,
    SQLiteLineageRepository,
    SQLitePolicySourceRepository,
    SQLiteReasoningModelSelectionRepository,
    SQLiteReviewConversationRepository,
    SQLiteVerdictCacheRepository,
)
from archcompass.adapters.retrieval import (
    MarkdownPolicySourceInspector,
    MarkdownPolicyStore,
    load_method_primer,
)
from archcompass.application.atlas_freshness import AtlasFreshnessService
from archcompass.application.atlas_queries import AtlasService
from archcompass.application.bundled_examples import BundledExampleService
from archcompass.application.cases import CaseService
from archcompass.application.model_catalog import ModelCatalogService, reasoning_config
from archcompass.application.policies import PolicyService
from archcompass.application.repository_index import RepositoryIndexService
from archcompass.application.review_conversations import ReviewConversationService
from archcompass.application.review_source import ReviewSourceService
from archcompass.application.reviews import ReviewService
from archcompass.application.safety import (
    validate_repository_directory,
)
from archcompass.configuration import (
    ReasoningModelConfig,
    load_provider_environment,
)
from archcompass.domain.errors import ConfigurationError
from archcompass.ports.atlas import AtlasQueryService, EdgeResolver, RepositoryAnalyzer
from archcompass.ports.model_catalog import ProviderDescriptor
from archcompass.ports.reasoning import FocusedReasoningProvider
from archcompass.ports.repositories import (
    AtlasRepository,
    BoundaryReviewRepository,
    CaseRepository,
    LineageRepository,
    VerdictCacheRepository,
)

BUNDLED_POLICY_SOURCE = Path(__file__).resolve().parent / "policies" / "general"

#: Everything a workspace holds that Arch Compass itself writes: the database, and the
#: policies authored in it. Named once because it is also what an analysis of the workspace's
#: own repository has to leave out.
WORKSPACE_STATE_DIRECTORY = Path(".archcompass")

#: Where a workspace keeps the policies written in it, beside the database it already keeps
#: there. The one policy directory Arch Compass owns the files in: everything else in the
#: corpus is somebody else's Markdown, read where it lies.
AUTHORED_POLICY_DIRECTORY = WORKSPACE_STATE_DIRECTORY / "policies"


@dataclass(frozen=True)
class Runtime:
    """The composed application surface.

    Dependencies are named by their port, not their adapter, so nothing outside this
    module can depend on a concrete SQLite, AST, or vector-store type. `database` is
    the exception: it is this module's own infrastructure handle rather than a
    swappable dependency, and structural tests keep presentation away from it.
    """

    workspace: Path
    database: SQLiteDatabase
    case_repository: CaseRepository
    atlas_repository: AtlasRepository
    lineage_repository: LineageRepository
    review_repository: BoundaryReviewRepository
    verdict_cache_repository: VerdictCacheRepository
    review_conversation_service: ReviewConversationService
    review_source_service: ReviewSourceService
    bundled_example_service: BundledExampleService
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


def build_runtime(
    workspace: Path,
    *,
    pin: ReasoningModelConfig | None = None,
    policy_sources: list[Path] | None = None,
    repository: Path | None = None,
    initialize: bool = True,
) -> Runtime:
    canonical_workspace = workspace.expanduser().resolve()
    if repository is not None:
        validate_repository_directory(repository)
    # Before any provider is constructed: a hosted provider reads its credential from
    # the environment, and a `.env` file is where an interactive run keeps it.
    load_provider_environment(canonical_workspace)
    canonical_workspace.mkdir(parents=True, exist_ok=True)
    # Which model this workspace reasons with is a row in this database, so it is opened
    # before anything asks. Nothing else here needs it.
    database = SQLiteDatabase(
        canonical_workspace / WORKSPACE_STATE_DIRECTORY / "archcompass.db",
        workspace=canonical_workspace,
    )
    if initialize:
        database.initialize()
    model_catalog_service = ModelCatalogService(
        registry=enabled_providers(),
        selections=SQLiteReasoningModelSelectionRepository(database),
        pin=pin,
    )
    # Resolved per call rather than built here: the choice can change while this process
    # runs, and a workspace that has not made one yet still has to start.
    reasoning = SelectedModelReasoner(model_catalog_service, _build_reasoner)
    cases = SQLiteCaseRepository(database)
    atlases = SQLiteAtlasRepository(database)
    lineages = SQLiteLineageRepository(database)
    reviews = SQLiteBoundaryReviewRepository(database)
    verdict_cache = SQLiteVerdictCacheRepository(database)
    review_conversations = SQLiteReviewConversationRepository(database)
    # The workspace is left out of every snapshot, which is what allows a repository to be
    # analysed with its own workspace inside it. What the workspace holds changes whenever a
    # review runs, so indexing it would move the content fingerprint on every run and leave
    # the atlas permanently stale.
    #
    # The state directory is named as well as the workspace, for the case this repository is
    # itself: a workspace that *is* the analysed repository cannot be excluded whole without
    # emptying the atlas, so what Arch Compass writes there is excluded instead.
    excluded_roots = (
        canonical_workspace,
        canonical_workspace / WORKSPACE_STATE_DIRECTORY,
    )
    analyzer = PythonAstRepositoryAnalyzer(
        edge_resolver=build_edge_resolver(excluded_roots),
        excluded_roots=excluded_roots,
    )
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
        analyzer=analyzer,
        atlases=atlases,
        lineages=lineages,
    )
    atlas_service = AtlasService(
        atlases=atlases,
        queries=queries,
        freshness=freshness,
    )
    bundled_example_service = BundledExampleService(
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
        verdict_cache=verdict_cache,
    )
    return Runtime(
        workspace=canonical_workspace,
        database=database,
        case_repository=cases,
        atlas_repository=atlases,
        lineage_repository=lineages,
        review_repository=reviews,
        verdict_cache_repository=verdict_cache,
        review_conversation_service=review_conversation_service,
        review_source_service=review_source_service,
        bundled_example_service=bundled_example_service,
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
    pin: ReasoningModelConfig | None = None,
) -> Runtime:
    """Open a workspace, creating what it is missing.

    Nothing is written but the workspace directory and its database. It used to seed a model
    configuration file too, and the file is gone: which providers exist is stated in code,
    and which model this workspace reasons with is a choice the interface asks for where a
    model is actually needed — offering only models a reachable provider has, rather than
    naming one that may not be installed.
    """

    canonical_workspace = workspace.expanduser().resolve()
    # Before anything reaches a provider: a hosted provider reads its credential from the
    # environment, and a `.env` is where an interactive run keeps it. `build_runtime` loads
    # it in this order too; loading it twice is free, because a variable already set is never
    # overwritten.
    load_provider_environment(canonical_workspace)
    return build_runtime(canonical_workspace, pin=pin)


#: Every provider this build knows how to reach, each registered by the module that
#: implements it.
#:
#: One table rather than three parallel dispatches on the same strings. Building, probing
#: and the defaults are wanted at different moments — one when a review runs, one when
#: someone opens the chooser, one when a selection is resolved — and three if-chains over
#: `"ollama" | "google" | "fake"` are three things that drift. It is also where the
#: descriptors are type-checked: probes are plain functions held by name, so this is the one
#: place their signatures have to agree with the port.
_ALL_PROVIDERS: Final[dict[str, ProviderDescriptor]] = {
    descriptor.name: descriptor
    for descriptor in (
        ollama_models.DESCRIPTOR,
        google_models.DESCRIPTOR,
        deterministic_models.DESCRIPTOR,
    )
}

#: Which of them a deployment offers, as a comma-separated list of names. Absent means all,
#: which is what a local run wants.
PROVIDERS_VARIABLE: Final = "ARCHCOMPASS_PROVIDERS"


def build_edge_resolver(excluded_roots: tuple[Path, ...] = ()) -> EdgeResolver | None:
    """The type oracle, if this installation has one.

    Its backend is an optional extra (`uv sync --extra resolution`), so whether the import
    succeeds is the whole of the decision — there is no flag, and nothing above this module
    can be configured into asking for a resolver that is not installed. Absent, the atlas is
    exactly what it was before typed edges existed.

    It is given the analyzer's excluded subtrees because it builds its own module list from
    the repository rather than from the snapshot; without them a workspace inside the
    repository would be type-checked even though the atlas has no nodes for it.
    """

    try:
        from archcompass.adapters.analysis.mypy_resolver import MypyEdgeResolver
    except ImportError:
        return None
    return MypyEdgeResolver(excluded_roots)


def enabled_providers() -> dict[str, ProviderDescriptor]:
    """The providers this deployment offers, in the order it named them.

    A hosted deployment has no Ollama to reach, and a chooser listing one is a row that can
    only ever say "nothing is listening" — worse than absent, because it reads as something
    broken rather than as something not on offer. An unknown name is refused rather than
    ignored: a typo that silently narrows the list would present itself as a provider that
    has gone missing.
    """

    raw = os.environ.get(PROVIDERS_VARIABLE, "").strip()
    if not raw:
        return dict(_ALL_PROVIDERS)
    names = [item.strip() for item in raw.split(",") if item.strip()]
    unknown = [item for item in names if item not in _ALL_PROVIDERS]
    if unknown:
        raise ConfigurationError(
            f"{PROVIDERS_VARIABLE} names {', '.join(unknown)}, which this build cannot "
            f"reach. It knows: {', '.join(_ALL_PROVIDERS)}."
        )
    return {item: _ALL_PROVIDERS[item] for item in names}


def pinned_model(
    provider: str, model: str, thinking: bool | None = None
) -> ReasoningModelConfig:
    """The configuration a command line asked for, refused by name if it cannot be reached.

    Validated against the enabled registry rather than against everything this build knows,
    so a run naming a provider its deployment has switched off is told so at the point of
    asking instead of at the first boundary of a review.
    """

    descriptor = enabled_providers().get(provider)
    if descriptor is None:
        raise ConfigurationError(
            f"{provider} is not a provider this deployment offers. It has: "
            f"{', '.join(enabled_providers())}."
        )
    return reasoning_config(descriptor, model, thinking)


def _build_reasoner(model: ReasoningModelConfig) -> FocusedReasoningProvider:
    descriptor = _ALL_PROVIDERS.get(model.provider)
    if descriptor is None:
        raise ConfigurationError(f"Unsupported reasoning provider: {model.provider}")
    return descriptor.build(model)
