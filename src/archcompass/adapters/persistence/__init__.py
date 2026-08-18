"""SQLite persistence adapters.

One repository per aggregate, each implementing a port and owning its own SQL. Read
`database.py` first — it is the connection policy every one of them shares (WAL, a busy
timeout, a connection per call) — then `migrations/`, which is the schema's history and the
only place it changes.
"""

from archcompass.adapters.persistence.atlas_repository import SQLiteAtlasRepository
from archcompass.adapters.persistence.core_conversation_repository import (
    SQLiteCoreConversationRepository,
)
from archcompass.adapters.persistence.core_finding_cache import SQLiteCoreFindingCache
from archcompass.adapters.persistence.core_model_selection_repository import (
    SQLiteCoreModelSelectionRepository,
    SQLiteEmbeddingModelSelectionRepository,
)
from archcompass.adapters.persistence.core_review_repository import (
    SQLiteCoreCaseRepository,
    SQLiteCoreReviewRepository,
    SQLiteCoreStandingDecisionRepository,
    SQLiteReviewExecutionRepository,
)
from archcompass.adapters.persistence.database import SQLiteDatabase
from archcompass.adapters.persistence.lineage_repository import SQLiteLineageRepository
from archcompass.adapters.persistence.policy_source_repository import (
    SQLitePolicySourceRepository,
)
from archcompass.adapters.persistence.scope_selection_repository import (
    SQLiteScopeSelectionRepository,
)
from archcompass.adapters.persistence.source_origin_repository import (
    SQLiteSourceOriginRepository,
)

__all__ = [
    "SQLiteAtlasRepository",
    "SQLiteCoreCaseRepository",
    "SQLiteCoreConversationRepository",
    "SQLiteCoreFindingCache",
    "SQLiteCoreModelSelectionRepository",
    "SQLiteCoreReviewRepository",
    "SQLiteCoreStandingDecisionRepository",
    "SQLiteDatabase",
    "SQLiteEmbeddingModelSelectionRepository",
    "SQLiteLineageRepository",
    "SQLitePolicySourceRepository",
    "SQLiteReviewExecutionRepository",
    "SQLiteScopeSelectionRepository",
    "SQLiteSourceOriginRepository",
]
