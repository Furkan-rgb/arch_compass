"""Drive the built workspace in a real browser, end to end.

Everything below the browser is real: the FastAPI adapter, SQLite, the migrations, the
detector, the bundled example and its repository. Only the model is substituted, because
a live review is one call per boundary and takes minutes; the substitute answers the same
port with the same shapes, so what is exercised is the wiring rather than the reasoning.

The bundle under test is the committed one in `presentation/web/static`, which is what a
user actually loads. A test against a dev server would pass while the shipped page was
stale.
"""

from __future__ import annotations

import socket
import threading
import time
from collections.abc import Iterator
from pathlib import Path

import pytest
import uvicorn

from archcompass.adapters.models.deterministic import DETERMINISTIC_MODEL
from archcompass.bootstrap import Runtime, build_runtime, pinned_model
from archcompass.domain.review import ReviewStatus
from archcompass.presentation.web import create_app

pytestmark = pytest.mark.browser

# The panel a question is asked in is a non-modal drawer portalled to the body, so it is
# named by the primitive's own slot rather than by a class on the review page.
ASK_PANEL = "[data-slot='sheet-content']"

# The rest of this page is drawn in utilities, so every hook below is the slot the element
# announces itself as rather than a class that describes how it looks.
REVIEW_PAGE = "[data-slot='review-page'] [data-slot='page-header']"
LEDGER = "[data-slot='ledger']"
ITEM = "[data-slot='ledger-item']"
ROW = "[data-slot='ledger-row']"
REVIEW_ROW = "[data-slot='review-row']"
REVIEW_LINK = "[data-slot='review-link']"
VERDICT = "[data-slot='verdict-text']"
OVERVIEW = "[data-slot='overview']"
REVIEW_ATLAS = "[data-slot='review-atlas']"
COMMIT = "[data-slot='commit']"
# The sentence over the run button names the repository it is about to judge, so one `strong`
# in it is the page stating that the one thing this step asks for has been chosen. There is no
# second rail to fill any more: the review writes the case from the reader's answers.
COMMIT_READY = (
    "document.querySelectorAll('[data-slot=\"commit\"] p strong').length === 1"
)
# What the second pass reads back: the reader's own answer under the question it was given
# for. Named by the section's label rather than a slot, because that label is what a screen
# reader is told it is.
ANSWERS_RECORDED = "section[aria-label='Answers already recorded']"
# Nobody names a case any more, so the one every run of this example belongs to is the
# one the workspace derived from the repository's location — the project's name, not the
# layout's: bundled code lives at `eval/cases/<name>/repository`, and the leaf `repository`
# names a convention, so the title comes from the example. It is what the listing groups
# under.
CASE_TITLE = "Boundaries in boundary-review"

def _free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1])


@pytest.fixture(scope="module")
def workspace(tmp_path_factory: pytest.TempPathFactory) -> Runtime:
    """The server's own runtime, so a test can put the workspace into a state on purpose.

    A run in progress is the clearest example: the substitute answers faster than a browser
    can look, so the only way to see that surface is to write the state the surface is for.
    """

    directory = tmp_path_factory.mktemp("browser-workspace")
    # Pinned rather than chosen: a workspace that has chosen nothing reasons with nothing,
    # and clicking through the model chip first would be a different test.
    return build_runtime(directory, pin=pinned_model("fake", DETERMINISTIC_MODEL))


@pytest.fixture(scope="module")
def workspace_url(workspace: Runtime) -> Iterator[str]:
    app = create_app(workspace)
    port = _free_port()
    server = uvicorn.Server(
        uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning")
    )
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    deadline = time.monotonic() + 30
    while not server.started:
        if time.monotonic() > deadline:
            raise RuntimeError("The workspace server did not start")
        time.sleep(0.05)
    try:
        yield f"http://127.0.0.1:{port}"
    finally:
        server.should_exit = True
        thread.join(timeout=10)


