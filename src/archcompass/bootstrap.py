"""Composition root: the only place that selects concrete adapters."""

from __future__ import annotations

import os
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer
from langgraph.checkpoint.sqlite import SqliteSaver

from archcompass.analysis.adapters import (
    UNLIMITED_ANALYSIS,
    AnalysisLimits,
    DeterministicAtlasQueryService,
    PythonAstRepositoryAnalyzer,
    SafeSourceReader,
)
from archcompass.analysis.analyzer import (
    DataclassCandidateDetector,
    DataclassRepositoryAnalyzer,
)
from archcompass.analysis.delta import DeterministicRevisionCalculator
from archcompass.analysis.freshness import AtlasFreshnessService
from archcompass.analysis.queries import AtlasService
from archcompass.configuration import (
    ReasoningModelConfig,
    load_provider_environment,
)
from archcompass.domain.errors import ConfigurationError, NoReasoningModelSelectedError
from archcompass.persistence import (
    SQLiteAtlasRepository,
    SQLiteCoreCaseRepository,
    SQLiteCoreConversationRepository,
    SQLiteCoreFindingCache,
    SQLiteCoreModelSelectionRepository,
    SQLiteCoreReviewRepository,
    SQLiteCoreStandingDecisionRepository,
    SQLiteDatabase,
    SQLiteEmbeddingModelSelectionRepository,
    SQLiteLineageRepository,
    SQLitePolicySourceRepository,
    SQLiteReviewExecutionRepository,
    SQLiteScopeSelectionRepository,
    SQLiteSourceOriginRepository,
)
from archcompass.persistence.context import SQLiteContextLoader
from archcompass.policies.adapters import (
    MarkdownPolicySourceInspector,
    MarkdownPolicyStore,
    SelectedDensePolicyRetriever,
)
from archcompass.policies.adapters.embeddings import (
    DEFAULT_GOOGLE_EMBEDDING_DIMENSIONS,
    DEFAULT_GOOGLE_EMBEDDING_MODEL,
    embedding_config_from_environment,
)
from archcompass.policies.corpus import DataclassPolicyCorpus
from archcompass.policies.retrieval import RejudgeAllCandidates, corpus_fingerprint
from archcompass.policies.service import PolicyService
from archcompass.ports.atlas import AtlasQueryService, EdgeResolver, RepositoryAnalyzer
from archcompass.ports.model_catalog import ProviderDescriptor
from archcompass.ports.persistence import (
    AtlasRepository,
    LineageRepository,
)
from archcompass.reasoning.adapters.embedding_catalog import ProviderEmbeddingModelDiscovery
from archcompass.reasoning.adapters.providers import (
    DETERMINISTIC_DESCRIPTOR,
    GOOGLE_DESCRIPTOR,
    OLLAMA_DESCRIPTOR,
)
from archcompass.reasoning.adapters.selected import (
    SelectedLangChainChatModel,
    SelectedLangChainJudge,
    SelectedLangChainQuestionGenerator,
    SelectedLangChainReviewAnswerer,
)
from archcompass.reasoning.cache import (
    CachingArchitectureJudge,
    CachingReviewRecorder,
)
from archcompass.reasoning.conversation import CoreReviewConversationService
from archcompass.reasoning.embedding_models import EmbeddingModelService
from archcompass.reasoning.model_catalog import ModelCatalogService, reasoning_config
from archcompass.reasoning.records import EmbeddingModelSelection
from archcompass.repositories.adapters import GitCommandLineClient, HttpsTarballFetcher
from archcompass.repositories.checkout import RepositoryCheckoutService
from archcompass.repositories.examples import BundledExampleService
from archcompass.repositories.safety import (
    validate_repository_directory,
)
from archcompass.repositories.service import RepositoryIndexService
from archcompass.repositories.sources import SourceArchiveService
from archcompass.repositories.storage import SourceStorage
from archcompass.workflow import ReviewWorkflowCapabilities, build_review_graph
from archcompass.workflow.cases import ArchitectureCaseService
from archcompass.workflow.ci import CleanBreakCiRunService
from archcompass.workflow.decisions import StandingDecisionService
from archcompass.workflow.defaults import (
    ChangedAndNewCandidateSelector,
    DeterministicReviewComposer,
    PersistentCaseReviser,
)
from archcompass.workflow.service import ReviewWorkflowService

BUNDLED_POLICY_SOURCE = Path(__file__).resolve().parent / "policies" / "general"

