"""What makes two judgements the same question, and what makes them different ones.

Every component of the key is here because changing it changes what the right answer is.
A component that could change without moving the key would be a boundary silently reusing
a verdict reached about something else, which is the one failure a verdict cache can have.
"""

from __future__ import annotations

from tests.reasoning_support import candidate, policies

from archcompass.domain.case import ArchitectureCase
from archcompass.domain.fingerprint import boundary_fingerprint, content_fingerprint
from archcompass.domain.verdict_cache import (
    case_fingerprint,
    policy_corpus_fingerprint,
    verdict_cache_key,
)


def _key(**overrides: object) -> str:
    arguments: dict[str, object] = {
        "boundary": boundary_fingerprint(candidate()),
        "content": content_fingerprint([("library.Store", "class Store: ...")]),
        "policy_corpus": policy_corpus_fingerprint(policies()),
        "case": "case_something",
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
        "content": _key(content="cont_something_else"),
        "policy_corpus": _key(policy_corpus="corpus_something_else"),
        "case": _key(case="case_something_else"),
        "case_revision": _key(case_revision=2),
        "model_identity": _key(model_identity="ollama:qwen3"),
        "prompt_identity": _key(prompt_identity="judge-finding-candidate:v5"),
    }
    for component, key in moved.items():
        assert key != original, f"{component} must change what question is being asked"
    assert len(set(moved.values())) == len(moved), "no two components may collide"


def test_a_rewrite_that_renames_nothing_is_a_different_question() -> None:
    """The content dimension, stated as the key: the gap the earlier key had.

    A shape fingerprint is a pattern and some participant names, so a class body rewritten in
    place moved nothing in it. Without the content term the old verdict carried for ever, and
    the advisor went on reporting a judgement about code that no longer existed.
    """

    before = content_fingerprint([("library.Store", "class Store:\n    def put(self): ...")])
    after = content_fingerprint([("library.Store", "class Store:\n    def put(self): raise")])

    assert _key(content=before) != _key(content=after)


def test_the_code_under_a_boundary_is_a_set_of_participants_not_an_order() -> None:
    """Which order a detector listed its participants in is presentation, never identity."""

    pairs = [("library.Store", "class Store: ..."), ("library.FileStore", "class F: ...")]
    assert content_fingerprint(pairs) == content_fingerprint(list(reversed(pairs)))


def test_answering_a_question_re_asks_every_boundary() -> None:
    """The property the second pass depends on, stated as the key rather than as a run.

    An answer appends a case revision *and* changes what the case says, so both terms move
    and nothing carries forward into a second pass. Moved-verdict attribution reads the
    difference between two genuine judgements; over a reused verdict it would be attributing
    a move to an answer that nothing re-weighed.
    """

    assert _key(case_revision=1) != _key(case_revision=2)


def test_a_case_is_identified_by_what_it_says_and_not_by_which_case_it_is() -> None:
    """Why `case_id` could leave the key, and what took its place.

    The id was load-bearing only while every visit minted a fresh case. Now a branch has one
    living case, and what a verdict rests on is what that case *says* — so two cases stating
    the same thing are one question, and a "start clean" that states something else is not.
    """

    stated = {
        "title": "Provider variation",
        "problem_statement": "Decide where provider-specific knowledge should live.",
    }
    one = ArchitectureCase(**stated)
    same = ArchitectureCase(**stated)
    different = one.model_copy(update={"desired_outcome": "One owner for the differences."})

    assert case_fingerprint(one) == case_fingerprint(same)
    assert case_fingerprint(one) != case_fingerprint(different)


def test_where_a_checkout_sits_is_not_what_a_case_says() -> None:
    """CI clones somewhere new every run, and the verdict is about the structure."""

    from archcompass.domain.case import RepositoryReference

    case = ArchitectureCase(title="Provider variation")
    moved = case.model_copy(
        update={"repository": RepositoryReference(root_path="/somewhere/else")}
    )

    assert case_fingerprint(case) == case_fingerprint(moved)
