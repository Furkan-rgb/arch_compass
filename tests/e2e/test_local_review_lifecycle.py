"""A whole review judged and embedded by models on this machine, and nothing else.

The sibling file runs the same lifecycle against Google. This one exists because the
deployment a company evaluating ArchCompass on its own source actually gets is the one where
nothing leaves the building: a reasoning model and an embedding model on their own hardware,
no key to obtain, no repository text on anybody's wire. That is a different set of failures
from a metered API — a local runner honours JSON schemas less reliably, allocates its context
window up front, and has no quota to be exhausted by — so it is worth a suite of its own
rather than a parameter on the other one.

`ARCHCOMPASS_PROVIDERS` is narrowed to `ollama` in the fixture, so a `.env` holding a Google
key cannot make any of this quietly reach the network and still pass.

Marked `ollama`, so `make test` deselects it and `make test-ollama` is what runs it. Anything
missing — the service, either model — skips with the command that would fix it.
"""

from __future__ import annotations

import re
from dataclasses import replace

import pytest

from archcompass.analysis.investigation import AtlasInvestigatorSource
from archcompass.bootstrap import Runtime
from archcompass.configuration import EmbeddingModelConfig
from archcompass.domain import Verdict
from archcompass.reasoning.adapters.factory import embedding_identity
from archcompass.reasoning.adapters.selected import (
    SelectedLangChainChatModel,
    SelectedLangChainHingeInvestigator,
)
from tests.e2e.conftest import (
    EMBEDDING_DIMENSIONS,
    EMBEDDING_MODEL,
    EMBEDDING_PROVIDER,
    LOCAL_REASONING_MODEL,
    LOCAL_THINKING,
    Lifecycle,
)

pytestmark = pytest.mark.ollama


def test_a_local_review_judges_every_candidate_within_the_domain_vocabulary(
    local_lifecycle: Lifecycle,
) -> None:
    first = local_lifecycle.first

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
    # arriving here at all is most of the assertion; these restate it against what was
    # stored. They matter more here than against a hosted model: a local model is exactly
    # where a stated cross-field rule is most likely to be the thing that was not honoured.
    for finding in first["findings"]:
        assert not (finding["hinge"] and finding["recommended_response"])
        if finding["recommended_response"]:
            assert finding["verdict"] == "material"

    # Policy citations are resolved from identifiers the application presented, never from a
    # name the model produced — so every cited policy is one that was actually presented.
    cited = {
        bearing["policy_id"]
        for finding in first["findings"]
        for bearing in finding["policies"]
    }
    assert cited <= local_lifecycle.corpus_policy_ids


def test_nothing_in_a_local_review_was_produced_by_a_hosted_model(
    local_lifecycle: Lifecycle,
) -> None:
    """The claim the whole suite exists to support, asserted rather than assumed.

    A machine that can run `make test-google` has a Google key in its `.env`, and
    `build_runtime` loads that `.env` before any provider is constructed. Narrowing
    `ARCHCOMPASS_PROVIDERS` is what stops it being reachable; this is what proves it was not
    reached — on the review, and on every retrieval record beneath it.
    """

    final = local_lifecycle.final

    assert final["model_identity"].startswith("ollama:")
    assert LOCAL_REASONING_MODEL in final["model_identity"]
    assert f"thinking={LOCAL_THINKING}" in final["model_identity"]
    # The deterministic substitute has its own prompt identity, so this also proves the run
    # did not quietly fall back to it.
    assert final["prompt_identity"]
    assert "deterministic" not in final["prompt_identity"]

    for provenance in final["retrieval_manifest"]:
        assert (provenance["model_identity"] or "").startswith("ollama:")


