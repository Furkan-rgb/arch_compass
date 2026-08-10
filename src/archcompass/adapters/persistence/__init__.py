"""SQLite persistence adapters.

One repository per aggregate, each implementing a port and owning its own SQL. Read
`database.py` first — it is the connection policy every one of them shares (WAL, a busy
timeout, a connection per call) — then `migrations/`, which is the schema's history and the
only place it changes.
"""

from archcompass.adapters.persistence.atlas_repository import SQLiteAtlasRepository
from archcompass.adapters.persistence.boundary_line_repository import (
    SQLiteBoundaryLineRepository,
)
from archcompass.adapters.persistence.case_repository import SQLiteCaseRepository
from archcompass.adapters.persistence.database import SQLiteDatabase
from archcompass.adapters.persistence.lineage_repository import SQLiteLineageRepository
from archcompass.adapters.persistence.model_selection_repository import (
    SQLiteReasoningModelSelectionRepository,
)
from archcompass.adapters.persistence.policy_source_repository import (
    SQLitePolicySourceRepository,
)
from archcompass.adapters.persistence.review_conversation_repository import (
    SQLiteReviewConversationRepository,
)
from archcompass.adapters.persistence.review_repository import SQLiteBoundaryReviewRepository
from archcompass.adapters.persistence.scope_selection_repository import (
    SQLiteScopeSelectionRepository,
)
from archcompass.adapters.persistence.source_origin_repository import (
    SQLiteSourceOriginRepository,
)
from archcompass.adapters.persistence.standing_decision_repository import (
    SQLiteStandingDecisionRepository,
)
from archcompass.adapters.persistence.verdict_cache_repository import (
    SQLiteVerdictCacheRepository,
)

__all__ = [
    "SQLiteAtlasRepository",
    "SQLiteBoundaryLineRepository",
    "SQLiteBoundaryReviewRepository",
    "SQLiteCaseRepository",
    "SQLiteDatabase",
    "SQLiteLineageRepository",
    "SQLitePolicySourceRepository",
    "SQLiteReasoningModelSelectionRepository",
    "SQLiteReviewConversationRepository",
    "SQLiteScopeSelectionRepository",
    "SQLiteSourceOriginRepository",
    "SQLiteStandingDecisionRepository",
    "SQLiteVerdictCacheRepository",
]
