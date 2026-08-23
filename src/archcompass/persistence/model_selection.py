"""Reasoning-model selection stored in the application database."""

from __future__ import annotations

from datetime import datetime, timedelta

from archcompass.persistence.sqlite.database import Transaction
from archcompass.reasoning.records import (
    EmbeddingModelSelection,
    ReasoningModelSelection,
)
from archcompass.reasoning.refusals import fingerprint_key
from archcompass.records import THINKING_LEVELS, ThinkingMode, utc_now


def _thinking(stored: object) -> ThinkingMode:
    """A stored thinking mode, back in the shape it was chosen in.

    Two shapes go into one column and they have to come out told apart: a switch was stored
    as 1 or 0 and a level as the word itself. Reading a level back would otherwise depend on
    how a union happens to coerce, and a row written by an older build — where every mode
    was forced through `int()` — still reads as the switch it was.

    Anything else is treated as no mode at all rather than raised on. A selection is a
    preference, and the honest failure for one that cannot be read is the model's own
    default, not a workspace that will not open.
    """

    if stored is None:
        return None
    if isinstance(stored, bool):
        return stored
    if isinstance(stored, int):
        return bool(stored)
    if isinstance(stored, str) and stored in THINKING_LEVELS:
        return stored  # type: ignore[return-value]
    return None


class SQLiteCoreModelSelectionRepository:
    def __init__(self, transaction: Transaction) -> None:
        self._transaction = transaction
        with self._transaction() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS core_reasoning_model_choice (
                    id INTEGER PRIMARY KEY CHECK(id = 1),
                    provider TEXT NOT NULL,
                    model TEXT NOT NULL,
                    -- `ThinkingMode` is two shapes, not one: a switch, which every column
                    -- here was built for, and a level — `minimal`/`low`/`medium`/`high` —
                    -- which Gemini 3 has instead of a switch. The declaration says INTEGER
                    -- because that is what shipped, and SQLite stores what it is given
                    -- regardless: a level is kept as text, a switch as 1 or 0. `_thinking`
                    -- below is the one place the two are told apart on the way back.
                    thinking INTEGER,
                    selected_at TEXT NOT NULL,
                    failed_at TEXT,
                    failure_detail TEXT NOT NULL DEFAULT '',
                    input_token_limit INTEGER,
                    output_token_limit INTEGER
                )
                """
            )

    def get(self) -> ReasoningModelSelection | None:
        with self._transaction() as connection:
            row = connection.execute(
                "SELECT provider, model, thinking, selected_at, failed_at, "
                "failure_detail, input_token_limit, output_token_limit "
                "FROM core_reasoning_model_choice WHERE id = 1"
            ).fetchone()
        if row is None:
            return None
        stored = dict(row)
        stored["thinking"] = _thinking(stored["thinking"])
        return ReasoningModelSelection.model_validate(stored)

    def set(self, selection: ReasoningModelSelection) -> ReasoningModelSelection:
        with self._transaction() as connection:
            connection.execute(
                """
                INSERT INTO core_reasoning_model_choice(
                    id, provider, model, thinking, selected_at, failed_at,
                    failure_detail, input_token_limit, output_token_limit
                ) VALUES (1, ?, ?, ?, ?, NULL, '', ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    provider=excluded.provider, model=excluded.model,
                    thinking=excluded.thinking, selected_at=excluded.selected_at,
                    failed_at=NULL, failure_detail='',
                    input_token_limit=excluded.input_token_limit,
                    output_token_limit=excluded.output_token_limit
                """,
                (
                    selection.provider,
                    selection.model,
                    # Verbatim. This used to be `int(selection.thinking)`, which was written
                    # when a thinking mode could only be a switch and which raises on every
                    # Gemini 3 model — `int("high")` is a `ValueError`, and choosing one in
                    # the picker answered 500. sqlite3 stores a bool as 1 or 0 and a level
                    # as the word itself, which is exactly what is wanted.
                    selection.thinking,
                    selection.selected_at.isoformat(),
                    selection.input_token_limit,
                    selection.output_token_limit,
                ),
            )
        stored = self.get()
        assert stored is not None
        return stored

    def clear(self) -> None:
        with self._transaction() as connection:
            connection.execute("DELETE FROM core_reasoning_model_choice WHERE id = 1")

    def record_failure(self, detail: str) -> None:
        with self._transaction() as connection:
            connection.execute(
                "UPDATE core_reasoning_model_choice SET failed_at = ?, "
                "failure_detail = ? WHERE id = 1",
                (utc_now().isoformat(), detail),
            )

    def clear_failure(self) -> None:
        with self._transaction() as connection:
            connection.execute(
                "UPDATE core_reasoning_model_choice SET failed_at = NULL, "
                "failure_detail = '' WHERE id = 1"
            )


class SQLiteEmbeddingModelSelectionRepository:
    """The independently selected policy-embedding model."""

    def __init__(self, transaction: Transaction) -> None:
        self._transaction = transaction
        with self._transaction() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS embedding_model_choice (
                    id INTEGER PRIMARY KEY CHECK(id = 1),
                    provider TEXT NOT NULL,
                    model TEXT NOT NULL,
                    dimensions INTEGER NOT NULL,
                    selected_at TEXT NOT NULL
                )
                """
            )

    def get(self) -> EmbeddingModelSelection | None:
        with self._transaction() as connection:
            row = connection.execute(
                "SELECT provider, model, dimensions, selected_at "
                "FROM embedding_model_choice WHERE id = 1"
            ).fetchone()
        return None if row is None else EmbeddingModelSelection.model_validate(dict(row))

    def set(self, selection: EmbeddingModelSelection) -> EmbeddingModelSelection:
        with self._transaction() as connection:
            connection.execute(
                """
                INSERT INTO embedding_model_choice(
                    id, provider, model, dimensions, selected_at
                ) VALUES (1, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    provider=excluded.provider,
                    model=excluded.model,
                    dimensions=excluded.dimensions,
                    selected_at=excluded.selected_at
                """,
                (
                    selection.provider,
                    selection.model,
                    selection.dimensions,
                    selection.selected_at.isoformat(),
                ),
            )
        stored = self.get()
        assert stored is not None
        return stored

    def clear(self) -> None:
        with self._transaction() as connection:
            connection.execute("DELETE FROM embedding_model_choice WHERE id = 1")