def test_two_local_models_are_still_two_selections(
    local_lifecycle: Lifecycle,
) -> None:
    """Both halves run on Ollama here, and they must still be recorded apart.

    The sibling suite demonstrates this with two vendors, where telling them apart is easy.
    This is the harder version and the one a self-hosted deployment actually lives in: same
    provider, same endpoint, two models with two jobs. If the reasoning selection ever leaked
    into the retrieval provenance, or the other way round, swapping one would read as having
    swapped the other — and here there is no vendor prefix to catch it.
    """

    final = local_lifecycle.final

    embedding_identities = {
        provenance["model_identity"] for provenance in final["retrieval_manifest"]
    }
    assert embedding_identities, "the completed review carried no retrieval provenance"
    assert embedding_identities == {
        embedding_identity(
            EmbeddingModelConfig(
                provider=EMBEDDING_PROVIDER,
                model=EMBEDDING_MODEL,
                dimensions=EMBEDDING_DIMENSIONS,
            )
        )
    }
    assert EMBEDDING_MODEL not in final["model_identity"]
    assert LOCAL_REASONING_MODEL not in embedding_identities.pop()

    for provenance in final["retrieval_manifest"]:
        assert dict(provenance["metadata"])["dimensions"] == str(EMBEDDING_DIMENSIONS)


def test_retrieval_selected_from_a_locally_built_index(
    local_lifecycle: Lifecycle,
) -> None:
    """A selection, not the corpus — which is only demonstrable against a real index.

    Under the deterministic substitute the retriever is a full-corpus oracle, so this is the
    one property the offline suite structurally cannot check. It carries an extra weight
    here: the index these vectors came from is not the one this package ships. That one was
    built with Google's embedder at 3,072 dimensions and finds nothing for a query embedded
    at 768, so reaching this assertion at all means the local index was built and attached.
    """

    manifest = local_lifecycle.first["retrieval_manifest"]
    corpus = local_lifecycle.corpus_policy_ids

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
    judged = {finding["candidate"]["id"] for finding in local_lifecycle.first["findings"]}
    assert {item["candidate_id"] for item in manifest} == judged


def test_the_summary_is_short_and_says_nothing_the_reader_already_knows(
    local_lifecycle: Lifecycle,
) -> None:
    """The opening paragraph, held to being an answer rather than a word count.

    The bounds are deliberately loose. This is prose from a live model and the point is not
    to pin its wording; it is to fail when the paragraph goes back to being a paragraph.
    """

    summary = (local_lifecycle.first.get("synopsis") or "").strip()
    if not summary:
        pytest.skip("no summary was written for this review")

    assert "\n" not in summary, "a summary is one paragraph, not a document"
    assert not summary.lstrip().startswith(("#", "-", "*")), "no headings and no bullets"

    # Sentence-ish: the ceiling is three, and one over is slack for an abbreviation or a
    # decimal that this split would miscount.
    sentences = [part for part in re.split(r"(?<=[.!?])\s+", summary) if part.strip()]
    assert len(sentences) <= 4, f"{len(sentences)} sentences: {summary}"

    padding = [
        "first review",
        "no previous",
        "nothing to compare",
        "team's intent",
        "requires attention regarding",
    ]
    said = [phrase for phrase in padding if phrase in summary.lower()]
    assert not said, f"the summary spends itself on {said}: {summary}"


