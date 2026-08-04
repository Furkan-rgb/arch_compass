"""What makes two judgements the same question, and what makes them different ones.

Every component of the key is here because changing it changes what the right answer is.
A component that could change without moving the key would be a boundary silently reusing
a verdict reached about something else, which is the one failure a verdict cache can have.
"""

from __future__ import annotations

from tests.reasoning_support import candidate, policies

from archcompass.domain.fingerprint import boundary_fingerprint
from archcompass.domain.verdict_cache import policy_corpus_fingerprint, verdict_cache_key


def _key(**overrides: object) -> str:
    arguments: dict[str, object] = {
        "boundary": boundary_fingerprint(candidate()),
        "policy_corpus": policy_corpus_fingerprint(policies()),
        "case_id": "case_1",
        "case_revision": 1,
        "model_identity": "fake:deterministic-architecture-v4",
        "prompt_identity": "judge-finding-candidate:v4",
    }
    arguments.update(overrides)
    return verdict_cache_key(**arguments)  # pyright: ignore[reportArgumentType]


def test_the_corpus_is_a_set_of_contents_not_an_order_of_arrival() -> None:
    """Sorted inside, so a caller that has not sorted computes the same corpus."""

    corpus = policies()
    assert policy_corpus_fingerprint(corpus) == policy_corpus_fingerprint(
        list(reversed(corpus))
    )


def test_rewording_one_policy_is_a_different_corpus() -> None:
    corpus = policies()
    edited = [
        corpus[0].model_copy(update={"content_hash": "a-different-content-hash"}),
        *corpus[1:],
    ]
    assert policy_corpus_fingerprint(corpus) != policy_corpus_fingerprint(edited)


def test_removing_a_policy_is_a_different_corpus() -> None:
    corpus = policies()
    assert policy_corpus_fingerprint(corpus) != policy_corpus_fingerprint(corpus[:-1])


def test_the_same_question_asked_twice_has_one_key() -> None:
    """Two runs, two candidate ids, two review ids — and one question."""

    assert _key() == _key()


def test_every_component_moves_the_key() -> None:
    original = _key()
    moved = {
        "boundary": _key(boundary="bdry_something_else"),
        "policy_corpus": _key(policy_corpus="corpus_something_else"),
        "case_id": _key(case_id="case_2"),
        "case_revision": _key(case_revision=2),
        "model_identity": _key(model_identity="ollama:qwen3"),
        "prompt_identity": _key(prompt_identity="judge-finding-candidate:v5"),
    }
    for component, key in moved.items():
        assert key != original, f"{component} must change what question is being asked"
    assert len(set(moved.values())) == len(moved), "no two components may collide"


def test_answering_a_question_re_asks_every_boundary() -> None:
    """The property the second pass depends on, stated as the key rather than as a run.

    An answer appends a case revision, and the revision is in the key, so nothing carries
    forward into a second pass. Moved-verdict attribution reads the difference between two
    genuine judgements; over a reused verdict it would be attributing a move to an answer
    that nothing re-weighed.
    """

    assert _key(case_revision=1) != _key(case_revision=2)
