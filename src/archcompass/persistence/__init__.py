"""Durable workspace state, stored in SQLite.

One repository per aggregate, each implementing a port and owning its own SQL: cases and
reviews and the decisions taken on them, the atlas an analysis produced, the lineage that
says which repository and branch it belongs to, the caches that stop a judgement being paid
for twice. Read `sqlite/database.py` first — it is the connection policy every one of them
shares — then `sqlite/migrations/`, which is the schema's history.
"""

from archcompass.persistence.atlases import SQLiteAtlasRepository
from archcompass.persistence.cases import SQLiteCoreCaseRepository
from archcompass.persistence.conversations import SQLiteCoreConversationRepository
from archcompass.persistence.decisions import SQLiteCoreStandingDecisionRepository
from archcompass.persistence.executions import SQLiteReviewExecutionRepository
from archcompass.persistence.findings import SQLiteCoreFindingCache
from archcompass.persistence.lineage import SQLiteLineageRepository
from archcompass.persistence.model_selection import (
    SQLiteBatchRefusalRepository,
    SQLiteCoreModelSelectionRepository,
    SQLiteEmbeddingModelSelectionRepository,
)
from archcompass.persistence.origins import SQLiteSourceOriginRepository
from archcompass.persistence.policy_sources import SQLitePolicySourceRepository
from archcompass.persistence.reviews import SQLiteCoreReviewRepository
from archcompass.persistence.scopes import SQLiteScopeSelectionRepository
from archcompass.persistence.sqlite.database import SQLiteDatabase

__all__ = [
    "SQLiteAtlasRepository",
    "SQLiteBatchRefusalRepository",
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