def test_a_person_can_review_an_example_and_ask_about_it(workspace_url: str) -> None:
    """The whole loop, as a person performs it, in a browser.

    Deliberately one test rather than several. Each step depends on the state the previous
    one produced, and splitting them would either re-run the review three times or share
    mutable state between tests that claim to be independent.
    """

    playwright = pytest.importorskip("playwright.sync_api")
    static = Path("src/archcompass/presentation/web/static/index.html")
    assert static.is_file(), "run `make frontend-build` before the browser test"

    with playwright.sync_playwright() as driver:
        browser = driver.chromium.launch()
        page = browser.new_page(viewport={"width": 1280, "height": 900})
        try:
            # `/start` rather than `/`, which is the showcase: the workbench is a step a
            # reader arrives at from there, and it is the one this test is about.
            page.goto(f"{workspace_url}/start", wait_until="networkidle")

            # 1. The start step asks one question: which code. What is offered is a shelf of
            #    example repositories — a name, and under the pointer a sentence saying what
            #    the repository is. Never what a review of it will find: that is the run's to
            #    say, and a shelf that said it first would be handing over the answer.
            page.wait_for_selector("[data-slot='examples']", timeout=20_000)
            example = page.get_by_role("button", name="Task scheduler boundary review")
            example.wait_for(state="visible", timeout=20_000)
            assert "six boundaries" in (example.get_attribute("title") or "")
            # One column, because there is one thing to choose. A case is not an input here
            # any more — the review writes it from the answers below — so there is nothing on
            # this step that authors one.
            assert page.locator("[data-slot='start-column']").count() == 1
            assert page.get_by_role("button", name="New case", exact=True).count() == 0

            # 2. Nothing can run yet: the flow states what is missing rather than
            #    offering a button that fails.
            run = page.get_by_role("button", name="Run review")
            assert run.is_disabled()

            # 3. One example click indexes its repository and selects it, and then the run is
            #    the user's to start. An example takes the identical path a folder-picked
            #    project takes from here on, which is the whole reason it is only a
            #    repository.
            #
            #    "Selected" is read off the one column — exactly one chosen entry — and off
            #    the sentence beside the run button. That sentence is the assertion worth
            #    keeping: it is the page stating what the click actually did, in the place the
            #    run is started, and what it states is that nothing but the code is going in.
            example.click()
            page.wait_for_function(COMMIT_READY, timeout=60_000)
            chosen = "[data-slot='start-column'] [data-slot='pick'] button[aria-pressed='true']"
            assert page.locator(chosen).count() == 1
            commit = page.inner_text(COMMIT)
            assert "on the code alone" in commit, commit
            assert "no case written" in commit, commit
            run.click()
            # Starting a run goes to the review, not to a copy of it drawn on the start
            # step. The stream announces the review's identity before the first model call,
            # so this URL exists while the run is still going — one place to watch it,
            # whether this tab is producing it or another one is.
            page.wait_for_url("**/reviews/rev_*", timeout=120_000)
            # Wait on something only the review page renders: the router changes the URL
            # before React commits the new page, so any text shared with the start step
            # would match the old DOM and pass for the wrong reason.
            page.wait_for_selector(REVIEW_PAGE, timeout=60_000)
            first_pass = page.url

            # 4. The first pass judges every boundary and then holds, because a review of code
            #    with nothing written about it cannot settle what the code does not say. It
            #    says so on the review's own page and offers the one thing there is to do.
            #
            #    No conclusion is drawn while it holds. That is the point of the state rather
            #    than a decoration of it: the verdicts it reached rest on a case that does not
            #    yet answer the question below, so presenting them as findings would lead with
            #    conclusions it is about to revise.
            answer_them = page.get_by_role("button", name="Answer 1 question")
            answer_them.wait_for(state="visible", timeout=120_000)
            assert page.locator(OVERVIEW).count() == 0
            answer_them.click()

            # 5. A question the review could enumerate the answers to offers them, as things
            #    to press rather than a list to read. Pressing one is the reader's act and
            #    nothing else's: it fills the box below with that option's own words, and the
            #    box stays theirs to edit. Nothing is selected until they press, which is what
            #    keeps the rule that only what the reader wrote enters the case.
            offered = "That variation is coming."
            page.get_by_role("group", name="Offered answers").wait_for(
                state="visible", timeout=20_000
            )
            option = page.get_by_role("button", name=offered)
            box = page.get_by_label("Or write your own")
            assert box.input_value() == ""
            assert option.get_attribute("aria-pressed") == "false"
            option.click()
            assert box.input_value() == offered
            # Marked from the box rather than from a second piece of state, so the pill and
            # the answer can never disagree about what is about to be recorded.
            assert option.get_attribute("aria-pressed") == "true"

            # The box is the standing "other", so free text is not a second surface: typing
            # over an offer makes the answer the reader's own again and the offer stops being
            # taken. Proved here rather than on a second question because this fixture asks
            # exactly one — it consolidates every boundary that turns on the same unknown into
            # one question — so a question carrying no options is not reachable in a browser
            # at all, and that shape is held in `review-questions.test.tsx`.
            box.fill("Both, in different places.")
            assert option.get_attribute("aria-pressed") == "false"
            option.click()
            assert box.input_value() == offered

            # 6. Carrying on records the answer as a revision of the case and starts the
            #    second pass, which is a review of its own beside the first rather than a
            #    correction of it — a new identity, reached before the first model call.
            page.get_by_role("button", name="Review what will be recorded").click()
            page.get_by_role("button", name="Continue the review").click()
            page.wait_for_function(
                "url => window.location.href !== url", arg=first_pass, timeout=120_000
            )
            page.wait_for_selector(REVIEW_PAGE, timeout=60_000)
            # And this one concludes. Whether the in-progress panel is ever visible here is
            # the substitute's business — it answers faster than a browser can look — so that
            # surface is proved on its own below.
            page.wait_for_selector(OVERVIEW, timeout=120_000)
            second_pass = page.url
            assert second_pass != first_pass
            header = page.locator("[data-slot='page-header']").inner_text().lower()
            assert "case rev 2" in header, header

            # 6a. What was recorded is what was pressed, word for word. The option was a way
            #     of writing the answer, not a code the case stores instead of it, so the pass
            #     that judged against it reads back the reader's sentence under the review's
            #     question.
            page.get_by_role("tab", name="Questions").click()
            page.wait_for_selector(ANSWERS_RECORDED, timeout=20_000)
            assert offered in page.inner_text(ANSWERS_RECORDED)
            page.get_by_role("tab", name="Findings").click()
            page.wait_for_selector(LEDGER, timeout=20_000)

            # 7. The page leads with what the verdicts amount to, and every claim in it
            #    names the boundaries it rests on.
            overview = page.locator(OVERVIEW)
            assert overview.count() == 1
            assert overview.locator("[data-slot='overview-lead']").inner_text().strip()
            assert overview.locator("[data-slot='overview-limits']").inner_text().strip()
            citations = overview.locator("[data-slot='citation']")
            assert citations.count() >= 1, overview.inner_text()

            # 8. A citation is a link into the evidence: clicking one lands on that
            #    boundary, which is the whole reason the overview is allowed to generalise.
            #    The row it names opens with it — landing on a collapsed line would be
            #    citing evidence and then not showing it.
            cited = citations.first.inner_text().strip()
            citations.first.click()
            page.wait_for_selector(f"#{cited}:target", timeout=10_000)
            page.wait_for_selector(f"#{cited}[data-state='open']", timeout=10_000)

            # 9. Every boundary is on the page, cleared ones included. A report that
            #    listed only problems would look identical whether the advisor examined
            #    six boundaries or none.
            assert page.locator(ITEM).count() == 6, page.content()[:2000]
            rows = page.locator(f"{LEDGER} {ROW}")
            assert rows.count() == 6
            # The verdict is a word, not only a colour: every row carries one, whether it
            # wears the chip the exception gets or the quiet text the majority does.
            words = page.locator(f"{ROW} [data-slot='badge'], {ROW} {VERDICT}")
            assert words.count() == 6, words.all_inner_texts()
            assert all(text.strip() for text in words.all_inner_texts())

            # 10. Detection limits are stated on each boundary, not once in a footer.
            assert page.locator("[data-slot='finding-limits']").count() == 6

            # 11. A follow-up question is answered and its grounding shown.
            #
            #    Asking is a panel the reader opens rather than a dock riding the foot of
            #    every review, so the first step is asking for it. Everything below is about
            #    the message that was appended, never the preview: an answer's prose arrives
            #    as it is written, and while it does there is a second `.msg--a` on the page
            #    carrying no grounding — grounding comes from flags that do not exist until
            #    the reply is complete. The turn in flight is the one marked `aria-busy`, so
            #    the record is what is left when that mark is not on it. Whether the
            #    substitute's preview survives long enough to be seen at all is a timing
            #    question, and nothing here asserts either way.
            recorded = '[data-slot="ask-log"] > li:not([aria-busy="true"])'
            page.get_by_role("button", name="Ask about this review").click()
            page.wait_for_selector(
                "input[aria-label='Question about this review']",
                state="visible",
                timeout=10_000,
            )
            page.get_by_label("Question about this review").fill(
                "Why was the TaskFormatter boundary judged the way it was?"
            )
            page.get_by_role("button", name="Ask", exact=True).click()
            page.wait_for_selector(f"{recorded} [data-slot='answer']", timeout=60_000)
            grounding = page.locator(f"{recorded} [data-slot='grounding']").first.inner_text()
            assert "BR-" in grounding, grounding

            # 12. Threads are durable and plural: a second one is kept apart from the
            #     first, and both stay reachable.
            page.get_by_role("button", name="New thread").click()
            page.get_by_label("Question about this review").fill("What should I do first?")
            page.get_by_role("button", name="Ask", exact=True).click()
            page.wait_for_selector(f"{recorded} [data-slot='answer']", timeout=60_000)
            # Two threads plus the "new thread" control. Waited for rather than read once:
            # the second thread is created by the ask itself, so the row of threads is
            # correct only after the listing has been read back — and the substitute answers
            # faster than that round trip.
            page.wait_for_function(
                "document.querySelectorAll('[data-slot=\"ask-threads\"] button').length === 3",
                timeout=30_000,
            )
            threads = page.locator("[data-slot='ask-threads'] button")
            assert page.locator("[data-slot='ask-log'] > li").count() == 1
            threads.first.click()
            page.wait_for_selector("[data-slot='ask-log'] > li", timeout=10_000)
            assert "TaskFormatter" in page.locator("[data-slot='ask-log']").inner_text()

            # 13b. The panel is beside the review, not over it. What the dock's two heights
            #      were for — never covering the thing the question is about, and never
            #      leaving the reader without an input to type into — the panel gets by
            #      construction, and these are the same two guarantees read off the new
            #      shape: the ledger stays reachable behind it at any scroll position, and
            #      the input stays visible however long the thread grows.
            extent = "document.documentElement.scrollHeight - window.innerHeight"
            page.evaluate("window.scrollTo(0, 0)")
            page.wait_for_timeout(120)
            assert page.get_by_label("Question about this review").is_visible()
            page.evaluate(f"window.scrollTo(0, {extent})")
            page.wait_for_timeout(120)
            assert page.get_by_label("Question about this review").is_visible()
            # Non-modal, which is the whole reason it is a panel: a row of the ledger it is
            # about can still be opened while the question sits there unanswered. A row the
            # citation above did not already open, so this is an opening rather than the
            # accordion closing the one that was.
            page.evaluate("window.scrollTo(0, 0)")
            page.locator(f"#BR-002 {ROW}").click()
            page.wait_for_selector("#BR-002[data-state='open']", timeout=10_000)
            assert page.locator(ASK_PANEL).is_visible()

            # 13c. And the two cannot fight each other. This is what made the dock stick:
            #      its height was measured from how close the reader was to the end of the
            #      page, and growing it moved that end — which un-made the condition that
            #      grew it, so a pixel of jitter on the boundary flipped it back and forth
            #      for ever. The panel's geometry is not derived from the scroll at all, so
            #      the same jitter at the same place has to leave it exactly where it is.
            #
            #      Asserted on the rendered box rather than on the document, because the
            #      document height genuinely does change with the panel: on a wide screen
            #      the column gives back exactly the width the panel takes, so that it never
            #      floats over the ledger it is about. That is the intended trade, and it
            #      happens once when the panel opens rather than continuously as you scroll.
            page.evaluate(f"window.scrollTo(0, {extent})")
            page.wait_for_timeout(200)
            seen = set()
            for _ in range(6):
                page.evaluate("window.scrollBy(0, -1)")
                page.wait_for_timeout(60)
                seen.add(str(page.locator(ASK_PANEL).bounding_box()))
                page.evaluate("window.scrollBy(0, 1)")
                page.wait_for_timeout(60)
                seen.add(str(page.locator(ASK_PANEL).bounding_box()))
            assert len(seen) == 1, seen
            assert page.get_by_label("Question about this review").is_visible()

            page.get_by_role("button", name="Close the question panel").click()
            page.wait_for_selector(ASK_PANEL, state="hidden", timeout=10_000)

            # 13a. A bearing card is as tall as its own sentence. They shared a class with
            #      the Policies page cards, and so inherited a 255px floor, a hover lift and
            #      a pointer cursor — a card of two lines stood a quarter of a screen tall.
            #      Measured in an open row, because that is the only place they are drawn.
            page.wait_for_timeout(200)  # the column widens as the panel goes
            opened = page.locator(f"{ITEM}[data-state='open']")
            assert opened.count() == 1
            cards = opened.locator("[data-slot='bearing']")
            assert cards.count() >= 2, cards.count()
            heights = [
                round(box["height"])
                for index in range(cards.count())
                if (box := cards.nth(index).bounding_box()) is not None
            ]
            assert heights and max(heights) < 200, heights
            # And no column is left blank: two cards take two columns, not two of three.
            # Read off the resolved track list rather than off where the cards landed. An
            # empty track collapses to `0px`, which is the whole assertion — every track
            # with width in it has a card in it, and they are all the same width.
            tracks = page.evaluate(
                """() => getComputedStyle(
                    document.querySelector(
                        '[data-slot="ledger-item"][data-state="open"] [data-slot="bearings"]'
                    )
                ).gridTemplateColumns.split(' ').filter(size => size !== '0px')"""
            )
            assert 0 < len(tracks) <= cards.count(), (tracks, cards.count())
            # Compared as numbers with a pixel of slack, for the same reason the canvas
            # further down is: an even split of a fractional width lands on 64ths of a pixel,
            # so three equal tracks are three unequal strings. What is asserted is that no
            # track is a different size, not that Chromium divides exactly.
            widths = [float(size.removesuffix("px")) for size in tracks]
            assert max(widths) - min(widths) <= 1, tracks

            # 13. The review carries its own atlas, drawn around the boundaries it examined
            #     and marked with their verdicts. Which verdict appears here is the
            #     substitute's business — it condemns every boundary nothing depends on, so
            #     this fixture has no cleared node to find. That both verdicts reach the
            #     right node state is settled in `review-atlas.test.ts`; what the browser
            #     proves is that the map is on the page, built from live atlas queries.
            #
            #     A tab of the review rather than a section further down it, so it is asked
            #     for. Nothing is inspected until it is: a reading that never opens the map
            #     makes no atlas query at all.
            page.get_by_role("tab", name="Atlas").click()
            page.wait_for_selector(f"{REVIEW_ATLAS} .atlas-canvas", timeout=30_000)
            page.wait_for_selector(f"{REVIEW_ATLAS} .atlas-node--hotspot", timeout=30_000)

            # 14a. The canvas fills its viewport. It used to keep a fixed height while the
            #      viewport stretched to match the taller detail column beside it, leaving
            #      a band of dead background under the graph.
            filled = page.evaluate(
                """() => {
                    const atlas = document.querySelector('[data-slot="review-atlas"]');
                    const viewport = atlas.querySelector('.atlas-viewport');
                    const canvas = atlas.querySelector('.atlas-canvas');
                    return [
                        viewport.getBoundingClientRect().height,
                        canvas.getBoundingClientRect().height,
                    ];
                }"""
            )
            assert filled[0] > 0
            # One pixel of slack for sub-pixel layout rounding, not for a missing rule.
            assert abs(filled[0] - filled[1]) <= 1, filled

            # 14. A finding shows its boundary on that map, without leaving the review.
            #     The question and the answer are one reading, so this selects the node in
            #     place rather than opening a second page to hold it. The control lives in
            #     the finding's own reasoning, so the row is opened to reach it — which is
            #     also the reading it belongs to.
            # 14b. A section is mounted on first visit and kept mounted after. The map is the
            #      reason: it inspects every boundary it draws, so leaving the tab must not
            #      throw that away and coming back must not pay for it again — the reader's
            #      exploration of it survives the trip too. Read off the DOM rather than off
            #      a timing, because "still there but not shown" is exactly the claim.
            page.get_by_role("tab", name="Findings").click()
            page.wait_for_selector(LEDGER, timeout=20_000)
            assert page.locator(f"{REVIEW_ATLAS} .atlas-canvas").count() == 1
            assert not page.locator(f"{REVIEW_ATLAS} .atlas-canvas").is_visible()

            page.locator(f"#BR-001 {ROW}").click()
            page.wait_for_selector("#BR-001[data-state='open']", timeout=10_000)
            atlas = page.get_by_role("button", name="Show BR-001 in the atlas")
            assert atlas.count() == 1
            atlas.first.click()
            page.wait_for_selector(f"{REVIEW_ATLAS} .atlas-node--active", timeout=30_000)
            # Still on the review: nothing navigated away.
            assert page.locator(REVIEW_PAGE).count() == 1

            # 15a. Clicking a node answers where the click was made. It used to set the
            #      location hash, which threw the reader back up to the finding, and to
            #      re-centre the canvas, which dragged the graph out from under the pointer.
            node = page.locator(f"{REVIEW_ATLAS} [data-atlas-node-id]").first
            # Brought into view first, and only then measured: Playwright scrolls to an
            # element before clicking it, and that scroll is the harness's, not the page's.
            node.scroll_into_view_if_needed()
            page.wait_for_timeout(700)  # let both smooth scrolls settle
            before = page.evaluate(
                """() => {
                    const atlas = document.querySelector('[data-slot="review-atlas"]');
                    const canvas = atlas.querySelector('.atlas-canvas');
                    return [window.scrollY, canvas.scrollLeft, canvas.scrollTop];
                }"""
            )
            url_before = page.url
            node.click()
            page.wait_for_timeout(700)
            after = page.evaluate(
                """() => {
                    const atlas = document.querySelector('[data-slot="review-atlas"]');
                    const canvas = atlas.querySelector('.atlas-canvas');
                    return [window.scrollY, canvas.scrollLeft, canvas.scrollTop];
                }"""
            )
            assert before == after, (before, after)
            # Compared rather than asserted absent: a citation clicked earlier left a hash
            # in the URL, and what matters is that selecting a node does not write one.
            assert page.url == url_before

            # 15. Past reviews are a standing record with their own place, grouped by the
            #     case each judged, and reopen from there. The start step keeps a pointer,
            #     not a listing that grows without limit under it.
            page.goto(f"{workspace_url}/start", wait_until="networkidle")
            page.wait_for_selector(COMMIT, timeout=20_000)
            assert page.locator(REVIEW_ROW).count() == 0
            # Substring, because the count and its plural are both part of the label.
            page.get_by_role("link", name="in this workspace").click()
            page.wait_for_url("**/reviews", timeout=20_000)
            page.wait_for_selector(REVIEW_ROW, timeout=20_000)
            # Grouped by the case each judged, and the group is headed by that case: the two
            # passes of one review are one history rather than two unrelated results.
            assert CASE_TITLE in page.locator("[data-slot='ledger-bar']").first.inner_text()
            # The row says what the review came to: every run this workspace has started is
            # listed, so the outcome is what tells them apart. A run still in progress says
            # so instead — proved against the repository, since the substitute answers
            # faster than a browser can look.
            outcome = page.locator(f"{REVIEW_LINK} {VERDICT}").first.inner_text().lower()
            assert "should change" in outcome, outcome
            page.locator(REVIEW_LINK).first.click()
            page.wait_for_selector(REVIEW_PAGE, timeout=20_000)

            # 16. The standalone atlas explorer is gone entirely. The only map is the one
            #     inside a review, where a boundary is already the question being asked.
            page.goto(f"{workspace_url}/start", wait_until="networkidle")
            assert page.get_by_role("link", name="Policies").count() == 1
            assert page.get_by_role("link", name="Repositories").count() == 0
            assert page.get_by_role("link", name="Explore this atlas").count() == 0

            # 17. Neither superseded path 404s; both land on the step that replaced them.
            #     Waited on by URL and by the sheet that only this step draws — the showcase
            #     at `/` carries a "Start a review" of its own, so the words alone would pass
            #     for a redirect that had gone nowhere.
            for superseded in ("cases", "repositories"):
                page.goto(f"{workspace_url}/{superseded}", wait_until="networkidle")
                page.wait_for_url("**/start", timeout=20_000)
                page.wait_for_selector(COMMIT, timeout=20_000)
        finally:
            browser.close()