#: Everything a workspace holds that Arch Compass itself writes: the database, and the
#: policies authored in it. Named once because it is also what an analysis of the workspace's
#: own repository has to leave out.
WORKSPACE_STATE_DIRECTORY = Path(".archcompass")
WORKSPACE_DATABASE_NAME = "workspace.sqlite3"

#: Where a workspace keeps the clones it was asked to make, beside the database and the
#: policies. A checkout is state Arch Compass wrote and can throw away — deleting the
#: directory loses nothing but the time to clone it again — so it belongs with the rest of
#: what the workspace owns rather than somewhere in the user's home.
CHECKOUT_DIRECTORY = WORKSPACE_STATE_DIRECTORY / "checkouts"

#: Where a workspace keeps the source trees it fetched without git. Its own directory rather
#: than a corner of the one above, because the difference is what `checkouts.refresh` tests
#: for: a checkout can be brought up to date from the remote it remembers, and an extracted
#: tree remembers nothing. Kept apart, a folder from here is simply not a managed checkout,
#: and the unconditional refresh every run begins with stays the no-op it is for anybody
#: else's working copy — rather than finding a directory it half recognises and failing.
SOURCE_DIRECTORY = WORKSPACE_STATE_DIRECTORY / "sources"

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
    atlas_repository: AtlasRepository
    lineage_repository: LineageRepository
    review_conversation_service: CoreReviewConversationService
    bundled_example_service: BundledExampleService
    analyzer: RepositoryAnalyzer
    query_service: AtlasQueryService
    policy_sources: tuple[Path, ...]
    case_service: ArchitectureCaseService
    policy_service: PolicyService
    repository_service: RepositoryIndexService
    atlas_service: AtlasService
    checkout_service: RepositoryCheckoutService
    #: Present only where a deployment named hosts to fetch from. `None` means this
    #: workspace puts repositories on disk with git, which is every local run.
    source_service: SourceArchiveService | None
    freshness_service: AtlasFreshnessService
    model_catalog_service: ModelCatalogService
    embedding_model_service: EmbeddingModelService
    core_case_repository: SQLiteCoreCaseRepository
    core_review_repository: SQLiteCoreReviewRepository
    review_workflow_service: ReviewWorkflowService
    checkpoint_connection: sqlite3.Connection
    core_ci_service: CleanBreakCiRunService
    standing_decision_service: StandingDecisionService


