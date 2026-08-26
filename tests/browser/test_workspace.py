"""End-to-end: the built workbench, a real browser, and a real workspace server.

The bootstrap lives in `conftest.py` now, because `test_mobile.py` reads the same running
review and producing a second one would double the cost of the suite. What it sets up is
unchanged and described there.
"""

from __future__ import annotations

import re

import pytest
from playwright.sync_api import expect

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

    # The docket is the page, not a tab on it, and it opens on what needs a human.
    page.get_by_text("settled").first.wait_for(timeout=REVIEW_TIMEOUT_MS)
    page.get_by_text("wants an answer").first.wait_for(timeout=REVIEW_TIMEOUT_MS)
    assert _visible(page.get_by_role("button", name="Save and rejudge"))
    assert _visible(page.get_by_role("button", name="Conclude with remaining uncertainty"))
    assert _visible(page.get_by_text("Review lineage"))

    # A finding reads as an assessment in three voices, with its provenance folded away
    # until asked for.
    page.get_by_role("button", name="All", exact=False).click()
    page.locator("[data-candidate]").first.click()
    assert _visible(page.get_by_text("Measured").first)
    assert _visible(page.get_by_text("Judged").first)
    assert _visible(page.get_by_text("Standing decision").first)
    # Who judged is attribution and is said out loud: the charter's whole point is that a
    # reader always knows which of the three voices is speaking, and a sentence whose author
    # is one disclosure away is a sentence presented as nobody's. So the identity sits on the
    # `Judged` line itself, above the model's paragraph — which is what `docs/design-system.md`
    # promises the model's voice is ("the reading size, under a line naming the model that
    # produced it").
    #
    # The same identity is recorded a second time inside `Provenance`, where it is one of the
    # inputs to the analysis hash rather than an attribution — and that copy is folded, which
    # is what a disclosure is for.
    #
    # **Asserted by where each copy is, not by counting a string on the page.** This used to
    # count two matches of `judge:deterministic-v1` and call the first one the attribution
    # line. It never was: that literal is the *prompt* identity
    # (`DETERMINISTIC_JUDGE_PROMPT_IDENTITY`), and the deterministic judge's model identity is
    # `fake:deterministic-architecture-v4` — so both matches were inside `Provenance`, one in
    # its closed summary and one in its `Prompt` row, and the attribution line was never read.
    # Shortening that summary to twelve characters of prompt identity took one of the two away
    # and nothing a reader sees moved. A count over the whole page cannot tell those apart;
    # scoping each half to the element that carries the promise can, and it survives the next
    # reformat of either line.
    model = "fake:deterministic-architecture-v4"
    # The parent of the voice word is the attribution line, so this asserts adjacency — the
    # identity is *on* the `Judged` line — rather than merely somewhere in the finding.
    judged_line = page.get_by_text("Judged", exact=True).first.locator("xpath=..")
    expect(judged_line).to_contain_text(model)

    provenance = page.locator("details", has=page.get_by_text("Provenance", exact=True)).first
    recorded = provenance.get_by_text(model)
    assert recorded.count() == 1
    # `is_visible()` rather than `_visible()`: the helper waits for the thing to appear, which
    # is right for asserting presence and is twenty seconds of nothing when asserting absence.
    assert not recorded.is_visible()
    provenance.get_by_text("Provenance", exact=True).click()
    assert _visible(recorded)

    # Reading something else about the review does not cost your place in the list: the same
    # row is still open when you come back.
    #
    # `expect` rather than a bare `count()`, because which surface is on screen is a URL
    # change now — `?tab=delta` — and a router navigation renders in a transition rather than
    # in the click that asked for it. A count read in the same tick reads the docket before it
    # has painted, which is a race the assertion had all along and only now loses.
    page.get_by_role("tab", name="Delta").click()
    expect(page).to_have_url(re.compile(r"\?tab=delta$"))
    page.get_by_role("tab", name="Docket").click()
    expect(page.locator("[data-candidate][aria-expanded='true']")).to_have_count(1)

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