def test_the_two_passes_of_one_case_are_one_history(workspace_url: str) -> None:
    """A second pass stands beside the first rather than correcting it.

    Depends on the walkthrough above, which is the point: what is proved here is that the two
    passes it produced — the one that held, and the one that concluded against the reader's
    answer — are one history under the case they both judged, and that both still open from
    there.

    Nothing here authors or revises a case, because nothing in the browser does any more.
    Answering the questions is what writes a case now, so the revision this reads back is the
    one the answer above produced. Revising is not driven from the review being read either:
    that page used to carry a "revise and review again" button and a pair of arrows to the
    neighbouring passes, and navigating by case revision landed a reader on the in-progress
    screen of a review that was not there. The listing is what replaced them — every run of
    one case under that case, the newest marked, in the place that holds every other run too.
    """

    playwright = pytest.importorskip("playwright.sync_api")

    with playwright.sync_playwright() as driver:
        browser = driver.chromium.launch()
        page = browser.new_page(viewport={"width": 1280, "height": 900})
        try:
            # 1. Two rows under one case, each saying which revision it ran against and which
            #    of them is the latest. Derived from the reviews of that case rather than
            #    stored on either of them, which is why answering once produces a history
            #    without anything having to link the two.
            page.goto(f"{workspace_url}/reviews", wait_until="networkidle")
            page.wait_for_selector(REVIEW_ROW, timeout=20_000)
            group = page.locator("[data-slot='case-history']").filter(has_text=CASE_TITLE)
            rows = group.locator(REVIEW_LINK)
            assert rows.count() == 2, rows.all_inner_texts()
            assert "case rev 2" in rows.first.inner_text().lower()
            assert "latest" in rows.first.inner_text().lower()
            assert "case rev 1" in rows.last.inner_text().lower()

            # 2. The first pass is kept exactly as it stood: still holding, still without a
            #    conclusion. Answering it produced the pass beside it rather than filling this
            #    one in, so what the reader's answer changed stays checkable against what was
            #    judged before it.
            rows.last.click()
            # Waited on rather than read once: the page header is drawn while the review is
            # still being read back, so the banner is the first thing on it that can only mean
            # the record arrived and says it is holding. Reading the absence of a conclusion
            # before that would be reading an empty page.
            page.get_by_role("button", name="Answer 1 question").wait_for(
                state="visible", timeout=20_000
            )
            held = page.url
            assert page.locator(OVERVIEW).count() == 0

            # 3. The second is the one with a conclusion, and it prints what it is pinned to
            #    rather than implying it — the case revision on the band that leads the page,
            #    beside the atlas, the policies and the model the verdicts were reached with.
            #    The labels are uppercased by the stylesheet, so compare against rendered text.
            page.go_back()
            page.wait_for_selector(REVIEW_ROW, timeout=20_000)
            page.locator("[data-slot='case-history']").filter(has_text=CASE_TITLE).locator(
                REVIEW_LINK
            ).first.click()
            page.wait_for_selector(OVERVIEW, timeout=20_000)
            assert page.url != held
            header = page.locator("[data-slot='page-header']").inner_text().lower()
            assert "case rev 2" in header, header
            pinned = page.locator("[data-slot='band-facts']").inner_text().lower()
            assert "atlas" in pinned, pinned
            assert "policies" in pinned, pinned
            assert "model" in pinned, pinned
        finally:
            browser.close()


