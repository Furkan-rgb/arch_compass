from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterator
from dataclasses import dataclass, replace
from pathlib import Path

import pytest

from archcompass.domain import (
    ArchitectureCase,
    Candidate,
    Finding,
    Participant,
    RecordedInvestigation,
    RepositoryAtlas,
    RepositoryRef,
    RetrievalProvenance,
    Review,
    ReviewDelta,
    ReviewStatus,
    Verdict,
)
from archcompass.domain._support import utc_now
from archcompass.persistence.findings import SQLiteCoreFindingCache
from archcompass.persistence.reviews import SQLiteCoreReviewRepository
from archcompass.persistence.sqlite.codecs import DataclassRecordCodec
from archcompass.ports.capabilities import ReviewedSubject
from archcompass.ports.policy_retrieval import RetrievedPolicySet
from archcompass.reasoning.cache import CachingArchitectureJudge, CachingReviewRecorder


def _stamped(repository: RepositoryRef) -> RepositoryAtlas:
    """An atlas with no structure in it but with the provenance every atlas carries.

    `parser_configuration` is not decoration. Reading an atlas back needs it, and one that
    does not name the parser that built it is now refused outright rather than handed a
    placeholder — the placeholder could never equal a live parser version, so it made a
    freshness check fail for ever and no re-index could clear it. These bounds are about the
    finding cache, so the fixture states the provenance once and says nothing more about it.
    """

    return RepositoryAtlas(
        "atlas",
        repository,
        parser_configuration=(("parser", "test-parser"), ("analysis", "test-config")),
    )


def test_cache_hit_names_the_review_that_first_recorded_the_finding(
    tmp_path: Path,
) -> None:
    database = tmp_path / "cache.db"

    def connect() -> sqlite3.Connection:
        return sqlite3.connect(database)

    cache = SQLiteCoreFindingCache(connect)
    reviews = SQLiteCoreReviewRepository(connect)
    recorder = CachingReviewRecorder(reviews, cache)
    repository = RepositoryRef("repo", tmp_path, "branch", "content")
    atlas = _stamped(repository)
    case = ArchitectureCase.create()
    candidate = Candidate.identified(
        pattern="sole_implementation",
        summary="Port has one implementation",
        participants=(Participant("Port", "interface"),),
    )
    finding = Finding(candidate, Verdict.CLEARED, "No conflict.", (), ())
    now = utc_now()
    review = Review(
        "review-source",
        1,
        repository,
        atlas,
        case,
        (finding,),
        (),
        ReviewStatus.COMPLETED,
        ReviewDelta(new=(candidate,)),
        now,
        now,
    )

    cached = cache.put("key", finding)
    recorder.record(replace(review, findings=(cached,)))

    reused = cache.get("key")
    assert reused is not None
    assert reused.cache_key == "key"
    assert reused.reused_from_review_id == review.id


def test_a_review_attaches_itself_to_a_finding_it_revised_after_caching_it(
    tmp_path: Path,
) -> None:
    """A settled hinge is the same judgement, so the cached row is still its source.

    The join used to be the finding's whole encoded document, which held only while
    nothing revised a finding between caching it and recording it. A second pass that
    settles a hinge does exactly that, and the row it no longer matched was the row
    holding the provenance every later reuse reads.
    """

    database = tmp_path / "cache.db"

    def connect() -> sqlite3.Connection:
        return sqlite3.connect(database)

    cache = SQLiteCoreFindingCache(connect)
    reviews = SQLiteCoreReviewRepository(connect)
    recorder = CachingReviewRecorder(reviews, cache)
    repository = RepositoryRef("repo", tmp_path, "branch", "content")
    atlas = _stamped(repository)
    case = ArchitectureCase.create()
    candidate = Candidate.identified(
        pattern="sole_implementation",
        summary="Port has one implementation",
        participants=(Participant("Port", "interface"),),
    )
    judged = Finding(
        candidate,
        Verdict.HELD,
        "Held pending intent.",
        (),
        (),
        hinge="whether the seam is deliberate",
    )
    # Cached first, then revised, in that order — which is the order production runs in, and
    # the reason the revision keeps its row. `cache.put` returns the finding carrying the key
    # it was filed under, `replace` carries that key through every later edit, and the review
    # therefore arrives at `record_sources` still holding the only thing it is matched on.
    settled = replace(
        cache.put("key", judged),
        verdict=Verdict.CLEARED,
        reasoning="The repository shows one implementation and no second caller.",
        hinge=None,
        investigation_identity="investigation-1",
    )
    now = utc_now()
    review = Review(
        "review-source",
        1,
        repository,
        atlas,
        case,
        (settled,),
        (),
        ReviewStatus.COMPLETED,
        ReviewDelta(new=(candidate,)),
        now,
        now,
    )

    recorder.record(review)

    reused = cache.get("key")
    assert reused is not None
    assert reused.reused_from_review_id == review.id


