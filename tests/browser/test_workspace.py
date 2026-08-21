"""End-to-end: the built workbench, a real browser, and a real workspace server.

The bootstrap lives in `conftest.py` now, because `test_mobile.py` reads the same running
review and producing a second one would double the cost of the suite. What it sets up is
unchanged and described there.
"""

from __future__ import annotations

import pytest

from tests.browser.harness import REVIEW_TIMEOUT_MS

pytestmark = pytest.mark.browser


def _visible(locator, timeout: int = 20_000) -> bool:
    """Wait for a locator, then report it. `is_visible()` does not wait, and every screen
    here arrives through a lazily loaded route chunk."""

    locator.first.wait_for(state="visible", timeout=timeout)
    return True


def test_the_landing_page_leads_into_a_review(page, workspace_url: str) -> None:  # type: ignore[no-untyped-def]
    page.goto(f"{workspace_url}/", wait_until="networkidle")

    assert _visible(
        page.get_by_role(
            "heading",
            name="Write your guidance once. Every review weighs it.",
        )
    )
    # The hero's claim is that a verdict rests on guidance somebody wrote, so the policy it
    # names has to be one the bundled corpus really ships.
    assert _visible(page.get_by_text("Delay abstractions until variation is credible"))
    assert _visible(page.get_by_text("6 retrieved").first)
    # The product's own claim about itself, stated plainly rather than hedged.
    assert _visible(page.get_by_text("It does not roam the repository"))
    page.get_by_role("button", name="Can I use Ollama?").click()
    assert _visible(page.get_by_text("Yes, for both roles").first)

    page.get_by_role("link", name="Review a repository").first.click()
    page.wait_for_url("**/start")
    assert _visible(page.get_by_role("heading", name="Review a repository", level=1))


def test_a_review_produces_a_workbench_with_a_clarification(page, review_url: str) -> None:  # type: ignore[no-untyped-def]
    page.goto(review_url, wait_until="networkidle")

    # The queue is the page, not a tab on it, and it opens on what needs a human.
    page.get_by_text("Attention queue").first.wait_for(timeout=REVIEW_TIMEOUT_MS)
    page.get_by_text("The repository cannot answer these").wait_for(timeout=REVIEW_TIMEOUT_MS)
    assert _visible(page.get_by_role("button", name="Save and rejudge"))
    assert _visible(page.get_by_role("button", name="Conclude with remaining uncertainty"))
    assert _visible(page.get_by_text("Review lineage"))

    # A finding reads as an assessment in three voices, with its provenance folded away
    # until asked for.
    page.get_by_role("button", name="All", exact=False).click()
    page.get_by_role("list", name="Candidates").get_by_role("button").first.click()
    assert _visible(page.get_by_text("Measured").first)
    assert _visible(page.get_by_text("Judged").first)
    assert _visible(page.get_by_text("Standing decision").first)
    # Who judged is attribution and is said out loud: the charter's whole point is that a
    # reader always knows which of the three voices is speaking, and a sentence whose author
    # is one disclosure away is a sentence presented as nobody's. So the identity leads the
    # model's paragraph.
    #
    # The same string then appears a second time, inside `Provenance`, where it is one of the
    # inputs to the analysis hash rather than an attribution — and that copy is folded, which
    # is what a disclosure is for. Under the deterministic provider the model and the prompt
    # are named identically, so these two are told apart by where they are rather than by
    # what they say.
    identity = page.get_by_text("judge:deterministic-v1")
    assert identity.count() == 2
    assert _visible(identity.first)
    # `is_visible()` rather than `_visible()`: the helper waits for the thing to appear, which
    # is right for asserting presence and is twenty seconds of nothing when asserting absence.
    assert not identity.last.is_visible()
    page.get_by_text("Provenance").first.click()
    assert _visible(identity.last)

    # Reading something else about the review does not cost the list.
    page.get_by_role("tab", name="Delta").click()
    assert _visible(page.get_by_role("list", name="Candidates"))
    page.get_by_role("tab", name="Workbench").click()

    # Retrieval is auditable from behind the judgement it audits, naming the retriever that
    # ran — and deterministic retrieval takes the whole corpus and embeds nothing, which the
    # provenance says rather than naming a model it never called.
    page.get_by_role("button", name="Judgement context").first.click()
    drawer = page.get_by_role("dialog", name="Judgement context")
    drawer.wait_for()
    drawer.get_by_role("tab", name="Provenance").click()
    assert _visible(drawer.get_by_text("full-corpus-test-oracle").first)
    assert _visible(drawer.get_by_text("non-embedding strategy").first)
    drawer.get_by_role("button", name="Close panel").click()

    # The embedding this workspace would use is still stated in the shell, beside the
    # reasoning model, because they are two independent selections.
    assert _visible(page.get_by_role("link", name="Embedding").first)
    assert "nomic-embed-text" in page.get_by_role("link", name="Embedding").first.inner_text()