def test_a_hinge_is_checked_against_this_repository_by_this_model(
    local_runtime: Runtime, local_lifecycle: Lifecycle
) -> None:
    """A real tool loop, against a real local model and the real atlas its review judged.

    The lifecycle runs with the lookups off, so that whether a person is asked is not left
    to how a tool loop went that morning — see `local_runtime`. This is the pass that switch
    skips, run here on its own for one finding, so nothing about it goes uncovered.

    Everything offline drives this through a stub or the deterministic provider, so nothing
    else establishes that a model on this machine chooses lookups the toolbox accepts, that
    what it chose survives onto the record, or that its closing answer fits
    `HingeResolutionOutput` — which is three cross-field rules no JSON schema can carry.

    The hinge is put onto a finding the review actually produced rather than invented
    alongside one. A hinge is this capability's input by definition: what is under test is
    what the model does with the repository when it is asked something the finding cannot
    answer, and the finding here is a real judgement of real code.
    """

    review = local_runtime.core_review_repository.get(local_lifecycle.final["id"])
    assert review.findings, "the completed review carried no findings to investigate"
    held = replace(
        review.findings[0],
        verdict=Verdict.HELD,
        recommended_response=None,
        hinge="whether this boundary is deliberate or was reached for out of habit",
    )

    investigator = SelectedLangChainHingeInvestigator(
        SelectedLangChainChatModel(local_runtime.model_catalog_service),
        AtlasInvestigatorSource(local_runtime.query_service),
    )
    # Not caught. `investigate_hinges` catches everything on purpose, because losing an
    # investigation must never cost the review the question it belongs to — and the price of
    # that is a run where the model could not honour the contract finishing green with an
    # empty manifest. This is the one place that price is not paid: a model on this machine
    # has no quota to blame, so anything it raises is the defect.
    investigated = investigator.investigate(
        held, review.case, repository=review.repository, atlas=review.atlas
    )

    record = investigated.investigation
    assert record is not None, "a live model with a real toolbox recorded nothing"
    assert record.candidate_id == str(held.candidate.id)
    # `withheld` is the sentence the toolbox returns when there was nothing to look at — an
    # empty atlas, or one an older parser wrote. It is a legitimate outcome of the *product*
    # and an illegitimate one here: `investigate` returns on it without calling the model or
    # a single tool, and every assertion below is then satisfied by a record that describes
    # nothing happening. This test exists to prove a live model chose lookups.
    assert not record.withheld, f"nothing was looked at: {record.withheld}"
    assert not record.abandoned, f"the loop gave up: {record.abandoned}"
    assert record.lookups, "a live model with a real toolbox made no lookup"
    # `closing` is deliberately not asserted. It is filled only when the model stops with a
    # turn that has no tool calls; a model that spends all six turns looking things up ends
    # the loop on the ceiling instead, which is a legitimate investigation with an empty
    # closing. What has to be there is the lookups and the resolution that follows them.
    # A lookup nobody can repeat is the unverifiable evidence the charter refuses, so every
    # call keeps the arguments it was made with alongside what came back — and names a tool
    # the toolbox actually offers rather than one the model imagined.
    offered = {
        "find_code",
        "describe_code",
        "related_code",
        "read_code",
        "flagged_signals",
    }
    for lookup in record.lookups:
        assert lookup.tool in offered, f"a recorded lookup named {lookup.tool!r}"
        assert lookup.result, "a recorded lookup kept no answer"
    assert record.atlas_fingerprint == review.repository.content_id
    assert record.model_identity.startswith("ollama:")

    # Whichever way it went, the finding that comes back is a coherent one. Settling is not
    # the goal — "I checked and the repository is silent" is as good an answer — so what is
    # asserted is that the two outcomes are the two the domain allows, and that the finding
    # names the record a reader can open.
    result = investigated.finding
    assert result.investigation_identity == record.identity
    # The record and the finding are shown side by side in the workbench, so they have to
    # agree about what happened: a record that says it settled the hinge beside a finding
    # that is still hinged is two accounts of one investigation.
    assert record.resolved == (result.hinge is None)
    if record.resolved:
        assert result.hinge is None, "a resolved hinge is still hinged"
        assert result.verdict in {Verdict.MATERIAL, Verdict.CLEARED}
        assert result.reasoning.strip()
        assert result.reasoning != held.reasoning, (
            "the verdict moved but the reasoning behind it is the one from before the "
            "lookups, so nothing the investigation found reached the finding"
        )
    else:
        # Deliberately not the post-conditions `_apply` sets by construction — those cannot
        # fail. What is asserted is that the record and the finding agree about what
        # happened, and that the reader is left with a question rather than a hole.
        assert result.verdict is Verdict.HELD
        assert result.hinge, "an unresolved hinge lost the question it was standing in for"
        assert not result.recommended_response


