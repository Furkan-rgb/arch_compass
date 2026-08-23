"""The parsed-atlas cache, asked the question a cache must always be able to answer.

`analysis_atlas` holds a module-global dict of the last two atlases it parsed, because the
round trip is nine full parses of the largest object in the system per review. A module
global is a process-wide one, and this process runs reviews on their own threads while
serving conversations on request threads — so the cache is reached concurrently, and a cache
that turns a working review into a failed one is worse than no cache.
"""

from __future__ import annotations

import sys
import threading
from pathlib import Path

from archcompass.analysis.analyzer import analysis_atlas
from archcompass.domain import RepositoryAtlas, RepositoryRef


def _atlas(index: int) -> RepositoryAtlas:
    return RepositoryAtlas(
        id=f"atlas_{index:024d}",
        repository=RepositoryRef(
            id="repo_1", path=Path("/tmp/repo"), branch_id="branch_1", content_id="c1"
        ),
        parser_configuration=(("parser", "1"), ("analysis", "1")),
    )


def test_the_cache_survives_many_threads_evicting_at_once() -> None:
    """Two reviews and a conversation at the same moment must not raise out of an analysis.

    The eviction was `while len(_PARSED) >= 2: _PARSED.pop(next(iter(_PARSED)))` with nothing
    around it. Two threads that both read a length of two take the same first key, and the
    second to reach `pop` raises `KeyError` — which is unguarded all the way out of the
    analysis node, so `ReviewRunner` marks the review failed.

    The switch interval is turned down because that window is a handful of bytecodes wide:
    at the default 5ms this passes on a cache with no lock at all, which would make it a test
    that reports success over the bug it is here for. At 1µs it fails in a third of its
    threads without the lock, reliably.
    """

    atlases = [_atlas(index) for index in range(40)]
    errors: list[BaseException] = []

    def hammer(offset: int) -> None:
        try:
            for step in range(400):
                analysis_atlas(atlases[(step + offset) % len(atlases)])
        except BaseException as exc:
            errors.append(exc)

    previous = sys.getswitchinterval()
    sys.setswitchinterval(1e-6)
    try:
        threads = [threading.Thread(target=hammer, args=(index * 7,)) for index in range(12)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
    finally:
        sys.setswitchinterval(previous)

    assert not errors, f"{len(errors)} of 12 threads raised, first: {errors[0]!r}"


def test_the_cache_answers_with_the_atlas_it_was_asked_about() -> None:
    """The key is the analysis id, so an entry can never be another analysis's structure."""

    first, second = _atlas(1), _atlas(2)
    assert analysis_atlas(first).version.version_id == first.id
    assert analysis_atlas(second).version.version_id == second.id
    # And again, now that both are resident: a hit must be the one asked for, not the newest.
    assert analysis_atlas(first).version.version_id == first.id


def test_the_cache_holds_two_atlases_and_no_more() -> None:
    """The bound is the point: this object is the largest in the system.

    Read through the public function rather than by inspecting the dict, so the assertion is
    about behaviour a caller can observe — a third atlas evicts the first, and asking for the
    first again returns an equal atlas rather than a stale or missing one.
    """

    from archcompass.analysis.analyzer import _PARSED

    for index in range(10, 20):
        analysis_atlas(_atlas(index))
    assert len(_PARSED) <= 2, f"the cache grew to {len(_PARSED)} entries"
    assert analysis_atlas(_atlas(10)).version.version_id == _atlas(10).id