def test_the_report_leads_with_the_summary_and_says_it_once(page, review_url: str) -> None:  # type: ignore[no-untyped-def]
    """The one claim in the product that spans Python and TypeScript with a shared literal.

    `workflow/report.py` writes the summary into the document under a run-in label, because
    the document is downloaded and attached to pull requests and has to stand on its own.
    `surfaces.tsx` hoists the same paragraph out of the document and sets it in the model's
    voice, and drops it from what it renders below so the reader does not meet it twice.

    Neither side can see the other's copy of the label. This can: it opens a real report and
    counts the sentence.
    """

    page.goto(review_url, wait_until="networkidle")
    page.get_by_role("tab", name="Report").click()

    # The deterministic provider writes the stand-in, so the sentence is known here.
    summary = page.get_by_text("This summary was composed deterministically")
    assert _visible(summary.first)
    assert summary.count() == 1
    # Attributed, like every other paragraph the model is responsible for.
    assert _visible(page.get_by_text("In summary").first)
    # And the document underneath is whole.
    assert _visible(page.get_by_text("Where this came from").first)


def test_answering_a_clarification_records_a_new_revision(page, review_url: str) -> None:  # type: ignore[no-untyped-def]
    page.goto(review_url, wait_until="networkidle")
    page.get_by_text("The repository cannot answer these").wait_for(timeout=REVIEW_TIMEOUT_MS)
    first_url = page.url

    answer = page.get_by_placeholder("Add the architectural context").first
    answer.fill("The platform team owns persistence; the domain consumes it through a port.")
    page.get_by_role("button", name="Save and rejudge").click()

    page.wait_for_url(lambda url: url != first_url, timeout=REVIEW_TIMEOUT_MS)
    page.get_by_text("Review 2", exact=False).first.wait_for(timeout=REVIEW_TIMEOUT_MS)

    # The answer became case context, and the lineage now holds both revisions.
    page.get_by_role("tab", name="Workbench").click()
    assert _visible(page.get_by_text("Review lineage"))
    assert _visible(page.get_by_text("case revision 2", exact=False).first)


def test_policies_render_as_markdown_and_navigation_survives_a_phone(  # type: ignore[no-untyped-def]
    page, workspace_url: str
) -> None:
    page.goto(f"{workspace_url}/policies", wait_until="networkidle")

    page.get_by_role("button", name="Author policy").click()
    page.get_by_label("Title").fill("Adapters translate, they do not decide")
    page.get_by_label("Description").fill("Keep decisions in the domain.")

    # The form opens on the scaffold the workspace parser requires, so a policy authored here
    # is one the next review can actually read. Appending a section keeps that true.
    body = page.get_by_label("Policy body")
    body.fill(f"{body.input_value()}\n## Rule\n\nAdapters **translate**.\n\n- No branching\n")
    page.get_by_role("tab", name="Preview").click()
    assert _visible(page.get_by_role("heading", name="Rule"))
    assert _visible(page.get_by_text("No branching"))
    page.get_by_role("button", name="Create policy").click()

    # It is a real policy the next review reads, and its body renders as a document.
    card = page.get_by_role("button", name="Adapters translate, they do not decide")
    card.first.wait_for(timeout=30_000)
    card.first.click()
    assert _visible(page.get_by_role("heading", name="Rule"))

    page.set_viewport_size({"width": 390, "height": 844})
    page.get_by_role("button", name="Open navigation").click()
    drawer = page.get_by_role("dialog", name="ArchCompass")
    drawer.wait_for()
    drawer.get_by_role("link", name="Architecture cases").click()
    page.wait_for_url("**/cases")
    assert _visible(page.get_by_role("heading", name="Architecture cases", level=1))


#: The narrowest phone worth designing for, and the widest that still counts as one. 320 is
#: where `html` sets its own floor, so a page that overflows there overflows by construction
#: rather than by content.
PHONE_WIDTHS = (320, 390, 430)

#: Every page reachable without running a review. The workbench itself is covered by the
#: review test above; these are the ones a visitor lands on first.
STANDING_PAGES = ("/", "/start", "/reviews", "/repositories", "/cases", "/policies", "/settings")