def test_a_review_being_produced_has_one_page_that_says_so(
    workspace_url: str,
    workspace: Runtime,
) -> None:
    """The in-progress surface, on the review's own page and nowhere else.

    Written into the store rather than raced against a real run: the substitute answers
    faster than a browser can look, so the only way to see the surface is to put the
    workspace into the state the surface exists for — which is also exactly what a second
    tab, a reload, or a run started from the CLI would find.
    """

    playwright = pytest.importorskip("playwright.sync_api")
    reviews = workspace.review_repository.list()
    assert reviews, "the tests above must have left a review to copy identity from"
    finished = workspace.review_repository.get(reviews[0].review_id)
    running = finished.model_copy(
        update={
            "review_id": "rev_browserinprogress",
            "status": ReviewStatus.RUNNING,
            "report": None,
            "markdown_report": None,
        }
    )
    workspace.review_repository.begin(running)
    workspace.review_repository.record_progress(running.review_id, detected=6, reviewed=2)

    with playwright.sync_playwright() as driver:
        browser = driver.chromium.launch()
        page = browser.new_page(viewport={"width": 1280, "height": 900})
        try:
            # 1. The listing says it is running, and how far it has got.
            page.goto(f"{workspace_url}/reviews", wait_until="networkidle")
            page.wait_for_selector(REVIEW_ROW, timeout=20_000)
            assert "judging 3 of 6" in page.inner_text(LEDGER).lower()

            # 2. Its own page is the place: the stages, what the run is pinned to, and a way
            #    to stop it — not a spinner, and not a second rendering of any of that
            #    elsewhere. The band leads with how far the run got rather than with a
            #    verdict split it has no right to report yet.
            page.goto(f"{workspace_url}/reviews/{running.review_id}", wait_until="networkidle")
            page.wait_for_selector("[data-slot='verdict-band']", timeout=20_000)
            assert page.locator("[data-slot='band-facts']").count() == 1
            assert "judged" in page.locator("[data-slot='band-facts']").inner_text().lower()
            assert page.locator("[data-slot='verdict-pair'] b").inner_text() == "2"
            assert page.locator(OVERVIEW).count() == 0

            # The run's own record is a tab of the review, and it draws the whole journey:
            # the sweep, the judging, the questions, the answers, and the second pass.
            page.get_by_role("tab", name="Run log").click()
            page.wait_for_selector("[data-slot='run-log']", timeout=20_000)
            assert page.locator("[data-slot='run-stage']").count() == 7
            # This tab is not the one running it, and the page says so rather than
            # implying it has detail it cannot have.
            assert "the run's own record" in page.inner_text("[data-slot='run-heading']")
            # And it does not invent the detail it lacks: the boundary names live in the
            # stream this browser is not holding, so the crawl numbers them instead.
            assert page.locator("[data-slot='run-crawl'] li").count() == 6
            assert "boundary 1" in page.locator("[data-slot='run-crawl'] li").first.inner_text()

            # 3. Cancelling from that page ends the run and the page follows.
            page.get_by_role("button", name="Cancel this review").click()
            page.wait_for_selector("text=This review was cancelled", timeout=20_000)
            assert workspace.review_repository.get(running.review_id).status is (
                ReviewStatus.CANCELLED
            )
        finally:
            browser.close()