def test_answering_a_clarification_completes_the_revision(page, review_url: str) -> None:  # type: ignore[no-untyped-def]
    """A question is answered by picking, and the box is what you reach for when none fit.

    This used to type into the textarea, because a question arrived with nothing to pick
    from and the box was the only way to answer. That is the shape the charter forbids —
    *never make someone type what they could pick* — and it was invisible for as long as the
    round could produce a blank box. The model now has to propose two to four answers, so
    the common case is a click and the box is the escape hatch it was meant to be.
    """

    page.goto(review_url, wait_until="networkidle")
    page.get_by_text("wants an answer").first.wait_for(timeout=REVIEW_TIMEOUT_MS)
    first_url = page.url

    choices = page.get_by_role("radio")
    choices.first.wait_for(timeout=REVIEW_TIMEOUT_MS)
    # The proposed answers, plus the one that is always offered last whatever was proposed.
    assert choices.count() >= 3
    own = page.get_by_role("radio", name="Something else", exact=False)
    assert own.count() == 1
    # Never a closed set: choosing it opens the box, and the box is empty rather than
    # pre-filled with the model's sentence.
    own.click()
    written = page.get_by_placeholder("Add the architectural context").first
    assert _visible(written)
    assert written.input_value() == ""

    # Answered by picking, which is the way through this round that the product is for.
    choices.first.click()
    page.get_by_role("button", name="Save and rejudge").click()

    # Answering does not navigate to the run's own address — that used to swap the heading,
    # the findings and the surface for a progress list, on a review the reader was already
    # looking at. But it does not leave them on the record their answer superseded either.
    # The page waits where it is and then carries them to the revision they asked for, which
    # is the whole reason they answered.
    #
    # Waiting on the URL rather than on a click: nothing here presses anything after "Save
    # and rejudge", and arriving anywhere at all is the assertion.
    page.wait_for_url(lambda url: url != first_url, timeout=REVIEW_TIMEOUT_MS)
    page.get_by_text("Review 1", exact=False).first.wait_for(timeout=REVIEW_TIMEOUT_MS)
    # And it is the current record, not another earlier one: the banner that says otherwise
    # is drawn on every superseded record, and this page must not be showing it.
    assert page.get_by_role("link", name="Read the current record").count() == 0

    # Back does not go to the record that announces itself as out of date. The follow
    # replaces rather than pushes, so the way back from here is where the reader came from.
    assert page.url != first_url

    page.get_by_role("tab", name="Docket").click()
    assert _visible(page.get_by_text("Review lineage"))
    assert _visible(page.get_by_text("case revision 2", exact=False).first)
    # One review, one entry. Answering did not add a revision to the rail.
    assert page.get_by_text("One immutable revision").count() == 1

    # And the round it asked is readable as a round, with what was said to it — which existed
    # nowhere before and is the reason a reader can tell a second round from the first.
    page.get_by_role("tab", name="Rounds").click()
    assert _visible(page.get_by_text("Round 1", exact=False).first)


#: The nine `##` sections the workspace parser requires, in the editor's own order, each
#: with prose of its own rather than the prompt the form prints beside it. Bold and a bullet
#: sit under Guidance so the preview has real Markdown to render.
_POLICY_SECTIONS = (
    ("Intent", "Keep the decision about *what to do* out of the code that talks to a vendor."),
    (
        "Guidance",
        "An adapter **translates** between a vendor's shape and ours, and nothing more.\n\n"
        "- No branching in an adapter on anything the domain could decide\n"
        "- No default that is really a policy",
    ),
    ("Signals", "A vendor client with an `if` on a domain enum in it."),
    ("Diagnostic questions", "Would this branch survive swapping the vendor out?"),
    ("Likely consequences", "The rule is discovered twice and the two copies disagree."),
    ("Exceptions", "A retry policy the vendor's own SDK owns is theirs, not ours."),
    ("Positive example", "`git_cli.py` shells out and returns records; `service.py` decides."),
    ("Counterexample", "An HTTP client that decides which repositories are allowed."),
    ("Related policies", "The one about ports being stated in domain terms."),
)


def _authored_policy_body() -> str:
    return "\n\n".join(f"## {name}\n\n{prose}" for name, prose in _POLICY_SECTIONS) + "\n"


