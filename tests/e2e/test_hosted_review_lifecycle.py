"""A whole review against a real model, asserted on shape rather than on prose.

Nothing here checks what the model said. A test that pinned wording would fail on the day the
model was upgraded, which is precisely the day it needs to keep working. What is checked is
that the parts fit together against a live provider: that retrieval selected from the corpus
rather than handing over all of it, that a verdict came back for every candidate in the
vocabulary the domain allows, that answering resumed the same execution instead of starting a
second one beside it, and that everything downstream — the standing decision, the grounded
conversation — still keys off identities ArchCompass minted rather than anything the model
wrote.
"""

from __future__ import annotations

import re

import pytest

from archcompass.configuration import EmbeddingModelConfig
from archcompass.domain.errors import ProviderError
from archcompass.reasoning.adapters.factory import embedding_identity
from tests.e2e.conftest import (
    EMBEDDING_DIMENSIONS,
    EMBEDDING_MODEL,
    EMBEDDING_PROVIDER,
    REASONING_MODEL,
    Lifecycle,
)

pytestmark = pytest.mark.openrouter


def test_a_real_review_judges_every_candidate_within_the_domain_vocabulary(
    lifecycle: Lifecycle,
) -> None:
    first = lifecycle.first

    assert first["status"] in {"awaiting_answers", "completed"}
    assert first["findings"], "a real judgement produced no findings at all"

    # "Leave it exactly as it is" is a first-class answer, so which verdict came back is not
    # asserted — only that the model was held to the vocabulary rather than inventing one,
    # and that it said why.
    verdicts = {finding["verdict"] for finding in first["findings"]}
    assert verdicts <= {"material", "cleared", "held"}
    assert all(finding["reasoning"].strip() for finding in first["findings"])

    # The two invariants a JSON schema cannot express, and which the prompt therefore has to
    # state: a judgement waiting on an answer recommends nothing, and only a material finding
    # recommends at all. A response that breaks either is refused at the model boundary, so
    # arriving here at all is most of the assertion; these restate it against what was stored.
    for finding in first["findings"]:
        assert not (finding["hinge"] and finding["recommended_response"])
        if finding["recommended_response"]:
            assert finding["verdict"] == "material"

    # Policy citations are resolved from positions the application numbered, never from a
    # name the model produced — so every cited policy is one that was actually presented.
    cited = {
        bearing["policy_id"]
        for finding in first["findings"]
        for bearing in finding["policies"]
    }
    assert cited <= lifecycle.corpus_policy_ids


def test_the_summary_is_short_and_says_nothing_the_reader_already_knows(
    lifecycle: Lifecycle,
) -> None:
    """The opening paragraph, held to being an answer rather than a word count.

    The contract used to ask for "three to five sentences", and a floor on a summary is an
    instruction to pad: a first review with one material finding in it came back with the
    sentence that said so, plus two manufactured to reach the floor — that this was the
    first review, that there was nothing to compare it against, that the team's intent was
    not written down. Nothing checked, because nothing in the suite read the summary at all.

    The bounds here are deliberately loose. This is prose from a live model and the point is
    not to pin its wording; it is to fail when the paragraph goes back to being a paragraph.
    """

    summary = (lifecycle.first.get("synopsis") or "").strip()
    if not summary:
        pytest.skip("no summary was written for this review")

    assert "\n" not in summary, "a summary is one paragraph, not a document"
    assert not summary.lstrip().startswith(("#", "-", "*")), "no headings and no bullets"

    # Sentence-ish: the ceiling is three, and one over is slack for an abbreviation or a
    # decimal that this split would miscount.
    sentences = [part for part in re.split(r"(?<=[.!?])\s+", summary) if part.strip()]
    assert len(sentences) <= 4, f"{len(sentences)} sentences: {summary}"

    # The three sentences the floor used to manufacture, and the frame that came with them.
    padding = [
        "first review",
        "no previous",
        "nothing to compare",
        "team's intent",
        "requires attention regarding",
    ]
    said = [phrase for phrase in padding if phrase in summary.lower()]
    assert not said, f"the summary spends itself on {said}: {summary}"


def test_questions_ground_in_candidates_the_application_identified(
    lifecycle: Lifecycle,
) -> None:
    first = lifecycle.first
    if first["status"] != "awaiting_answers":
        pytest.skip(
            f"{REASONING_MODEL} judged every candidate without stating a hinge, so this run "
            "asked no questions; there is nothing to ground."
        )

    candidate_ids = {finding["candidate"]["id"] for finding in first["findings"]}
    assert first["questions"]
    for question in first["questions"]:
        assert question["candidate_ids"], "a question that grounds in nothing is not usable"
        assert set(question["candidate_ids"]) <= candidate_ids