def build_runtime(
    workspace: Path,
    *,
    pin: ReasoningModelConfig | None = None,
    policy_sources: list[Path] | None = None,
    repository: Path | None = None,
    initialize: bool = True,
    source_hosts: frozenset[str] = frozenset(),
    max_source_bytes: int = 0,
    source_timeout: int = 0,
    source_storage: SourceStorage | None = None,
    analysis_limits: AnalysisLimits = UNLIMITED_ANALYSIS,
) -> Runtime:
    canonical_workspace = workspace.expanduser().resolve()
    if repository is not None:
        validate_repository_directory(repository)
    # Before any provider is constructed: a hosted provider reads its credential from
    # the environment, and a `.env` file is where an interactive run keeps it.
    load_provider_environment(canonical_workspace)
    canonical_workspace.mkdir(parents=True, exist_ok=True)
    core_database = SQLiteDatabase(
        canonical_workspace / WORKSPACE_STATE_DIRECTORY / WORKSPACE_DATABASE_NAME,
        workspace=canonical_workspace,
    )
    # Repository-analysis records and domain aggregates share one application database.
    database = core_database
    if initialize:
        database.initialize()
    provider_registry = enabled_providers()
    model_catalog_service = ModelCatalogService(
        registry=provider_registry,
        selections=SQLiteCoreModelSelectionRepository(core_database.raw_connect),
        pin=pin,
    )
    explicit_embedding = any(
        os.environ.get(name, "").strip()
        for name in (
            "ARCHCOMPASS_EMBEDDING_PROVIDER",
            "ARCHCOMPASS_EMBEDDING_MODEL",
            "ARCHCOMPASS_EMBEDDING_DIMENSIONS",
            "ARCHCOMPASS_EMBEDDING_BASE_URL",
            "ARCHCOMPASS_EMBEDDING_API_KEY_ENV",
        )
    )
    embedding_model_service = EmbeddingModelService(
        providers=tuple(provider_registry.values()),
        discovery=ProviderEmbeddingModelDiscovery(),
        selections=SQLiteEmbeddingModelSelectionRepository(core_database.raw_connect),
        default=EmbeddingModelSelection(
            provider="google",
            model=DEFAULT_GOOGLE_EMBEDDING_MODEL,
            dimensions=DEFAULT_GOOGLE_EMBEDDING_DIMENSIONS,
        ),
        pin=embedding_config_from_environment() if explicit_embedding else None,
    )
    # Resolved per call rather than built here: the choice can change while this process
    # runs, and a workspace that has not made one yet still has to start.
    atlases = SQLiteAtlasRepository(database)
    lineages = SQLiteLineageRepository(database)
    core_cases = SQLiteCoreCaseRepository(core_database.raw_connect)
    core_reviews = SQLiteCoreReviewRepository(core_database.raw_connect)
    # Which folders a repository is reviewed without. Read by indexing and by the freshness
    # check, which is the whole reason it is stored rather than passed: the check recomputes
    # the fingerprint and has to leave out what the analysis left out.
    scope_selections = SQLiteScopeSelectionRepository(database)
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
        # A workspace that fetches repositories it was pointed at by strangers is the one
        # that needs a ceiling on how much of one it will hold in memory. Everywhere else
        # the directory was chosen by the person whose machine it is, and an analysis that
        # quietly left half of it out would be the worse answer.
        limits=analysis_limits,
    )
    freshness = AtlasFreshnessService(analyzer, scope_selections)
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
    case_service = ArchitectureCaseService(core_cases, core_reviews, lineages)
    repository_service = RepositoryIndexService(
        analyzer=analyzer,
        atlases=atlases,
        lineages=lineages,
        scope_selections=scope_selections,
    )
    atlas_service = AtlasService(
        atlases=atlases,
        queries=queries,
        freshness=freshness,
    )
    bundled_example_service = BundledExampleService(
        repositories=repository_service,
    )
    executions = SQLiteReviewExecutionRepository(core_database.raw_connect)
    core_decisions = SQLiteCoreStandingDecisionRepository(core_database.raw_connect)
    core_finding_cache = SQLiteCoreFindingCache(core_database.raw_connect)
    core_conversations = SQLiteCoreConversationRepository(core_database.raw_connect)
    selected_chat = SelectedLangChainChatModel(model_catalog_service)
    review_conversation_service = CoreReviewConversationService(
        reviews=core_reviews,
        conversations=core_conversations,
        answerer=SelectedLangChainReviewAnswerer(selected_chat),
    )
    checkpoint_connection = sqlite3.connect(
        canonical_workspace / WORKSPACE_STATE_DIRECTORY / "review-checkpoints.db",
        check_same_thread=False,
    )
    checkpointer = SqliteSaver(
        checkpoint_connection,
        serde=JsonPlusSerializer(
            allowed_msgpack_modules=[
                ("archcompass.domain.repository", "RepositoryRef"),
                *[
                    ("archcompass.domain.case", name)
                    for name in (
                        "PolicyContext",
                        "ArchitectureCase",
                        "CaseConstraint",
                        "CaseDecision",
                        "CaseFacet",
                        "Question",
                        "AnswerStatus",
                        "Answer",
                    )
                ],
                ("archcompass.domain.atlas", "RepositoryAtlas"),
                *[
                    ("archcompass.domain.candidate", name)
                    for name in ("Participant", "Candidate")
                ],
                *[
                    ("archcompass.domain.values", name)
                    for name in ("SourceLocation", "Evidence")
                ],
                *[
                    ("archcompass.domain.finding", name)
                    for name in ("Verdict", "PolicyBearing", "Finding")
                ],
                *[
                    ("archcompass.domain.review", name)
                    for name in (
                        "ReviewStatus",
                        "ChangeCause",
                        "CandidateChange",
                        "AddressedCandidate",
                        "ReviewDelta",
                        "RetrievalProvenance",
                        "Review",
                    )
                ],
                *[
                    ("archcompass.domain.policy", name)
                    for name in ("PolicyScope", "PolicyStrength", "Policy")
                ],
                *[
                    ("archcompass.ports.policy_retrieval", name)
                    for name in ("PolicySelection", "RetrievedPolicySet")
                ],
                ("archcompass.ports.capabilities", "ReviewDraft"),
            ],
        ),
    )
    checkpointer.setup()
    policy_corpus = DataclassPolicyCorpus(policy_service)

    def selected_model_identity() -> str:
        selected = model_catalog_service.current()
        if selected is None:
            return ""
        if selected.provider == "fake":
            return f"fake:{selected.model}"
        return f"{selected.provider}:{selected.model}:thinking={selected.thinking}"

    def selected_prompt_identity() -> str:
        selected = model_catalog_service.current()
        return (
            "judge:deterministic-v1"
            if selected is not None and selected.provider == "fake"
            else "judge:v2"
        )

    def deterministic_retrieval_mode() -> bool:
        selected = model_catalog_service.current()
        if selected is None:
            raise NoReasoningModelSelectedError(
                "No reasoning model is selected. Choose one with the model chip before "
                "starting a review."
            )
        return selected.provider == "fake"

    graph = build_review_graph(
        ReviewWorkflowCapabilities(
            context=SQLiteContextLoader(
                database.raw_connect, core_cases, core_reviews
            ),
            analyzer=DataclassRepositoryAnalyzer(analyzer),
            detector=DataclassCandidateDetector(),
            revisions=DeterministicRevisionCalculator(
                corpus_fingerprint=lambda repository_ref: corpus_fingerprint(
                    policy_corpus.policies_for(repository_ref)
                ),
                model_identity=selected_model_identity,
                prompt_identity=selected_prompt_identity,
            ),
            initial_candidates=ChangedAndNewCandidateSelector(),
            corpus=policy_corpus,
            retriever=SelectedDensePolicyRetriever(
                core_database.raw_connect,
                embedding_config=embedding_model_service.current,
                deterministic_mode=deterministic_retrieval_mode,
            ),
            judge=CachingArchitectureJudge(
                SelectedLangChainJudge(selected_chat),
                core_finding_cache,
                model_identity=selected_model_identity,
                prompt_identity=selected_prompt_identity,
            ),
            questions=SelectedLangChainQuestionGenerator(selected_chat),
            rejudgements=RejudgeAllCandidates(),
            cases=PersistentCaseReviser(core_cases),
            composer=DeterministicReviewComposer(),
            recorder=CachingReviewRecorder(core_reviews, core_finding_cache),
        ),
        checkpointer=checkpointer,
    )
    review_workflow_service = ReviewWorkflowService(
        graph,
        reviews=core_reviews,
        executions=executions,
    )
    standing_decision_service = StandingDecisionService(
        decisions=core_decisions, reviews=core_reviews
    )
    core_ci_service = CleanBreakCiRunService(
        repositories=repository_service,
        workflow=review_workflow_service,
        decisions=standing_decision_service,
    )
    checkout_service = RepositoryCheckoutService(
        git=GitCommandLineClient(),
        checkouts_root=canonical_workspace / CHECKOUT_DIRECTORY,
    )
    # Only built when a deployment named the hosts it will fetch from. `None` everywhere
    # else, which is what a workspace on somebody's own machine wants: it has git, and a
    # clone gives it the history that a durable identity is derived from.
    source_service = (
        SourceArchiveService(
            fetcher=HttpsTarballFetcher(
                hosts=source_hosts,
                max_bytes=max_source_bytes,
                timeout=source_timeout,
            ),
            sources_root=canonical_workspace / SOURCE_DIRECTORY,
            hosts=source_hosts,
            origins=SQLiteSourceOriginRepository(database),
            storage=source_storage,
            reserve_bytes=max_source_bytes,
        )
        if source_hosts
        else None
    )
    return Runtime(
        workspace=canonical_workspace,
        database=database,
        atlas_repository=atlases,
        lineage_repository=lineages,
        review_conversation_service=review_conversation_service,
        bundled_example_service=bundled_example_service,
        analyzer=analyzer,
        query_service=queries,
        policy_sources=configured_policy_sources,
        case_service=case_service,
        policy_service=policy_service,
        repository_service=repository_service,
        atlas_service=atlas_service,
        checkout_service=checkout_service,
        source_service=source_service,
        freshness_service=freshness,
        model_catalog_service=model_catalog_service,
        embedding_model_service=embedding_model_service,
        core_case_repository=core_cases,
        core_review_repository=core_reviews,
        review_workflow_service=review_workflow_service,
        checkpoint_connection=checkpoint_connection,
        core_ci_service=core_ci_service,
        standing_decision_service=standing_decision_service,
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
        OLLAMA_DESCRIPTOR,
        GOOGLE_DESCRIPTOR,
        DETERMINISTIC_DESCRIPTOR,
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
        from archcompass.analysis.adapters.mypy_resolver import MypyEdgeResolver
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