#: How long a refusal is taken at its word before the provider is asked again.
#:
#: An operational policy rather than anything the architecture implies, and the interval is
#: the least interesting part of it: what matters is that a refusal is no longer permanent.
#: A week is chosen because enabling billing is rare and deliberate, and the cost of being
#: wrong is one submission refused again — the same single wasted call a refusal already
#: costs — against a workspace that silently judges everything the expensive way for ever.
_REFUSAL_HOLDS_FOR = timedelta(days=7)


class SQLiteBatchRefusalRepository:
    """Keys the provider's batch facility has turned away, remembered for a while.

    `400 FAILED_PRECONDITION` from the Gemini Batch API is a fact about the project behind
    the key: it is not eligible, and it will not be eligible tomorrow because the process
    restarted. Holding that only in memory cost a rejected submission on the first review of
    every session, and — worse — a review that told its reader it had queued a batch while
    it judged every candidate interactively.

    Remembered for a while rather than for ever. Eligibility is a property of the project
    and a project can gain it — somebody enables billing — and nothing about that reaches
    this process. So the row carries when it was observed and stops matching once it is old,
    which is the only way a workspace recovers without hand-written SQL.

    What is stored is a fingerprint, never the key. This has to answer "was this one
    refused", and nothing here has any business being able to reproduce a credential.
    """

    def __init__(self, transaction: Transaction) -> None:
        self._transaction = transaction
        with self._transaction() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS batch_refusal (
                    key_fingerprint TEXT PRIMARY KEY,
                    refused_at TEXT NOT NULL
                )
                """
            )

    def refused(self, api_key: str) -> bool:
        """Whether this key was refused recently enough for the answer to still hold.

        A stored refusal is an observation, not a verdict: on a day in the past, the batch
        API would not take a submission from this project. It was read as permanent, and
        `refused_at` was written and never looked at — so a project that enabled billing
        judged every review interactively for ever, paying per-candidate metering the batch
        tier would have halved, with nothing on screen to say why. The only recovery was
        SQL against this table by hand.

        Reading the timestamp is what makes a stale row stop matching on its own. The cost
        of being wrong is one submission occasionally refused again, which is what a refusal
        already costs once; the cost of never revisiting it is permanent silent degradation.
        """

        with self._transaction() as connection:
            row = connection.execute(
                "SELECT refused_at FROM batch_refusal WHERE key_fingerprint = ?",
                (fingerprint_key(api_key),),
            ).fetchone()
        if row is None:
            return False
        try:
            refused_at = datetime.fromisoformat(str(row[0]))
        except ValueError:
            # A row this build cannot read is not a reason to keep refusing. Asking again
            # costs one submission; refusing on an unparseable timestamp costs every review.
            return False
        return utc_now() - refused_at < _REFUSAL_HOLDS_FOR

    def record(self, api_key: str) -> None:
        """Note that this key was refused now, replacing whatever was noted before.

        `INSERT OR REPLACE` is what refreshes the observation: a key refused again today is
        refused as of today, not as of the first time. The row is per credential
        fingerprint, so the table is bounded by the number of credentials this workspace has
        seen — expired rows are left alone rather than swept, because the next refusal
        updates the one that is already there.
        """

        with self._transaction() as connection:
            connection.execute(
                "INSERT OR REPLACE INTO batch_refusal(key_fingerprint, refused_at) "
                "VALUES (?, ?)",
                (fingerprint_key(api_key), utc_now().isoformat()),
            )