def test_answering_resumes_the_same_review_rather_than_starting_another(
    lifecycle: Lifecycle,
) -> None:
    if lifecycle.resumed is None:
        pytest.skip(
            f"{REASONING_MODEL} completed this review in one pass, so there was no "
            "clarification round to resume."
        )
    first, resumed = lifecycle.first, lifecycle.resumed

    # Either outcome is correct. Answering does not oblige the model to conclude: it may
    # judge on what it now knows, or find that the answers moved the question rather than
    # settling it and ask again, which the graph allows up to three rounds. What is asserted
    # is that the review the answers produced is the same review, one round on — and, below,
    # that the rounds did reach an end.
    assert resumed["status"] in {"completed", "awaiting_answers"}
    assert lifecycle.final["status"] == "completed", (
        "the clarification rounds never concluded; the fixture answers until they do"
    )
    # One review, one number, however many rounds it took. This file used to assert the
    # opposite — that answering produced the next sequence, pointing back at the snapshot
    # that asked — which is what a clarification round used to do and what put one review
    # under two numbers on the rail. `round` is now the only thing separating two snapshots
    # of one review, and the lineage pointer belongs to the review rather than the round, so
    # both snapshots carry the same one.
    assert resumed["id"] != first["id"], "the round overwrote the snapshot that asked"
    assert resumed["sequence"] == first["sequence"]
    assert resumed["round"] == first["round"] + 1
    assert resumed["previous_review_id"] == first["previous_review_id"]
    assert resumed["case"]["id"] == first["case"]["id"]
    assert resumed["case"]["revision"] > first["case"]["revision"]

    answered = [
        answer for answer in resumed["case"]["answers"] if answer["status"] == "answered"
    ]
    assert len(answered) == len(first["questions"])
    assert all(answer["value"] for answer in answered)
    assert resumed["findings"], "the second round judged nothing"

    # The point of the round, and the thing that silently did not happen while this resumed
    # with `stop`: every candidate is put to the model again, against a case that now says
    # something. A second review whose findings are its predecessor's byte for byte is one
    # that was copied forward rather than re-judged.
    #
    # Asserted as "at least one moved" rather than per finding, because an answer is not
    # obliged to change a verdict — it is obliged to be read. A prompt is tens of thousands
    # of characters of evidence and policy, and a few hundred of answer; a model that
    # reaches the same conclusion about most of them, having been told, is judging, not
    # ignoring.
    before = {
        finding["candidate"]["id"]: (finding["verdict"], finding["reasoning"])
        for finding in first["findings"]
    }
    after = {
        finding["candidate"]["id"]: (finding["verdict"], finding["reasoning"])
        for finding in resumed["findings"]
    }
    assert after.keys() == before.keys(), "the rejudgement changed which candidates exist"
    assert any(after[key] != before[key] for key in before), (
        "every finding came back identical to the round the answers were given in, which is "
        "what a copied-forward review looks like"
    )


def test_retrieval_selected_from_the_corpus_rather_than_handing_over_all_of_it(
    lifecycle: Lifecycle,
) -> None:
    """The point of a real embedding provider: the manifest is a selection, not the corpus.

    Under the deterministic substitute the retriever is a full-corpus oracle, so this is the
    one property the offline suite structurally cannot check — `retriever` naming that oracle
    here would mean the review never reached a real index at all.
    """

    manifest = lifecycle.first["retrieval_manifest"]
    corpus = lifecycle.corpus_policy_ids

    assert manifest, "a review with no retrieval provenance is not auditable"
    assert corpus, "the bundled corpus is empty; this assertion would prove nothing"
    for provenance in manifest:
        assert provenance["retriever"] == "dense-scoped"
        selected = provenance["selected_policy_ids"]
        assert selected, "retrieval returned nothing for a candidate"
        assert set(selected) <= corpus
        assert len(selected) < len(corpus), (
            "retrieval handed over the whole corpus, so nothing was actually selected"
        )
        assert provenance["corpus_fingerprint"]
        assert provenance["query_fingerprint"]

    # One provenance record per judged candidate, keyed by candidate identity.
    judged = {finding["candidate"]["id"] for finding in lifecycle.first["findings"]}
    assert {item["candidate_id"] for item in manifest} == judged


def test_the_review_records_which_model_and_which_embedding_produced_it(
    lifecycle: Lifecycle,
) -> None:
    """Two selections, recorded separately, because they are separately replaceable.

    The reasoning model is stamped on each finding; the embedding model is stamped on each
    retrieval record. Swapping one must not read as having swapped the other, which is only
    demonstrable when both are real — and here they are not even the same vendor.
    """

    final = lifecycle.final

    # Per finding, because a review no longer claims one judgement identity of its own. It
    # claimed the comma-joined set of these, and the revision delta compared that set against
    # a single identity — see `domain/review.py` where the fields used to be.
    judged_by = {item["model_identity"] for item in final["findings"]}
    asked_by = {item["prompt_identity"] for item in final["findings"]}
    assert judged_by, "the completed review carried no findings to be attributed"
    for identity in judged_by:
        assert identity.startswith("openrouter:")
        assert REASONING_MODEL in identity
    # The deterministic substitute has its own prompt identity, so this also proves the run
    # did not quietly fall back to it.
    assert all(asked_by)
    assert not any("deterministic" in identity for identity in asked_by)

    embedding_identities = {
        provenance["model_identity"] for provenance in final["retrieval_manifest"]
    }
    assert embedding_identities, "the completed review carried no retrieval provenance"
    # Asked of the function that mints the identity rather than restated as a literal. The
    # literal was here, and it went stale the day a task-prompted model earned a suffix on
    # its identity so that its vectors could not be compared against unprompted ones: the
    # product was right, the assertion was a year-old copy of it, and nothing said so
    # because this file is outside `make check`.
    assert embedding_identities == {
        embedding_identity(
            EmbeddingModelConfig(
                provider=EMBEDDING_PROVIDER,
                model=EMBEDDING_MODEL,
                dimensions=EMBEDDING_DIMENSIONS,
            )
        )
    }
    assert not any(EMBEDDING_PROVIDER in identity for identity in judged_by)

    for provenance in final["retrieval_manifest"]:
        assert dict(provenance["metadata"])["dimensions"] == str(EMBEDDING_DIMENSIONS)