def test_questions_ground_in_candidates_the_application_identified(
    local_lifecycle: Lifecycle,
) -> None:
    first = local_lifecycle.first
    # Asserted, not skipped. `generate_questions` catches everything and returns no
    # questions, so a broken generator produces exactly what a confident model produces —
    # and a skip here reads the first as the second and says so in its message. This suite
    # runs with the lookups off precisely so that the hinge reaches a person every time,
    # which makes "it asked nothing" a failure rather than a mood.
    assert first["status"] == "awaiting_answers", (
        "this review asked nothing. With ARCHCOMPASS_HINGE_INVESTIGATION off a held finding "
        "goes straight to question generation, so either nothing was held — in which case "
        f"the subject repository is wrong for this suite — or the questions were lost: "
        f"{[(f['verdict'], bool(f['hinge'])) for f in first['findings']]}"
    )

    candidate_ids = {finding["candidate"]["id"] for finding in first["findings"]}
    assert first["questions"]
    for question in first["questions"]:
        assert question["candidate_ids"], "a question that grounds in nothing is not usable"
        assert set(question["candidate_ids"]) <= candidate_ids
        # Two or none, never one. The schema floors the model at two, and `_offered_answers`
        # then drops any that are really "I don't know" — which can leave fewer than two, in
        # which case it offers none at all and the interface shows a box to type in. One
        # option is the shape neither of those produces, and the only way to see it would be
        # the filter having been bypassed.
        assert len(question["options"]) != 1, question["options"]


def test_answering_a_local_review_continues_it_rather_than_starting_another(
    local_lifecycle: Lifecycle,
) -> None:
    """One review, one number, however many rounds it took to get there.

    A clarification round is not a second review. It is the same review, still mid-question,
    recorded again — so the sequence does not move, the case does not become another case,
    and the lineage pointer does not swing onto the snapshot that asked. What moves is
    `round`, which is the only thing that distinguishes two snapshots of one review.
    """

    assert local_lifecycle.resumed is not None, (
        "this review completed in one pass, so the clarification round this suite exists to "
        "drive never ran. See the note on asking in the grounding test above."
    )
    first, resumed = local_lifecycle.first, local_lifecycle.resumed

    assert resumed["status"] in {"completed", "awaiting_answers"}
    assert local_lifecycle.final["status"] == "completed", (
        "the clarification rounds never concluded; the driver answers until they do"
    )

    assert resumed["id"] != first["id"], "the round overwrote the snapshot that asked"
    assert resumed["sequence"] == first["sequence"], (
        "answering moved the review's number, so one review occupies two places on the rail"
    )
    assert resumed["round"] == first["round"] + 1
    assert resumed["previous_review_id"] == first["previous_review_id"], (
        "the lineage pointer moved onto this review's own earlier snapshot"
    )
    assert resumed["case"]["id"] == first["case"]["id"]

    answered = [
        answer for answer in resumed["case"]["answers"] if answer["status"] == "answered"
    ]
    assert len(answered) == len(first["questions"])
    assert all(answer["value"] for answer in answered)
    assert resumed["findings"], "the second round judged nothing"

    # The point of the round: every candidate is put to the model again, against a case that
    # now says something. A second review whose findings are its predecessor's byte for byte
    # is one that was copied forward rather than re-judged.
    #
    # Asserted as "at least one moved" rather than per finding, because an answer is not
    # obliged to change a verdict — it is obliged to be read.
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


def test_a_decision_and_a_grounded_conversation_key_off_archcompass_identities(
    local_lifecycle: Lifecycle,
) -> None:
    final = local_lifecycle.final
    candidate_ids = {finding["candidate"]["id"] for finding in final["findings"]}

    decision = local_lifecycle.decision
    assert decision["candidate_id"] in candidate_ids
    assert decision["finding_verdict"] == final["findings"][0]["verdict"]

    message = local_lifecycle.conversation["messages"][-1]
    assert message["answer"]["text"].strip(), "the model answered the follow-up with nothing"
    # Whatever it said, the candidates it cited are ones ArchCompass minted.
    assert set(message["answer"]["supporting_candidate_ids"]) <= candidate_ids