def test_no_page_scrolls_sideways_on_a_phone(page, workspace_url: str) -> None:  # type: ignore[no-untyped-def]
    """A phone may scroll down. Scrolling *across* is always a layout that did not fit.

    This is a rule a comment cannot hold, because nothing about the offending markup looks
    wrong: a flex or grid item is `min-width: auto` by default, and this interface puts
    absolute paths and mono identifiers on screen that are wider than a phone. One of them
    anywhere in a column makes the column that wide, then the page. The base stylesheet
    removes that floor and the panel description breaks long paths; this notices when
    something reintroduces it.
    """

    offenders: list[str] = []
    for width in PHONE_WIDTHS:
        page.set_viewport_size({"width": width, "height": 844})
        for path in STANDING_PAGES:
            page.goto(f"{workspace_url}{path}", wait_until="networkidle")
            overflow = page.evaluate(
                "() => document.documentElement.scrollWidth - document.documentElement.clientWidth"
            )
            if overflow > 0:
                offenders.append(f"{path} at {width}px overflows by {overflow}px")

    assert not offenders, "; ".join(offenders)


def test_the_header_call_to_action_stands_down_on_a_phone(page, workspace_url: str) -> None:  # type: ignore[no-untyped-def]
    """It wrapped onto two lines and squeezed the wordmark against the menu button.

    Asserted through the rendered result rather than the class list, because the class list
    said it was hidden while the cascade said otherwise: `hidden` on a component that sets
    its own `inline-flex` is two display utilities on one element, and `cn` did not resolve
    the conflict until it was taught to. Only the browser knows which won, so the browser is
    what is asked.
    """

    page.set_viewport_size({"width": 390, "height": 844})
    page.goto(f"{workspace_url}/", wait_until="networkidle")
    header = page.locator("header")
    assert header.get_by_role("link", name="Review a repository").count() == 0
    # Still stated on the page it belongs to, a screen-length below.
    assert _visible(page.get_by_role("link", name="Review a repository").first)

    page.goto(f"{workspace_url}/reviews", wait_until="networkidle")
    assert page.locator("header").get_by_role("link", name="New review").count() == 0

    # And back at a width that has room for it.
    page.set_viewport_size({"width": 1440, "height": 960})
    assert _visible(page.locator("header").get_by_role("link", name="New review"))


#: Every tab of the workbench. The workbench is the page a reviewer actually spends time on,
#: and each tab is a different layout — a finding, a list, a rendered report, a transcript.
WORKBENCH_TABS = ("Workbench", "Delta", "Report", "Ask")


def test_the_workbench_fits_a_phone_on_every_tab(page, review_url: str) -> None:  # type: ignore[no-untyped-def]
    """Two ways for a tab to not fit, and this asks about both.

    The page scrolling sideways is the visible one. The other is a box that overflows inside
    an ancestor which hides it — the finding is `overflow-hidden`, so a participant chip
    wider than the column was not escaping the panel, it was being sliced mid-identifier
    inside it, and the page measured clean the whole time.

    The example repository's names are short (`ports.Clock`), so this will not reproduce the
    identifier that found the bug; `overflow.test.tsx` holds that case. This one is about the
    layout itself, which does not depend on how long a name happens to be.
    """

    clipped = """() => {
      const out = [];
      for (const el of document.querySelectorAll('body *')) {
        const over = el.scrollWidth - el.clientWidth;
        if (over <= 1) continue;
        const style = getComputedStyle(el);
        if (style.overflowX !== 'hidden' && style.overflowX !== 'clip') continue;
        const names = el.className.baseVal ?? el.className ?? '';
        // Truncation and line clamping clip on purpose, and say so in the class list.
        if (/\\btruncate\\b|\\bsr-only\\b|line-clamp/.test(names)) continue;
        out.push(`${names.slice(0, 60)} by ${over}px`);
      }
      return out;
    }"""

    offenders: list[str] = []
    for width in PHONE_WIDTHS:
        page.set_viewport_size({"width": width, "height": 844})
        page.goto(review_url, wait_until="networkidle")
        for tab in WORKBENCH_TABS:
            page.get_by_role("tab", name=tab).first.click()
            page.wait_for_timeout(250)
            across = page.evaluate(
                "() => document.documentElement.scrollWidth - document.documentElement.clientWidth"
            )
            if across > 0:
                offenders.append(f"{tab} at {width}px scrolls across by {across}px")
            for hidden in page.evaluate(clipped):
                offenders.append(f"{tab} at {width}px clips {hidden}")

    assert not offenders, "; ".join(offenders)