def test_which_endpoint_served_a_finding_is_not_part_of_what_it_was_asked(
    tmp_path: Path,
) -> None:
    """A judgement re-routed by the gateway is still the same judgement.

    `served_by` names the endpoint that answered, and a gateway balancing its load moves it
    between one review and the next with nothing about the question having changed. Two
    thing must therefore not read it: `CachingArchitectureJudge.key`, which decides both
    whether a verdict may be reused and — since the key is also the row's identity — which
    row a review attaches itself to.

    The second half is the one with teeth. A route that moved the key would move the row a
    review can claim, so the reuse would go on working and the provenance beside it would
    silently stop being recorded. That is the same failure mode as the prompt-identity defect
    this field was added while fixing, and it would arrive the first time OpenRouter answered
    from a second endpoint. This test now proves it over one value rather than two, which is
    the point of there being one.
    """

    database = tmp_path / "cache.db"

    def connect() -> sqlite3.Connection:
        return sqlite3.connect(database)

    cache = SQLiteCoreFindingCache(connect)
    reviews = SQLiteCoreReviewRepository(connect)
    recorder = CachingReviewRecorder(reviews, cache)
    repository = RepositoryRef("repo", tmp_path, "branch", "content")
    atlas = _stamped(repository)
    case = ArchitectureCase.create()
    candidate = Candidate.identified(
        pattern="sole_implementation",
        summary="Port has one implementation",
        participants=(Participant("Port", "interface"),),
    )
    cached = cache.put(
        "key",
        Finding(
            candidate, Verdict.CLEARED, "No conflict.", (), (), served_by="Google AI Studio"
        ),
    )
    now = utc_now()
    review = Review(
        "review-source",
        1,
        repository,
        atlas,
        case,
        (replace(cached, served_by="Vertex"),),
        (),
        ReviewStatus.COMPLETED,
        ReviewDelta(new=(candidate,)),
        now,
        now,
    )

    recorder.record(review)

    reused = cache.get("key")
    assert reused is not None
    assert reused.reused_from_review_id == review.id


def test_a_finding_stored_before_the_route_was_recorded_still_reads(
    tmp_path: Path,
) -> None:
    """148 findings in this workspace were written without the field, and they must open.

    A review is immutable and somebody will open one. Nothing backfills these — no route was
    observed when they were judged, so there is no value to backfill *to*, and inventing one
    would put a claim about where a verdict came from into a record that never made it. The
    empty string is the honest reading and it is what the domain default gives.

    Written here as the raw document rather than through the codec, because what is being
    checked is precisely that a document with no `served_by` key decodes at all.
    """

    database = tmp_path / "cache.db"

    def connect() -> sqlite3.Connection:
        return sqlite3.connect(database)

    cache = SQLiteCoreFindingCache(connect)
    candidate = Candidate.identified(
        pattern="sole_implementation",
        summary="Port has one implementation",
        participants=(Participant("Port", "interface"),),
    )
    stored = json.loads(
        DataclassRecordCodec(Finding).encode(
            Finding(candidate, Verdict.CLEARED, "No conflict.", (), ())
        )
    )
    del stored["served_by"]
    with connect() as connection:
        connection.execute(
            "INSERT INTO core_finding_cache(cache_key, finding_json) VALUES (?, ?)",
            ("older-row", json.dumps(stored)),
        )

    reused = cache.get("older-row")

    assert reused is not None
    assert reused.served_by == ""