def test_policies_render_as_markdown_and_navigation_survives_a_phone(  # type: ignore[no-untyped-def]
    page, workspace_url: str
) -> None:
    page.goto(f"{workspace_url}/policies", wait_until="networkidle")

    page.get_by_role("button", name="Author policy").click()
    page.get_by_label("Title").fill("Adapters translate, they do not decide")
    page.get_by_label("Description").fill("Keep decisions in the domain.")

    # The form opens on the scaffold the workspace parser requires — nine empty `##` headings
    # — and will not save until each one has prose that is not the prompt beside it. This
    # test used to append a tenth section and press the button, which stopped working the
    # day the scaffold stopped writing its own prompts into the draft (`sections.ts:64-79`),
    # and had been reported as a click on a disabled control ever since. Writing all nine is
    # what an author does, so it is what this does.
    body = page.get_by_label("Policy body")
    body.fill(_authored_policy_body())
    page.get_by_role("tab", name="Preview").click()
    # `exact=True` on every one of these. `get_by_role(name=...)` matches a *substring* by
    # default, and the corpus listed under this form is 54 collapsible cards whose headings
    # each carry a strength descriptor — so the loose spelling matched 54 headings and the
    # one it was actually asking about was whichever came first in the DOM. The claim is that
    # `## Guidance` became a heading element, and a heading whose whole name is "Guidance" is
    # what says so.
    assert _visible(page.get_by_role("heading", name="Guidance", exact=True))
    assert _visible(page.get_by_text("No branching in an adapter"))
    page.get_by_role("button", name="Create policy").click()

    # It is a real policy the next review reads, and its body renders as a document.
    card = page.get_by_role("button", name="Adapters translate, they do not decide")
    card.first.wait_for(timeout=30_000)
    card.first.click()
    assert _visible(page.get_by_role("heading", name="Guidance", exact=True))

    page.set_viewport_size({"width": 390, "height": 844})
    page.get_by_role("button", name="Open navigation").click()
    # *Navigation*, not *ArchCompass*. The drawer used to take the product's name as its
    # heading and say "review workbench" under it — two lines of branding at the top of the
    # one surface that exists to say where you can go, sharing no word with the control that
    # opened it or with the landmark inside it. The name moved to the description and the
    # heading now says what the sheet holds. What this test is about is unchanged: the
    # navigation on a phone is a real dialog, opened by name, and its links go where they say.
    drawer = page.get_by_role("dialog", name="Navigation")
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
    """The landing header's call to action stands down; the workspace topbar's does not.

    It wrapped onto two lines and squeezed the wordmark against the menu button.

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
    # The workspace topbar keeps its call to action at every width, which is the opposite of
    # what the landing header above does, and the difference is deliberate. A visitor reading
    # the landing page has the same link a screen below; somebody working has this bar and
    # nothing else, and the drawer is two taps. Below `sm` the wordtext beside the mark gives
    # up its room to pay for it — the chrome stops saying which product it is, which was
    # weighed and chosen rather than overlooked.
    #
    # So what is asked is not that the link stands down. It is that buying the room did not
    # break the bar's shape: the link is there, the bar does not wrap or scroll inside itself,
    # and the page does not go sideways. That is the guard this assertion used to be.
    assert _visible(page.locator("header").get_by_role("link", name="New review"))
    # `.first`, because the page's own `PageHeader` is a `<header>` too and the bar is the
    # one the shell renders above it. The bar itself is that header's single row.
    bar = page.locator("header").first.locator("> div").first
    assert bar.evaluate("e => e.scrollWidth <= e.clientWidth")
    assert page.evaluate(
        "() => document.documentElement.scrollWidth <= document.documentElement.clientWidth"
    )

    # And at a width that has room for the wordtext too.
    page.set_viewport_size({"width": 1440, "height": 960})
    assert _visible(page.locator("header").get_by_role("link", name="New review"))


#: Every tab of the review page. The docket is where a reviewer actually spends their time,
#: and the other three are different layouts — a list, a rendered report, a transcript.
WORKBENCH_TABS = ("Docket", "Delta", "Report", "Ask")


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