def test_opening_a_dialog_does_not_slide_the_page_sideways(workspace_url: str) -> None:
    """The page underneath a dialog holds still, to the pixel.

    Which two mechanisms collide here, and why one has to be switched off, is written beside
    the `body[data-scroll-locked]` rule in `styles.css`.

    Only a browser can see this. There is no layout in jsdom, so the unit suite renders the
    same dialog with the same rules and measures nothing at all.

    `--hide-scrollbars` is Playwright's own default for headless, and it is precisely the
    condition under which the bug cannot happen: with no scrollbar to measure the
    compensation is zero and the page holds still for the wrong reason.
    """

    playwright = pytest.importorskip("playwright.sync_api")

    with playwright.sync_playwright() as driver:
        browser = driver.chromium.launch(ignore_default_args=["--hide-scrollbars"])
        page = browser.new_page(viewport={"width": 1440, "height": 800})
        try:
            page.goto(f"{workspace_url}/reviews", wait_until="networkidle")
            gutter = page.evaluate(
                "window.innerWidth - document.documentElement.clientWidth"
            )
            assert gutter > 0, "no scrollbar gutter is reserved, so this proves nothing"

            column = page.locator("header[data-slot='app-bar'] > div")
            before = column.bounding_box()
            assert before is not None

            page.get_by_role("button", name="Search and jump to").click()
            page.wait_for_selector("[data-slot='dialog-content']", timeout=10_000)
            during = column.bounding_box()
            assert during is not None
            assert during["x"] == before["x"], "the page slid sideways under the dialog"
            assert during["width"] == before["width"]

            page.keyboard.press("Escape")
            page.wait_for_selector("[data-slot='dialog-content']", state="detached")
            after = column.bounding_box()
            assert after is not None
            assert after["x"] == before["x"]
        finally:
            browser.close()