def test_the_answered_review_is_readable_through_the_surfaces_that_outlive_it(
    local_lifecycle: Lifecycle,
) -> None:
    """A review is not finished when the graph returns. It is finished when it can be read.

    Everything asserted elsewhere in this file comes out of the response that ended the run.
    These come from the surfaces a person uses afterwards — the document they download, the
    list they scroll, the case they open — and each of them has been wrong at some point
    while the response was right.
    """

    final = local_lifecycle.final

    report = local_lifecycle.report
    assert report.strip(), "a completed review handed over an empty document"
    # Every finding is in the document, found by the name the report actually prints. The id
    # is not that name — `_identity` prints the participant — and asserting on the id was a
    # disjunct that could never be true, leaving the whole check resting on a prefix of
    # model prose that the report reflows.
    for finding in final["findings"]:
        name = finding["candidate"]["participants"][0]["qualified_name"]
        assert name in report, f"the report does not mention {name}"

    # A concluded review cannot be answered, so its document must not tell anyone to. Tied
    # to whether a hinge actually survived to the end, because the sentence lives inside
    # `if finding.hinge:` — asserting only its absence passes on a review with no hinge
    # left, which is most of them.
    hinged = [finding for finding in final["findings"] if finding["hinge"]]
    assert "Answering it records the answer" not in report, (
        "a concluded review tells its reader to answer a question nothing is waiting for"
    )
    assert ("**Unresolved.**" in report) == bool(hinged), (
        f"{len(hinged)} finding(s) ended still hinged, and the report says otherwise"
    )

    # One review, one row. Two waiting snapshots and a final one live under one sequence,
    # and a listing that showed them would show this review three times — twice claiming to
    # be still waiting.
    listed = [row for row in local_lifecycle.listing if row["id"] == final["id"]]
    assert len(listed) == 1, "the answered review is not the one the listing shows"
    assert [row["sequence"] for row in local_lifecycle.listing] == sorted(
        {row["sequence"] for row in local_lifecycle.listing}, reverse=True
    ), "the listing shows a sequence twice, or out of order"


def test_the_answers_a_person_typed_are_on_the_case_and_not_only_on_the_review(
    local_lifecycle: Lifecycle,
) -> None:
    """The case is the durable record; a review blob is a snapshot of one moment.

    This is the assertion that would have caught the worst thing this product has done. A
    round that failed after its answers were taken left two reviews pointing at a case
    revision `seal_case` never wrote — the answers survived inside review JSON, the case
    held none of them, and every later review was judged against an empty case while the
    interface showed the questions as answered.
    """

    assert local_lifecycle.resumed is not None, (
        "this review asked nothing, so there are no answers to have kept"
    )

    revisions = {revision["revision"]: revision for revision in local_lifecycle.case_history}
    assert revisions, "the case this review answered has no history at all"

    sealed = local_lifecycle.final["case"]
    assert sealed["revision"] in revisions, (
        f"the review names case revision {sealed['revision']}, which was never written; "
        f"the case holds {sorted(revisions)}"
    )

    answered = [
        answer
        for answer in revisions[sealed["revision"]]["answers"]
        if answer["status"] == "answered"
    ]
    assert answered, "the sealed revision holds none of the answers that were given"
    assert all(answer["value"] for answer in answered)
    assert all(answer["actor"] == "architect" for answer in answered)

    # One revision for the whole review, however many rounds it took. Every revision this
    # review opened above the one it started from is its own, and there is exactly one.
    opened = [
        revision
        for revision in revisions
        if revision > local_lifecycle.first["case"]["revision"]
    ]
    assert len(opened) <= 1, (
        f"one review opened {len(opened)} case revisions: {sorted(opened)}"
    )