def test_a_decision_and_a_grounded_conversation_key_off_archcompass_identities(
    lifecycle: Lifecycle,
) -> None:
    final = lifecycle.final
    candidate_ids = {finding["candidate"]["id"] for finding in final["findings"]}

    decision = lifecycle.decision
    assert decision["candidate_id"] in candidate_ids
    assert decision["finding_verdict"] == final["findings"][0]["verdict"]

    message = lifecycle.conversation["messages"][-1]
    assert message["answer"]["text"].strip(), "the model answered the follow-up with nothing"
    # Whatever it said, the candidates it cited are ones ArchCompass minted.
    assert set(message["answer"]["supporting_candidate_ids"]) <= candidate_ids


def test_a_hinge_is_checked_against_the_repository_before_it_reaches_a_person(
    lifecycle: Lifecycle,
) -> None:
    """The only place a real tool loop runs, against a real model and a real atlas.

    Every offline test drives this through a stub or the deterministic provider, so nothing
    else establishes that a live model chooses lookups the toolbox accepts, or that what it
    chose survives onto the record.

    Skips rather than fails where the model hinged on nothing: whether this repository needs
    human context is its judgement, and the surrounding suite already treats that as a
    legitimate outcome rather than a flaky one.
    """

    manifest = lifecycle.final["investigation_manifest"]
    if not manifest:
        pytest.skip("this review reached no hinge, so nothing was investigated")

    candidate_ids = {finding["candidate"]["id"] for finding in lifecycle.final["findings"]}
    for record in manifest:
        assert record["candidate_id"] in candidate_ids, "an investigation named no candidate"
        # A lookup nobody can repeat is the unverifiable evidence the charter refuses, so
        # every call keeps the arguments it was made with alongside what came back.
        for lookup in record["lookups"]:
            assert lookup["tool"], "a recorded lookup named no tool"
            assert lookup["result"], "a recorded lookup kept no answer"
        # Nothing empty is ever stored: a record exists because something happened.
        assert record["lookups"] or record["withheld"]
        # And a record of looking says why the looking ended, so a reader — and the second
        # judgement — can tell "the repository is silent" from "we stopped asking".
        if record["lookups"]:
            assert record["termination"], "an investigation that ran recorded no termination"

    investigated = {record["candidate_id"] for record in manifest}
    for finding in lifecycle.final["findings"]:
        if finding["candidate"]["id"] not in investigated:
            continue
        # The finding names its own record by content hash, which is what lets the workbench
        # show a reader the checking behind the verdict they are looking at.
        assert finding["investigation_identity"], "an investigated finding named no record"


def test_a_live_models_hinge_investigations_are_not_thrown_away(
    lifecycle: Lifecycle,
) -> None:
    """The test above cannot fail, and this is the one that can.

    `investigate_hinges` catches every exception on purpose: losing an investigation must
    never cost the review the question it belongs to. The consequence is that a run where
    the tool loop failed finishes green — the manifest comes back empty, and the assertions
    on it skip themselves saying no hinge was reached, which is a different fact and the
    opposite one.

    This reads the losses instead. There is no structured call to fail any more: the pass
    runs tools and records what they answered, so what can still be lost is a transport that
    will not bind tools, a provider that stops answering, or a model that cannot drive the
    loop at all. Nothing offline proves those, because every other test drives this through a
    stub that answers in the right shape by construction.

    An exhausted free tier is not a defect and skips, exactly as the fixture treats it
    everywhere else. Every other loss fails, and the exception it fails with is the one the
    review threw away.
    """

    losses = lifecycle.dropped_investigations
    if not losses:
        return

    quota = tuple(loss for loss in losses if isinstance(loss, ProviderError))
    if len(quota) == len(losses):
        pytest.skip(f"the free tier ran out mid-investigation: {str(quota[0])[:200]}")

    other = [loss for loss in losses if not isinstance(loss, ProviderError)]
    reported = "\n\n".join(
        f"{type(loss).__name__}: {loss}"[:600] for loss in other
    )
    raise AssertionError(
        f"{len(other)} of {len(losses)} hinge investigations were thrown away by "
        f"{REASONING_MODEL}, so nothing was established and the review asked its "
        f"unimproved question instead:\n\n"
        f"{reported}"
    )