def test_a_person_can_delete_a_review_they_no_longer_want(workspace_url: str) -> None:
    """Deleting is not editing: the record goes, rather than being made to say something else.

    Runs last, because it removes what the tests above produced. Cancelling cannot be driven
    here — the substitute answers faster than a browser can reach the button — so what the
    browser proves is the destructive path, and the repository tests prove the stopping.
    """

    playwright = pytest.importorskip("playwright.sync_api")

    with playwright.sync_playwright() as driver:
        browser = driver.chromium.launch()
        page = browser.new_page(viewport={"width": 1280, "height": 900})
        try:
            page.goto(f"{workspace_url}/reviews", wait_until="networkidle")
            page.wait_for_selector(REVIEW_ROW, timeout=20_000)
            before = page.locator(REVIEW_ROW).count()
            assert before > 1, "the tests above must have left several reviews"

            # 1. Behind a menu, and asked twice: a listing where every row carries a live
            #    delete button is a listing you cannot scan without risk.
            page.locator("[data-slot='row-actions'] [data-size='icon']").first.click()
            page.wait_for_selector("[data-slot='row-menu']", timeout=10_000)
            page.get_by_role("menuitem", name="Delete", exact=True).click()
            asked = page.locator("[data-slot='row-menu-ask']").inner_text()
            assert "question threads go with it" in asked

            # 2. And it is possible to change your mind, which is the point of asking.
            page.get_by_role("menuitem", name="Keep it").click()
            assert page.locator("[data-slot='row-menu']").count() == 0
            assert page.locator(REVIEW_ROW).count() == before

            page.locator("[data-slot='row-actions'] [data-size='icon']").first.click()
            page.get_by_role("menuitem", name="Delete", exact=True).click()
            page.get_by_role("menuitem", name="Delete permanently").click()

            # 3. Gone from the listing, and gone from the workspace.
            page.wait_for_function(
                "expected =>"
                " document.querySelectorAll('[data-slot=\"review-row\"]').length === expected",
                arg=before - 1,
                timeout=20_000,
            )
            page.reload(wait_until="networkidle")
            page.wait_for_selector(REVIEW_ROW, timeout=20_000)
            assert page.locator(REVIEW_ROW).count() == before - 1
        finally:
            browser.close()