def test_a_review_of_code_that_has_not_moved_is_refused_rather_than_charged_for(
    local_lifecycle: Lifecycle,
) -> None:
    """And leaves nothing behind, which is the half that was wrong.

    The last clarification round already judged every candidate against the answers, so a
    review asked for immediately afterwards has genuinely nothing to do, and saying so
    instead of spending another judging pass is the product working.

    What it must not do is keep a souvenir. `NothingToReviewError` says in its own docstring
    that it is raised before anything is written — and it was not: by the time it is raised
    the repository, atlas and case are all in graph state, so a failure snapshot was built
    from them and filed. A person who pressed "Run review" on unchanged code was correctly
    told nothing had changed and then found a failed second review on the rail that they had
    never asked to keep.
    """

    refusal = local_lifecycle.unchanged_refusal
    assert refusal is not None, "the fixture did not ask for a review of unchanged code"
    assert refusal["status_code"] == 409, refusal
    assert refusal["code"] == "nothing_changed", refusal
    assert refusal["retryable"] is False

    listing = local_lifecycle.listing_after_refusal
    assert listing, "the listing was not read after the refusal"
    assert local_lifecycle.final["id"] in {row["id"] for row in listing}
    # Two ways to say it, because the phantom had both properties and either alone could be
    # satisfied by something legitimate: it sat above the answered review's number, and it
    # was `failed` on a workspace where nothing had failed.
    later = [row for row in listing if row["sequence"] > local_lifecycle.final["sequence"]]
    assert not later, f"the refused review left a snapshot behind: {later}"
    assert not [row for row in listing if row["status"] == "failed"], (
        f"a review was refused and recorded as failed: {listing}"
    )


def test_the_next_review_is_judged_against_the_answers_rather_than_starting_over(
    local_lifecycle: Lifecycle,
) -> None:
    """What answering a question is for, asserted on the review that comes after it.

    Everything else here proves the round happened. This proves it was worth having. The
    repository has moved — one new port with one implementation — so there is real work,
    and what the second review must do with it is pick up the answered case rather than
    reopen an empty one, take the next number in the lineage, point back at the review that
    asked, and account for every candidate the first review saw instead of presenting them
    all as new.
    """

    subsequent = local_lifecycle.subsequent
    assert subsequent is not None, "the fixture did not run a second review"
    final = local_lifecycle.final

    assert subsequent["status"] == "completed"
    assert subsequent["id"] != final["id"]
    assert subsequent["findings"], "the second review judged nothing"
    # A new review, not another round of the old one — so here the sequence does move, and
    # the lineage pointer is the previous review rather than the previous snapshot. Its own
    # round count is not asserted: a second review is free to ask about the code that
    # changed, and the fixture stops it rather than answering, which is still a round.
    assert subsequent["sequence"] == final["sequence"] + 1
    assert subsequent["previous_review_id"] == final["id"]

    # The answered case, carried forward rather than reopened empty. This is the whole
    # point of recording answers on the case instead of only on the review.
    assert subsequent["case"]["id"] == final["case"]["id"]
    assert subsequent["case"]["revision"] >= final["case"]["revision"]
    answered_before = [
        answer for answer in final["case"]["answers"] if answer["status"] == "answered"
    ]
    answered_now = [
        answer for answer in subsequent["case"]["answers"] if answer["status"] == "answered"
    ]
    assert len(answered_now) >= len(answered_before), "the second review lost the answers"

    # One boundary was added and nothing was taken away, so the delta has exactly one thing
    # to call new and nothing to call addressed — and everything the first review judged is
    # still accounted for by name rather than being presented as new work.
    delta = subsequent["delta"]
    seen = {finding["candidate"]["id"] for finding in final["findings"]}
    carried = set(delta["unchanged"]) | {item["candidate_id"] for item in delta["changed"]}
    assert delta["new"], "a new one-implementation port produced no new candidate"
    assert not set(delta["new"]) & seen, "a candidate the first review judged is called new"
    assert carried <= seen, (
        f"the delta carried candidates the first review never saw: {sorted(carried - seen)}"
    )
    assert not delta["addressed"], (
        f"nothing was removed, but the delta addressed candidates: {delta['addressed']}"
    )

    # A question that was asked and answered is not asked again. Equivalence is the facet
    # and the candidates it grounds in, not the model's wording, so a rephrasing does not
    # get past it.
    asked_before = {
        question["equivalence_key"] for question in local_lifecycle.first["questions"]
    }
    asked_again = {question["equivalence_key"] for question in subsequent["questions"]}
    assert not (asked_before & asked_again), (
        "the second review asked a question the first one had already been answered"
    )