def test_a_review_stored_before_the_route_was_recorded_still_opens(
    tmp_path: Path,
) -> None:
    """The same tolerance on the record somebody actually opens, which is the review.

    The test above proves a *cached* document decodes without the key. That is the row a
    later review may reuse; it is not the row a person reads. All 148 of this workspace's
    findings also live inside seven `core_review_snapshots` documents, and a review is
    immutable — nothing rewrites those, and the only thing standing between them and an
    `UnreadableStoredRecordError` on every page that opens one is the field having a
    default. A field that breaks reading an old record is worse than no field, and the
    nesting is what makes it worth asserting twice: the finding is validated as part of a
    much larger document here, by an adapter built for `Review` rather than for `Finding`.

    The key is stripped from the stored document rather than the field being left unset,
    because an encoder that has the field always writes it. What has to decode is the shape
    that is on disk right now.
    """

    database = tmp_path / "reviews.db"

    def connect() -> sqlite3.Connection:
        return sqlite3.connect(database)

    reviews = SQLiteCoreReviewRepository(connect)
    repository = RepositoryRef("repo", tmp_path, "branch", "content")
    atlas = _stamped(repository)
    candidate = Candidate.identified(
        pattern="sole_implementation",
        summary="Port has one implementation",
        participants=(Participant("Port", "interface"),),
    )
    now = utc_now()
    review = Review(
        "review-before-the-field",
        1,
        repository,
        atlas,
        ArchitectureCase.create(),
        (Finding(candidate, Verdict.CLEARED, "No conflict.", (), ()),),
        (),
        ReviewStatus.COMPLETED,
        ReviewDelta(new=(candidate,)),
        now,
        now,
    )
    stored = json.loads(DataclassRecordCodec(Review).encode(review))
    for finding in stored["findings"]:
        del finding["served_by"]
    with connect() as connection:
        connection.execute(
            """
            INSERT INTO core_review_snapshots(
                review_id, repository_id, branch_id, sequence, round, status, review_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                review.id,
                repository.id,
                repository.branch_id,
                review.sequence,
                review.round,
                review.status.value,
                json.dumps(stored),
            ),
        )

    opened = reviews.get(review.id)

    assert [finding.served_by for finding in opened.findings] == [""]


def test_the_route_survives_being_stored_on_a_review_and_read_back(
    tmp_path: Path,
) -> None:
    """And the field is worth nothing unless it comes back out again.

    The pair to the test above: absent decodes as empty, and present decodes as what was
    written. Both go through `SQLiteCoreReviewRepository`, because the review snapshot is
    where a judgement's provenance is read from months later — the finding cache is an
    optimisation and may be cold, but the review is the durable record the charter's "say
    where it came from" is a promise about.
    """

    database = tmp_path / "reviews.db"

    def connect() -> sqlite3.Connection:
        return sqlite3.connect(database)

    reviews = SQLiteCoreReviewRepository(connect)
    repository = RepositoryRef("repo", tmp_path, "branch", "content")
    atlas = _stamped(repository)
    candidate = Candidate.identified(
        pattern="sole_implementation",
        summary="Port has one implementation",
        participants=(Participant("Port", "interface"),),
    )
    now = utc_now()
    review = Review(
        "review-with-a-route",
        1,
        repository,
        atlas,
        ArchitectureCase.create(),
        (
            Finding(
                candidate,
                Verdict.CLEARED,
                "No conflict.",
                (),
                (),
                served_by="Google AI Studio,Vertex",
            ),
        ),
        (),
        ReviewStatus.COMPLETED,
        ReviewDelta(new=(candidate,)),
        now,
        now,
    )

    reviews.record(review)

    assert reviews.get(review.id).findings[0].served_by == "Google AI Studio,Vertex"


class _FixedJudge:
    """A judge that answers whatever it is asked, so the key is the only thing under test."""

    def __init__(self, verdicts: Iterator[Verdict]) -> None:
        self._verdicts = verdicts

    def judge(
        self,
        candidate: Candidate,
        case: ArchitectureCase,
        policies: RetrievedPolicySet,
        investigation: RecordedInvestigation | None = None,
        *,
        subject: ReviewedSubject | None = None,
    ) -> Finding:
        del case, policies, investigation, subject
        return Finding(candidate, next(self._verdicts), "Judged.", (), ())


@dataclass(frozen=True)
class _InForce:
    """The two stamps the key reads, held still, so the case is the only term that moves."""

    model_identity: str = "fake:model:thinking=None"
    prompt_identity: str = "judge:test-v1"


def _cached_judge(
    cache: SQLiteCoreFindingCache, *verdicts: Verdict
) -> CachingArchitectureJudge:
    return CachingArchitectureJudge(
        _FixedJudge(iter(verdicts)), cache, selection=_InForce
    )


def _review(
    review_id: str,
    repository: RepositoryRef,
    case: ArchitectureCase,
    finding: Finding,
) -> Review:
    now = utc_now()
    return Review(
        review_id,
        1,
        repository,
        _stamped(repository),
        case,
        (finding,),
        (),
        ReviewStatus.COMPLETED,
        ReviewDelta(new=(finding.candidate,)),
        now,
        now,
    )


def test_two_cases_are_two_judgements_and_each_keeps_its_own_review(
    tmp_path: Path,
) -> None:
    """The defect, end to end: one candidate, two cases, two rows, two reviews.

    This is what was measured rather than inferred. The cache key carries the
    `ArchitectureCase`; the second hash that `record_sources` used to join on was built from
    the stamps a finding carries, and a finding does not record its case. So a candidate
    re-judged after a question was answered wrote a second row under a second key and a
    *first* identity — 231 rows in the workspace that found it, 137 with an identity, 124
    distinct. Thirteen pairs, three of them holding different verdicts, and the update said
    `AND source_review_id IS NULL`, so whichever review recorded first took both rows.

    Nothing here reaches a provider: the judge answers from a list, which is enough because
    what is under test is which row each answer lands in.
    """

    database = tmp_path / "cache.db"

    def connect() -> sqlite3.Connection:
        return sqlite3.connect(database)

    cache = SQLiteCoreFindingCache(connect)
    reviews = SQLiteCoreReviewRepository(connect)
    recorder = CachingReviewRecorder(reviews, cache)
    repository = RepositoryRef("repo", tmp_path, "branch", "content")
    candidate = Candidate.identified(
        pattern="sole_implementation",
        summary="Port has one implementation",
        participants=(Participant("Port", "interface"),),
    )
    policies = RetrievedPolicySet(
        str(candidate.id),
        (),
        RetrievalProvenance(candidate.id, "test", "1", "corpus", ()),
    )
    asked = ArchitectureCase.create()
    answered = asked.open_revision()
    judge = _cached_judge(cache, Verdict.HELD, Verdict.CLEARED)

    held = judge.judge(candidate, asked, policies)
    cleared = judge.judge(candidate, answered, policies)
    recorder.record(_review("review-asked", repository, asked, held))
    recorder.record(_review("review-answered", repository, answered, cleared))

    assert held.verdict is Verdict.HELD
    assert cleared.verdict is Verdict.CLEARED
    assert held.cache_key != cleared.cache_key
    first = cache.get(held.cache_key)
    second = cache.get(cleared.cache_key)
    assert first is not None and second is not None
    assert first.verdict is Verdict.HELD
    assert second.verdict is Verdict.CLEARED
    assert first.reused_from_review_id == "review-asked"
    assert second.reused_from_review_id == "review-answered"


def test_the_key_is_never_written_into_the_document_it_keys(tmp_path: Path) -> None:
    """One value, in one place, and the place is the primary key.

    The whole mechanism is that `cache_key` is carried rather than computed, and a copy of
    it inside `finding_json` would be a computed second copy in everything but name: it
    would be written by one code path, read by another, and free to disagree the moment a
    row was rewritten under a different key. This is the assertion that stops a later reader
    from "helpfully" storing it, and it fails loudly if they do.
    """

    database = tmp_path / "cache.db"

    def connect() -> sqlite3.Connection:
        return sqlite3.connect(database)

    cache = SQLiteCoreFindingCache(connect)
    candidate = Candidate.identified(
        pattern="sole_implementation",
        summary="Port has one implementation",
        participants=(Participant("Port", "interface"),),
    )
    carrying = Finding(
        candidate, Verdict.CLEARED, "No conflict.", (), (), cache_key="some-other-key"
    )

    stored = cache.put("key", carrying)

    with connect() as connection:
        document = json.loads(
            connection.execute(
                "SELECT finding_json FROM core_finding_cache WHERE cache_key = ?", ("key",)
            ).fetchone()[0]
        )
    assert document["cache_key"] == ""
    assert stored.cache_key == "key"


def test_a_row_written_before_the_key_was_carried_is_still_claimed(
    tmp_path: Path,
) -> None:
    """231 rows in the workspace predate this field, and none of them are lost.

    The key recipe has not moved, so every one of those rows can still be hit. What they do
    not have is the key inside their stored document — and they must not need it. `get`
    stamps the finding with the key it was looked up by, which is why an old row rejoins the
    provenance record the first time it is reused rather than staying unattributed for ever.

    The document is written by hand with the field stripped, because what is being checked
    is precisely the shape that is on disk right now.
    """

    database = tmp_path / "cache.db"

    def connect() -> sqlite3.Connection:
        return sqlite3.connect(database)

    cache = SQLiteCoreFindingCache(connect)
    reviews = SQLiteCoreReviewRepository(connect)
    recorder = CachingReviewRecorder(reviews, cache)
    repository = RepositoryRef("repo", tmp_path, "branch", "content")
    candidate = Candidate.identified(
        pattern="sole_implementation",
        summary="Port has one implementation",
        participants=(Participant("Port", "interface"),),
    )
    stored = json.loads(
        DataclassRecordCodec(Finding).encode(
            Finding(candidate, Verdict.CLEARED, "No conflict.", (), ())
        )
    )
    del stored["cache_key"]
    with connect() as connection:
        connection.execute(
            "INSERT INTO core_finding_cache(cache_key, finding_json) VALUES (?, ?)",
            ("older-row", json.dumps(stored)),
        )

    reused = cache.get("older-row")
    assert reused is not None
    assert reused.cache_key == "older-row"
    recorder.record(
        _review("review-later", repository, ArchitectureCase.create(), reused)
    )

    claimed = cache.get("older-row")
    assert claimed is not None
    assert claimed.reused_from_review_id == "review-later"


def test_the_key_survives_a_review_being_stored_and_read_back(tmp_path: Path) -> None:
    """The join has to cross a process boundary, because a review does.

    A review that asks a question stops, waits for a person, and finishes in whatever
    process happens to resume it. `record_sources` runs each time that review is recorded,
    so the key it matches on has to come back out of `review_json` — an in-memory stamp
    would work in every test and lose the row on the one path that matters.
    """

    database = tmp_path / "reviews.db"

    def connect() -> sqlite3.Connection:
        return sqlite3.connect(database)

    reviews = SQLiteCoreReviewRepository(connect)
    repository = RepositoryRef("repo", tmp_path, "branch", "content")
    candidate = Candidate.identified(
        pattern="sole_implementation",
        summary="Port has one implementation",
        participants=(Participant("Port", "interface"),),
    )
    review = _review(
        "review-with-a-key",
        repository,
        ArchitectureCase.create(),
        Finding(candidate, Verdict.CLEARED, "No conflict.", (), (), cache_key="the-key"),
    )

    reviews.record(review)

    assert reviews.get(review.id).findings[0].cache_key == "the-key"


def test_the_second_identity_column_is_dropped_from_a_database_that_has_one(
    tmp_path: Path,
) -> None:
    """The column goes, so that nothing can quietly start writing a second hash into it.

    A dead column named `finding_identity` sitting beside `cache_key` is an invitation, and
    this class of defect has come back twice already. The real workspace has one with 137
    values in it, of which only 124 are distinct — so this also proves the drop runs against
    a database that predates it rather than only against a fresh one.
    """

    database = tmp_path / "old.db"

    def connect() -> sqlite3.Connection:
        return sqlite3.connect(database)

    with connect() as connection:
        connection.execute(
            """
            CREATE TABLE core_finding_cache (
                cache_key TEXT PRIMARY KEY,
                finding_json TEXT NOT NULL,
                source_review_id TEXT,
                finding_identity TEXT
            )
            """
        )
        connection.execute(
            "INSERT INTO core_finding_cache VALUES (?, ?, ?, ?)",
            ("kept", "{}", "review-old", "an-identity"),
        )

    SQLiteCoreFindingCache(connect)

    with connect() as connection:
        columns = {
            str(row[1])
            for row in connection.execute("PRAGMA table_info(core_finding_cache)")
        }
        surviving = connection.execute(
            "SELECT cache_key, source_review_id FROM core_finding_cache"
        ).fetchall()
    assert "finding_identity" not in columns
    assert surviving == [("kept", "review-old")]


def test_a_sqlite_too_old_to_drop_a_column_opens_the_cache_anyway(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`DROP COLUMN` needs SQLite 3.35, and nothing installable can promise one.

    `sqlite3` is the standard library bound to whatever `libsqlite3` the interpreter was
    linked against, so the version is a property of the machine rather than of the lockfile.
    Unguarded, the only `DROP COLUMN` in this repository would therefore raise on the first
    line of the finding cache on an older system library — which is every process that opens
    a workspace, before a review can be read. A dead column is survivable; that is not.

    So this asserts both halves of what the guard promises. On the old library the column
    survives and the cache is fully usable over it — a finding is written, claimed by a
    review and read back with its provenance, which is the whole contract this class has.
    Then the same database is opened by a library that does know the statement, and the
    column goes: the drop is deferred rather than abandoned, because it is re-checked on
    every open. The rows the old library wrote survive that with their keys and their
    attribution, which is the part a one-way migration would have had to promise and could
    not.

    The version is faked rather than the library downgraded, so what is proved here is that
    the branch turns on the version and that the branch it takes leaves a working cache. It
    is not proof that 3.34 refuses the statement — that is SQLite's own release history, and
    no test in this process can stand in for it.
    """

    database = tmp_path / "old.db"

    def connect() -> sqlite3.Connection:
        return sqlite3.connect(database)

    with connect() as connection:
        connection.execute(
            """
            CREATE TABLE core_finding_cache (
                cache_key TEXT PRIMARY KEY,
                finding_json TEXT NOT NULL,
                source_review_id TEXT,
                finding_identity TEXT
            )
            """
        )
        connection.execute(
            "INSERT INTO core_finding_cache VALUES (?, ?, ?, ?)",
            ("kept", "{}", "review-old", "an-identity"),
        )

    monkeypatch.setattr(sqlite3, "sqlite_version_info", (3, 34, 0))
    cache = SQLiteCoreFindingCache(connect)
    recorder = CachingReviewRecorder(SQLiteCoreReviewRepository(connect), cache)
    repository = RepositoryRef("repo", tmp_path, "branch", "content")
    candidate = Candidate.identified(
        pattern="sole_implementation",
        summary="Port has one implementation",
        participants=(Participant("Port", "interface"),),
    )
    written = cache.put(
        "written-by-an-old-library",
        Finding(candidate, Verdict.CLEARED, "No conflict.", (), ()),
    )
    recorder.record(
        _review("review-new", repository, ArchitectureCase.create(), written)
    )

    with connect() as connection:
        columns = {
            str(row[1])
            for row in connection.execute("PRAGMA table_info(core_finding_cache)")
        }
    claimed = cache.get("written-by-an-old-library")
    assert "finding_identity" in columns, "the drop must be skipped, not attempted"
    assert claimed is not None
    assert claimed.reused_from_review_id == "review-new"

    monkeypatch.undo()
    SQLiteCoreFindingCache(connect)

    with connect() as connection:
        columns = {
            str(row[1])
            for row in connection.execute("PRAGMA table_info(core_finding_cache)")
        }
        surviving = connection.execute(
            "SELECT cache_key, source_review_id FROM core_finding_cache ORDER BY cache_key"
        ).fetchall()
    assert "finding_identity" not in columns
    assert surviving == [("kept", "review-old"), ("written-by-an-old-library", "review-new")]
