"""End-to-end: the built workbench, a real browser, and a real workspace server.

The bootstrap lives in `conftest.py` now, because `test_mobile.py` reads the same running
review and producing a second one would double the cost of the suite. What it sets up is
unchanged and described there.
"""

from __future__ import annotations

import json
import re
from itertools import pairwise
from typing import Any

import pytest
from playwright.sync_api import expect

from tests.browser.harness import (
    DESKTOP,
    REVIEW_TIMEOUT_MS,
    open_first_candidate,
    show_everything,
)

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
    assert _visible(page.get_by_text("6 found").first)
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
    page.get_by_text("question unanswered").first.wait_for(timeout=REVIEW_TIMEOUT_MS)
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


def test_the_judged_rails_rule_stops_where_its_words_stop(page, review_url: str) -> None:  # type: ignore[no-untyped-def]
    """The one claim about the Judged band that jsdom is structurally unable to check.

    The rail beside the model's argument draws a hairline down its left edge, and a grid item
    stretches down its row by default — so the rule ran the height of the *argument* rather than
    the height of the rail: 239px of margin note at the top of an 1,147px border on the longest
    recorded reasoning, and the rest of it a line with nothing beside it. `lg:self-start` is the
    fix and it is one class, which is what makes it the kind of thing somebody deletes as
    redundant.

    `finding-detail.test.tsx` asserts that class and says in its own comment that it cannot do
    better: jsdom applies no stylesheet and computes no layout, so it can see that
    `lg:self-start` was written and never that it resolved to anything. That is a real gap and
    this is where it closes.

    Two assertions, and they are not the same one twice.

    The first is the mechanism, read out of the cascade. `align-self: start` on the item beats
    `align-items` on the container, so this is the whole of the guarantee and it is exactly what
    a deleted class costs.

    The second is the effect, read off a rectangle — and it is a bound rather than a proof on
    this fixture, which is worth saying plainly. The deterministic judge writes a short
    reasoning, so here the *rail* is the taller of the two and the row's height is its own; the
    defect only paints when the argument is taller. So this bites on a `min-h-full`, a stray
    bottom padding, or any future fixture whose argument outgrows its rail, and it is silent on
    the case that produced the original 908px. That case is the first assertion's.

    Desktop only, deliberately. Below `lg` the grid is one column, the rail carries no border at
    all, and there is nothing here to be true or false.
    """

    page.goto(review_url, wait_until="networkidle")
    page.get_by_role("button", name="All", exact=False).click()
    open_first_candidate(page)
    page.get_by_text("Judged").first.wait_for(timeout=REVIEW_TIMEOUT_MS)

    measured = page.evaluate(
        """
        () => {
          // The argument is the one block on the surface set at the reading size, which is the
          // same property `design-system.test.ts` enforces — so this finds it by the thing that
          // is guarded rather than by a class list that may be rewritten.
          const argument = [...document.querySelectorAll('[class*="text-[16px]"]')][0];
          if (!argument) return null;
          const grid = argument.parentElement;
          // The last of the grid's three children, not the second. The verdict's sentence is a
          // grid item now — placed in the argument's own column so its cap cannot take it past
          // the argument's edge, which the test below measures — so the rail is the argument's
          // neighbour by placement rather than by index.
          const rail = grid.lastElementChild;
          const style = getComputedStyle(rail);
          const last = rail.lastElementChild;
          return {
            columns: getComputedStyle(grid).gridTemplateColumns.split(" ").length,
            alignSelf: style.alignSelf,
            border: style.borderLeftWidth,
            railBottom: rail.getBoundingClientRect().bottom,
            contentBottom: last.getBoundingClientRect().bottom,
          };
        }
        """
    )
    assert measured is not None, "no block at the reading size — the argument moved or lost 16px"
    # The band really is two columns at this width, or the rest of this is about nothing.
    assert measured["columns"] == 2, measured

    # The rule is drawn at all. Without this the two below pass on a rail with no edge, which is
    # a different bug wearing the same numbers.
    assert measured["border"] == "1px", measured
    # Chromium reports `align-self: start` back as `flex-start`, so both spellings of the
    # one value are accepted and `stretch` — which is the default and the defect — is not.
    assert measured["alignSelf"] in {"start", "flex-start"}, measured

    # And it stops where the words stop. One pixel of slack for the sub-pixel rounding a
    # fractional line height leaves on a bounding box; the defect this replaces was 908px.
    overhang = measured["railBottom"] - measured["contentBottom"]
    assert overhang <= 1, f"the rail's rule runs {overhang:.0f}px past its own content"


#: Every docket row's verdict edge, its row's box, and the hairline the list draws under it.
#:
#: Read off the `<ul>` the docket names rather than off a class list, and one entry per list so
#: that "the row after this one" is never a row in a different group. The edge is the only
#: direct-child `<span aria-hidden>` a row draws; it carries no text, so there is nothing else
#: to find it by, and that is the point — nothing here asserts on a class.
DOCKET_EDGES = """
() => [...document.querySelectorAll('ul[aria-label^="Candidates"]')].map((list) =>
  [...list.children].map((item) => {
    const article = item.firstElementChild;
    const edge = article.querySelector(':scope > span[aria-hidden="true"]');
    const edgeStyle = getComputedStyle(edge);
    const itemStyle = getComputedStyle(item);
    const edgeBox = edge.getBoundingClientRect();
    const rowBox = item.getBoundingClientRect();
    const articleBox = article.getBoundingClientRect();
    // What `--rule` resolves to at this row, in the notation `borderBottomColor` answers
    // in, so the two can be compared as strings. A probe rather than a literal: `.band`
    // re-declares `--rule`, so the value is whatever the token means *here*. A
    // `display: none` span computes a colour and no layout, and every box above is
    // already a number.
    const probe = document.createElement('span');
    probe.style.display = 'none';
    probe.style.color = 'var(--rule)';
    item.appendChild(probe);
    const ruleToken = getComputedStyle(probe).color;
    probe.remove();
    return {
      top: edgeBox.top,
      bottom: edgeBox.bottom,
      left: edgeBox.left,
      right: edgeBox.right,
      width: edgeStyle.borderLeftWidth,
      style: edgeStyle.borderLeftStyle,
      colour: edgeStyle.borderLeftColor,
      opacity: edgeStyle.opacity,
      visibility: edgeStyle.visibility,
      depth: edgeStyle.zIndex,
      articleTop: articleBox.top,
      articleBottom: articleBox.bottom,
      rowLeft: rowBox.left,
      rowRight: rowBox.right,
      rule: itemStyle.borderBottomWidth,
      ruleColour: itemStyle.borderBottomColor,
      ruleToken,
      ink: itemStyle.color,
      last: item === list.lastElementChild,
    };
  }),
)
"""

#: Sub-pixel slack, kept as insurance rather than because a measurement needs it.
#:
#: The boxes here are fractional — a row's `<article>`, which is the box every claim below is
#: made against, is 88.89px tall at 1440 and 108.39px at 390, and the first row's edge ends at
#: y=1077.03. (The `<li>` around it is a pixel taller either way, 89.89 and 109.39, because it
#: carries the row rule.) So this arithmetic looks like it has to round.
#: It does not. Every pair compared below is laid out against the same box, so an edge's top
#: and bottom agree with its row's to +0.00 on all six rows, at both widths, in both themes,
#: and every gap between consecutive edges is exactly 1.00. The slack is here against a
#: future layout that does round, and half a pixel is the size for it: everything this test
#: exists to catch is off by one pixel or by nine, never by a fraction.
EDGE_SLACK_PX = 0.5

#: What a computed colour comes back as when nothing is painted. Chromium answers every
#: `transparent` — the keyword, `divide-transparent`, an unset border — in this one spelling.
TRANSPARENT = "rgba(0, 0, 0, 0)"


#: The verdicts dealt across the docket, over the review's findings in the order the API
#: sends them. All three, because the product has three; dealt round-robin so that the deal
#: does not depend on how many findings the example repository happens to produce.
DEALT_VERDICTS = ("material", "held", "cleared")

#: Every docket row's verdict rail, the id of the candidate it belongs to, and what the three
#: verdict hues resolve to at that row.
#:
#: The candidate id is the binding: the verdict a row states is the verdict the response
#: carried for that id, which is a fact the test knows because it wrote it.
#:
#: It is read off `data-candidate`, and that attribute is worth being exact about, because
#: this comment said something false about it and took the claim from `harness.py`, which
#: said the same. Nothing in the application reads it — `docket.tsx:671` writes it onto the
#: row's button and no other non-test line in `frontend/src` mentions it, and the `j`/`k` walk
#: steps through `visible.map((finding) => finding.candidate.id)` in React state
#: (`docket.tsx:1468`) rather than through the DOM. So this is a seam, and the honest reason
#: to prefer it is not that the product navigates by it. It is that the value in it is
#: `finding.candidate.id` — the identity the walk steps through, the key a decision is filed
#: under, and the id this test dealt a verdict to — written by the row itself. A redesign of
#: everything visible about the row leaves it correct; a row's name, position or shape does
#: not survive that.
#:
#: The hues are probed rather than written down, for the reason `DOCKET_EDGES` above probes
#: the row rule: `var(--material)` is what the token means *at this row*, and a literal here
#: would be a second copy of the stylesheet — a copy agrees with the product only until
#: somebody edits one of them.
DOCKET_RAILS = """
() => [...document.querySelectorAll('ul[aria-label^="Candidates"]')].map((list) =>
  [...list.children].map((item) => {
    const article = item.firstElementChild;
    const edge = article.querySelector(':scope > span[aria-hidden="true"]');
    const probe = document.createElement('span');
    probe.style.display = 'none';
    item.appendChild(probe);
    const hue = (token) => {
      probe.style.color = `var(--${token})`;
      return getComputedStyle(probe).color;
    };
    const hues = {
      material: hue('material'),
      held: hue('held'),
      cleared: hue('cleared'),
    };
    probe.remove();
    return {
      candidate: article.querySelector('[data-candidate]').dataset.candidate,
      colour: getComputedStyle(edge).borderLeftColor,
      hues,
    };
  }),
)
"""


def deal_a_mixed_column(page) -> dict[str, str]:  # type: ignore[no-untyped-def]
    """Give the review's findings three different verdicts, and say which one went where.

    **The verdicts are injected. Nothing else here is, and this is what that costs.** It
    proves the workbench draws the verdict it is handed; it proves nothing whatever about
    which verdicts the pipeline produces, and a mixed review is a state this suite has still
    never seen a real judge reach.

    A real fixture was looked for first and there is none. `DeterministicJudge.judge` — the
    only judge any offline run has — reads `Verdict.HELD if hinge else Verdict.CLEARED` at
    `reasoning/adapters/deterministic.py:112`, and its hinge is `None if case.answers` at
    :105. `answers` belongs to the *case*, not to the candidate, so every candidate of one
    review is judged by one question about one shared value and they all come back the same:
    six held before anything is answered, six cleared after. Choosing a different repository
    under `examples/cases/` changes which candidates are found and not what any of them is
    judged. Nor does a second review mix them — the case is a term in
    `CachingArchitectureJudge.key`, so answering moves every key at once and nothing is
    carried forward at the old verdict. `material` is the sharper half of the same fact: this
    judge cannot return it at all, so until this test the accent had never been on a rail in
    any run of this suite. `test_policies_grid.py` established injecting one field of one
    review response on this branch, and states its own limits the same way.

    The deal is round-robin over the findings the response carries, and the docket sorts by
    verdict rank, so the column arrives grouped: with the six candidates this repository
    produces, two material rows, then two held, then two cleared. That leaves exactly one
    boundary where two *coloured* verdicts are drawn one above the other, which is the thing
    being looked for; the test below refuses a docket without one rather than passing
    quietly.

    Returns the deal as `{candidate id: verdict}`. The handler is index-based and so is
    stable across the four-second poll, which re-fetches this response for as long as the page
    is open.
    """

    dealt: dict[str, str] = {}

    def handler(route, request) -> None:  # type: ignore[no-untyped-def]
        response = route.fetch()
        try:
            document: dict[str, Any] = response.json()
        except Exception:  # pragma: no cover - a non-JSON body is not this test's subject
            route.fulfill(response=response)
            return
        for index, finding in enumerate(document.get("findings", [])):
            verdict = DEALT_VERDICTS[index % len(DEALT_VERDICTS)]
            finding["verdict"] = verdict
            dealt[finding["candidate"]["id"]] = verdict
        route.fulfill(response=response, body=json.dumps(document))

    # The review document and not the run that produced it: a single path segment that is not
    # `runs`, which is the pattern `test_policies_grid.py` already reaches this response with.
    page.route(re.compile(r"/api/reviews/(?!runs)[^/?]+$"), handler)
    return dealt


def _rails_of_a_dealt_docket(context, review_url: str):  # type: ignore[no-untyped-def]
    """Open the review in `context`, deal the column, and measure every rail in it.

    A context rather than the shared `page` fixture, because the one thing the caller varies
    is the colour scheme and that is a property of the context. Everything else is the fixture
    verbatim.
    """

    page = context.new_page()
    dealt = deal_a_mixed_column(page)
    page.goto(review_url, wait_until="networkidle")
    show_everything(page)
    page.locator("[data-candidate]").first.wait_for(timeout=REVIEW_TIMEOUT_MS)
    return dealt, page.evaluate(DOCKET_RAILS)


@pytest.mark.parametrize("theme", ["light", "dark"])
def test_a_rail_states_the_verdict_of_its_own_row(browser, review_url: str, theme: str) -> None:  # type: ignore[no-untyped-def]
    """Each row's rail is painted the hue its own verdict names, on a column of three.

    Nothing bound those two together. A verifier retyped `TONE_EDGE.held` as
    `border-l-material` in `ui/meta.tsx`, which paints every held candidate in the docket in
    the accent red, and no gate in the repository failed — not this suite, and not
    `ui/verdict-hues.test.ts`, which asks where the three hues may be *named* and never what
    any of them is paired with. The edge is the third statement of a verdict, after the sign
    and the word, and it is the one a column is read by before any word on it has been read,
    so a held row drawn in the accent is the product's central judgement stated wrongly in the
    register that carries furthest.

    Three layers can each be wrong on their own and two of them are not on screen.
    `verdictOf` maps a verdict to a tone and `TONE_EDGE` maps a tone to a class; both are data
    and both are held in jsdom by `a verdict's hue is the one named after that verdict`,
    which is where a pure mapping belongs. What jsdom cannot see is the rest: it applies no
    stylesheet, so `border-l-held` there is a string rather than a colour, and it cannot see
    whether the docket reaches for those tables at all. That is the whole of this test — a
    verdict on the wire, through the component and the stylesheet, to a colour on a row.

    So the claim is made per row and against the row's own verdict, never against a tally: a
    docket where the material and held rails had swapped hues shows the same two colours in
    the same two counts as a correct one, and only asking each row what verdict it carries
    tells them apart. The colours compared against are `var(--material)`, `var(--held)` and
    `var(--cleared)` resolved at the row itself, and they are checked to be three different
    colours first, because comparing a row against a hue indistinguishable from its
    neighbour's would be a passing test measuring nothing.

    **Settled rows are skipped, and skipping them is why the counts below exist.** A settled
    row draws a full-height *transparent* rail — `settled` picks the colour and never the box,
    which is the invariant `test_the_verdict_edge_is_cut_only_by_the_row_rule` below measures
    — so it makes no claim about hue to check. Every `cleared` row here is one:
    `needsAttention` in `docket-rules.ts` settles a cleared candidate unless a decision was
    taken against a different verdict, so `--cleared` on a rail needs a stale decision and is
    out of this test's reach; it is held one layer down with the other two. That is a sweep
    which could pass by comparing nothing at all, on a branch that has already shipped one of
    those. So it counts what it compared: at least three rows over at least two verdicts, and
    at least one place where two neighbours state two different verdicts in two different
    colours — the mixed column, which no run had ever seen.

    One thing a browser is the wrong instrument for, said here because it is the reason the
    other layer exists. `--held` is declared as the ink itself — `#0a0a0a` in light and
    `#fafafa` in dark, the same two values as `--ink` — so a rail retyped `border-l-ink`
    would paint every held row in a colour indistinguishable from the right one, and this
    test would pass. Nothing on screen can catch that. The class-level pairing in
    `ui/verdict-hues.test.ts` can, and does.

    **Both themes, and it took a mutation to earn the second one.** This ran at the shared
    `page` fixture's colour scheme, which is Chromium's default and so is light — and each of
    the three hues is declared twice, once in `:root` and again in the dark blocks, where
    `--held` and `--cleared` are different values rather than the same ones. So a fault
    confined to the dark half was invisible here. Measured, not reasoned: `--held` overridden
    to `--material` inside `@media (prefers-color-scheme: dark)` and nothing else touched
    left this test passing and painted every held rail in the accent for a dark reader.
    `ui/tokens.test.ts` reads both scopes and would refuse *that* spelling, because it asks
    that `--held` stay colourless; overriding it to `--cleared` instead is neutral, passes
    there too, and was the second mutation this parameter was added for. The review is
    session-scoped, so the second theme costs one more context and one more load, not a
    second review.
    """

    context = browser.new_context(**DESKTOP, color_scheme=theme)
    try:
        rails = _rails_of_a_dealt_docket(context, review_url)
    finally:
        context.close()
    dealt, lists = rails
    rows = [row for listed in lists for row in listed]
    assert rows, "the docket listed no candidates — there is no column here to measure"
    assert dealt, "the review response was never intercepted, so no verdict here was dealt"
    missing = [row["candidate"] for row in rows if row["candidate"] not in dealt]
    assert not missing, f"the docket drew rows the deal never reached: {missing}"

    # Three hues, or a row agreeing with its own verdict says nothing at all. They are close
    # in kind — two of the three verdicts are carried by weight rather than by hue, so
    # `--held` is declared as the ink and `--cleared` as `--ink-3` — which is why this is
    # measured off the running page rather than assumed.
    hues = rows[0]["hues"]
    assert len(set(hues.values())) == 3, (
        f"the three verdict hues resolve to {len(set(hues.values()))} colours: {hues}"
    )

    compared: list[str] = []
    for row in rows:
        # Transparent is the settled rail, which states its verdict in the sign and the word
        # and withdraws the hue. There is no hue here to be wrong.
        if row["colour"] == TRANSPARENT:
            continue
        verdict = dealt[row["candidate"]]
        named = [name for name, value in row["hues"].items() if value == row["colour"]]
        assert row["colour"] == row["hues"][verdict], (
            f"a {verdict} row draws {row['colour']} where its own verdict names "
            f"{row['hues'][verdict]} — "
            + (
                f"that is the hue of {named}"
                # `border-l-held/15` lands here: the right hue at the wrong strength names no
                # verdict at all, and reading "the hue of []" as "of none of them" is a step
                # nobody should have to take at three in the morning.
                if named
                else "and that is no verdict's hue, which is where a right hue at a wrong "
                "alpha comes out"
            )
        )
        compared.append(verdict)

    assert len(compared) >= 3 and len(set(compared)) >= 2, (
        f"the sweep compared {len(compared)} rows over {len(set(compared))} verdicts — a "
        "docket that settled almost everything makes this test pass without measuring a hue"
    )

    # And the column breaks where the verdicts do. This is the sentence the docket's own
    # comment has always made about the rail and nothing had ever run: two verdicts side by
    # side are two segments of two colours, not one bar. Within a list only — two groups are
    # two `<ul>`s with a heading between them.
    segments = [
        (above, below)
        for listed in lists
        for above, below in pairwise(listed)
        if TRANSPARENT not in (above["colour"], below["colour"])
        and above["colour"] != below["colour"]
    ]
    assert segments, (
        "no two neighbouring rows state two different verdicts in two different colours — "
        "the deal reached the page but the column is one hue, so the one thing this test "
        "exists to see is not on screen"
    )


def sweep_the_verdict_edges(lists: list[list[dict]]) -> int:
    """Every claim about the docket's verdict column, over one measurement of it.

    Called twice by the test below, on two different dockets: the column as it loads, where
    this fixture's judge has held all six candidates and every edge is coloured, and the same
    column with one row settled. The claims are about a column of rows and not about a column
    of *coloured* rows, so making them twice is what turns the second into something a run
    has actually seen.

    Returns how many consecutive pairs it compared, so the caller can refuse a docket that
    listed one row per group and would have made the continuity claims vacuous.
    """

    rows = [row for listed in lists for row in listed]
    assert rows, "the docket listed no candidates — there is no column here to measure"

    # The edge is drawn, at the width and in the stroke this is about. Without these two the
    # rest passes on a docket whose verdicts are three pixels of nothing, or three pixels of
    # dashes — different bugs wearing the same numbers, and the second is the reported defect
    # at its maximum: not one hole in the rail per row but one every other pixel.
    #
    # Each of the five below names the property it read and prints only the rows that failed
    # it. They used to print `rows`: six dictionaries of the sixteen keys `DOCKET_EDGES`
    # returns, none of which says which key the assertion had been about — and all five fire
    # on the same subject, a rail that is not drawn, so a dump is the one thing that cannot
    # tell them apart. Worth the five lines because of what one of them is holding: putting
    # `opacity-15` on the rail's span in `docket.tsx` erases the verdict column on screen,
    # was applied and run, and is caught here and by nothing else in the repository — not by
    # `test_a_rail_states_the_verdict_of_its_own_row`, which reads a border colour that
    # `opacity` does not touch, and not by the vitest suite, where a class is a string and
    # nothing computes an opacity at all.
    def _every(name: str, holds, said: str) -> None:  # type: ignore[no-untyped-def]
        broken = [row for row in rows if not holds(row)]
        assert not broken, (
            f"{said}: {[row[name] for row in broken]} on {len(broken)} of {len(rows)} rails"
        )

    _every("width", lambda row: row["width"] == "3px", "a rail is not three pixels wide")
    _every("style", lambda row: row["style"] == "solid", "a rail is not a solid stroke")

    # And it is painted. These three say nothing about the box, which is the reason they are
    # here: every other claim in this function reads a border colour or a bounding rectangle,
    # and all three of `opacity: 0`, `visibility: hidden` and a negative `z-index` leave both
    # of those exactly as a healthy docket reports them. Each one deletes the whole verdict
    # column — measured against the docket at 1440 in light, all three erase the same 1561
    # pixels, every one of them in the rail's own three columns — and each was applied,
    # rebuilt and run against the rest of this sweep unchanged, which passed.
    #
    # `z-index` is the odd one and is included for the same reason as the other two. The
    # `<ul>` is `bg-surface`, which is opaque, so a rail given a stacking order behind it is
    # as gone as one at zero opacity.
    #
    # Negative is the whole of the fault, and this used to admit only `auto` or `0` — which
    # was stricter than the sentence above it and refused a value the rail now needs. An open
    # row's folds are inside `animate-expand`, whose keyframes end on `transform: none` under
    # an animation declared `both`: the retained value computes to `matrix(1, 0, 0, 1, 0, 0)`,
    # which draws nothing and still establishes a stacking context, and a transformed element
    # paints as though it were `z-index: 0`. At `auto` the rail tied with it and lost on tree
    # order, so a fold's opaque `hover:bg-sunken` erased the rail wherever a pointer went.
    # `test_a_hovered_fold_cannot_paint_over_the_verdict_rail` above holds that; this holds
    # the half that has not changed, which is that the rail is never put behind the ground.
    _every("opacity", lambda row: row["opacity"] == "1", "a rail is faded out")
    _every("visibility", lambda row: row["visibility"] == "visible", "a rail is hidden")
    _every(
        "depth",
        lambda row: row["depth"] == "auto" or int(row["depth"]) >= 0,
        "a rail is behind the ground",
    )

    # Every edge is exactly its row's height and starts exactly at its row's left edge.
    #
    # The height is the claim that carries the mixed column. The left edge is what makes the
    # hairline below a cut a reader sees: the edge is pinned to the panel's own content box,
    # and `abs` rather than `<=` is deliberate — an edge that had drifted inboard by any
    # amount at all would still be under the row rule, and would be a stripe down the middle
    # of a row rather than the panel's coloured margin.
    for row in rows:
        assert abs(row["top"] - row["articleTop"]) <= EDGE_SLACK_PX, row
        assert abs(row["bottom"] - row["articleBottom"]) <= EDGE_SLACK_PX, row
        assert abs(row["left"] - row["rowLeft"]) <= EDGE_SLACK_PX, row

    # The hairline is painted, in the hairline's own colour, and it reaches across the three
    # pixels the edge occupies.
    #
    # The colour is not decoration here, it is the whole argument. `--rule` in light is 10%
    # black on white, so the line that cuts the rail composites to 229.5 — 25.5 levels under
    # the surface, in one pixel — and reads as a boundary; anything else there reads as
    # damage. Two ways to lose it, and neither changes a width: `divide-transparent` deletes
    # every row separator on the docket and puts the user's white notch back at 1px instead
    # of 9, and dropping `divide-rule` while keeping `divide-y` falls back to `currentColor`
    # and paints a near-black line the width of the panel. Measured under that second
    # mutation, the row rule comes back `rgb(10, 10, 10)` where the token is
    # `rgba(0, 0, 0, 0.1)`. "Not transparent" catches the first and misses the second, so this
    # asserts the value: the border is what `--rule` resolves to at this row, read off a
    # throwaway probe because `.band` re-declares the token and a literal here would be a
    # second copy of it. `--rule` is nearly the surface colour on purpose, and that is a claim
    # about the token rather than about the docket — `ui/tokens.test.ts` holds it.
    for row in rows:
        if row["last"]:
            # `divide-y` skips the last row, because the panel's own border closes the list.
            continue
        assert row["rule"] == "1px", row
        # The probe answered with something, and something other than the text colour it
        # would inherit if `--rule` had gone missing — without this the comparison below
        # could pass by both sides being wrong in the same direction.
        assert row["ruleToken"] not in {TRANSPARENT, row["ink"]}, row
        assert row["ruleColour"] == row["ruleToken"], row
        assert row["rowRight"] >= row["right"] - EDGE_SLACK_PX, row

    # And the cut is that hairline and nothing more. Compared within one list only: two groups
    # are two `<ul>`s with a heading between them, and the space there is a section break.
    runs = 0
    for listed in lists:
        for above, below in pairwise(listed):
            runs += 1
            gap = below["top"] - above["bottom"]
            assert gap >= 1 - EDGE_SLACK_PX, (
                f"consecutive verdict edges are {gap:.2f}px apart — a run of one verdict "
                "fuses into a bar that reads as the panel's own border"
            )
            assert gap <= 1 + EDGE_SLACK_PX, (
                f"consecutive verdict edges are {gap:.2f}px apart — the row rule is one "
                "pixel, so anything wider is a notch in the edge rather than a boundary"
            )
    return runs


def settle_a_row_with_a_neighbour_either_side(page) -> tuple[int, int]:  # type: ignore[no-untyped-def]
    """Accept one candidate that has a row above it and a row below it, and say which one.

    The bulk bar rather than the row's own decision bar, and the difference matters to what
    is being measured. Deciding from inside a row opens a panel under it and hands the
    reviewer the next row; checking a box and pressing Accept settles a row without opening
    anything, so the docket stays a column of closed rows and the column is the subject.

    Returns the row's position as (list, row), because the caller identifies it by where it
    sits: the docket's order does not depend on decisions, so the index is stable across the
    re-render this causes.
    """

    lists = page.locator('ul[aria-label^="Candidates"]')
    for index in range(lists.count()):
        rows = lists.nth(index).locator("> li")
        if rows.count() < 3:
            continue
        row = rows.nth(1)
        # The box is `opacity-0` until the row is hovered, which hides it from a reader and
        # from nothing else — it has a box, it takes a click, and Playwright agrees.
        row.get_by_role("checkbox").check()
        page.get_by_role("button", name="Accept all").click()
        # The decision is a request to a real workspace, so wait for the thing being waited
        # for: the row's own edge giving up its colour. Nothing else on the row says as
        # early or as exactly that this row is now settled.
        edge = row.locator('article > span[aria-hidden="true"]')
        expect(edge).to_have_css("border-left-color", TRANSPARENT, timeout=REVIEW_TIMEOUT_MS)
        return index, 1
    raise AssertionError(
        "no docket group listed three rows — there is no row here with a neighbour on both "
        "sides, and a settled row at the end of a list does not exercise a mixed column"
    )


#: The rail, and every stacking context between an open row's folds and the article.
#:
#: Paint order is the subject, so this reads the two things that decide it and nothing else:
#: whether an element between a fold and the article establishes a stacking context, and what
#: the rail's own `z-index` resolves to. It reads no class names.
#:
#: A transformed element is painted as though it were `position: relative; z-index: 0`, which
#: is why `makes` treats a transform as an effective zero.
RAIL_PAINT_ORDER = """
() => {
  const button = document.querySelector('[data-candidate]');
  const article = button.closest('article');
  const rail = article.querySelector(':scope > span[aria-hidden="true"]');
  const railZ = getComputedStyle(rail).zIndex;
  const establishes = (el) => {
    const c = getComputedStyle(el);
    if (c.position !== 'static' && c.zIndex !== 'auto') return Number(c.zIndex);
    if (c.transform !== 'none' || c.filter !== 'none' || c.perspective !== 'none') return 0;
    if (parseFloat(c.opacity) < 1) return 0;
    if (c.isolation === 'isolate' || c.mixBlendMode !== 'normal') return 0;
    if (c.willChange !== 'auto' || c.contain !== 'none') return 0;
    return null;
  };
  return [...article.querySelectorAll('details > summary')].map((summary) => {
    const contexts = [];
    for (let el = summary; el && el !== article; el = el.parentElement) {
      const z = establishes(el);
      if (z !== null) contexts.push({ z, transform: getComputedStyle(el).transform });
    }
    return {
      label: summary.textContent.trim().split('\\n')[0],
      background: getComputedStyle(summary).backgroundColor,
      contexts,
      railZ,
    };
  });
}
"""


def test_a_hovered_fold_cannot_paint_over_the_verdict_rail(page, review_url: str) -> None:  # type: ignore[no-untyped-def]
    """An open row's folds sit above the rail in paint order, so the rail needs a z-index.

    Reported as the red line disappearing under the pointer. Measured before the fix, down
    the rail's own three pixels inside the hovered summary's band: `rgb(10, 10, 10)` at rest
    and `rgb(235, 235, 235)` on hover. The rail was not dimmed, it was covered.

    The cause is a stacking context nobody wrote. The open body is `animate-expand`, whose
    keyframes end on `transform: none`, and the animation is declared `both` — so the final
    value is retained after it finishes and the computed transform is
    `matrix(1, 0, 0, 1, 0, 0)` rather than the keyword. It draws nothing and moves nothing.
    But *any* computed transform other than `none` establishes a stacking context, and a
    transformed element paints as though it were `position: relative; z-index: 0`. The rail
    is `absolute` at `z-index: auto`, which is also zero, and a tie is broken by tree order —
    so the body, later in the DOM, won. A summary's `hover:bg-sunken` is opaque, and the
    summary's box starts at x=137, exactly where the rail starts.

    `z-[1]` is the whole fix, and the value is deliberately the smallest that clears zero
    rather than a step on the scale. The sticky bands above this list are `z-20` and `z-30`,
    and a rail scrolling under them must pass behind: measured at `z-[1]`, the pixels across
    both bands are identical to a build with no z-index at all.

    Two claims, because they fail in different directions. If the body stops establishing a
    context the rail's z-index is no longer load-bearing and this test should be reconsidered
    rather than quietly kept; if the rail loses it while the body still has one, the reported
    defect is back. Neither is a class assertion — a rail given `z-[1]` inside a body that
    gained `z-10` would pass a class check and fail here.
    """

    page.goto(review_url, wait_until="networkidle")
    page.get_by_role("button", name="All", exact=False).click()
    open_first_candidate(page)

    folds = page.evaluate(RAIL_PAINT_ORDER)
    assert folds, "the open row drew no folds — there is nothing here that could cover a rail"

    for fold in folds:
        assert fold["contexts"], (
            f"nothing between the {fold['label']!r} fold and the article establishes a "
            "stacking context any more, so the rail's z-index is no longer holding anything "
            "up — read this test's docstring before deleting it"
        )
        highest = max(context["z"] for context in fold["contexts"])
        assert fold["railZ"] != "auto", (
            f"the verdict rail is at z-index auto under the {fold['label']!r} fold, which "
            f"establishes a stacking context at {highest} — the rail is painted over and "
            "vanishes wherever the fold's hover background is drawn"
        )
        assert int(fold["railZ"]) > highest, (
            f"the verdict rail is at z-index {fold['railZ']} and the {fold['label']!r} fold "
            f"establishes a stacking context at {highest}"
        )


def test_the_verdict_edge_is_cut_only_by_the_row_rule(page, review_url: str) -> None:  # type: ignore[no-untyped-def]
    """A run of same-verdict rows is one run of colour, cut where every row is cut.

    The user's report was "there is a gap on the red part": two consecutive material rows,
    each with its verdict as a left edge, and a white notch in the red between them. It was a
    decision rather than a fault. The edge was `inset-y-1`, four pixels of air at each end,
    written to stop a run of same-verdict rows — the common case on a second visit — fusing
    into one unbroken bar that read as the panel's own border rather than as six verdicts.

    That defect was real and the answer was the wrong size. Four pixels above a row boundary,
    four below, and the list's own 1px divider between them is a **nine pixel** break: swept
    on this fixture at 1440, an edge from y=992.14 to y=1073.03 in an 89px row, the next
    beginning at y=1082.03. Every other seam on this surface is one pixel. Nine is not a
    boundary, it is a hole, and the eye reads a hole in a rule as something failing to paint.

    What the notch was for, the list already did. `divide-y` puts a `--rule` hairline on every
    row boundary and it spans the `<li>`'s whole width — the three pixels the edge occupies
    included, because the edge starts at the list's content box and so does the border. So a
    full-height edge is cut once per row, by the one pixel that cuts everything else.

    The half of the old defect that mattered has not come back, and it is worth being exact
    about which half. Six identical verdicts do read as one column of colour with hairline
    ticks in it rather than as six separate marks — but six identical verdicts *are* one run,
    and the question the edge exists to answer is where the red starts, which a continuous
    shape answers better than six pieces do. What made the old bar a defect was that it could
    be taken for the panel's own chrome, and it cannot: the panel's border is one pixel of
    `--rule` on all four sides — 10% black in light, 11% white in dark — where this is three
    pixels of an opaque verdict hue on one, the dimmest of them `--cleared`, which is
    `--ink-3`. Nothing else about the panel is coloured. Where consecutive verdicts differ the
    column visibly breaks into per-row segments, which is exactly where the difference is
    worth seeing — and that half is measured by `test_a_rail_states_the_verdict_of_its_own_row`
    above, on a docket dealt two coloured verdicts, rather than here. Everything below is a
    box and a gap, and holds whatever the rows are coloured.

    Three claims, and they fail in different directions, which is why there are three.

    *Continuity*: consecutive edges are no further apart than that hairline. Restoring
    `inset-y-1` — or any inset — puts nine pixels here and this is what says so.

    *Separation*: they are no closer either. Deleting `divide-y` from the `<ul>`, or writing
    the rule back onto the `<article>` where `:last-child` matched every row and it painted on
    none — the bug this list has already had once — closes the gap to zero and refuses the
    verdicts as six. The two together are the whole property: **exactly one pixel, exactly the
    row's own.**

    *The rule reaches, and is a rule*: the hairline spans the edge's own x and is painted in
    `--rule`. Inset the list's padding past the edge and the gap stays a pixel while the red
    runs straight through it; take the colour off and the gap is still a pixel while the line
    is either invisible or near-black across the whole docket.

    Under all three, the invariant that makes a **mixed** column safe: every edge is exactly
    its row's height, settled or not. `settled` picks the colour and never the box, so a
    settled row is a full-height transparent edge and its neighbours are unaffected by it.
    That claim used to be asserted over a column it had never seen — this fixture's judge
    holds all six candidates, and no browser check decides anything before this one, so every
    edge was coloured every time it ran. So this settles a row in the middle of a run and
    sweeps again. That second sweep is the mixed column.

    Geometry, all of it, so jsdom can see none of it: it applies no stylesheet and computes no
    layout, and the notch stood for as long as it did because the class that drew it was one
    nothing could fail.
    """

    page.goto(review_url, wait_until="networkidle")
    page.get_by_role("button", name="All", exact=False).click()
    page.locator("[data-candidate]").first.wait_for(timeout=REVIEW_TIMEOUT_MS)

    lists = page.evaluate(DOCKET_EDGES)
    rows = [row for listed in lists for row in listed]
    assert [row for row in rows if row["colour"] != TRANSPARENT], (
        "no row states a verdict as an edge — every one of them is transparent"
    )
    assert sweep_the_verdict_edges(lists) >= 1, (
        "the docket listed one row per group — nothing here is a run"
    )

    # And again with a mixed column, which is the state this surface spends its life in and
    # the one nothing had ever measured.
    listed, settled = settle_a_row_with_a_neighbour_either_side(page)
    mixed = page.evaluate(DOCKET_EDGES)
    assert sweep_the_verdict_edges(mixed) >= 1, "the docket lost its rows to a decision"

    # The row that was decided gave up its colour and kept its box, and the rows either side
    # of it kept both. This is the whole of what `settled` is allowed to change.
    assert mixed[listed][settled]["colour"] == TRANSPARENT, mixed[listed][settled]
    for neighbour in (settled - 1, settled + 1):
        assert mixed[listed][neighbour]["colour"] != TRANSPARENT, mixed[listed][neighbour]


#: The widths the lede's residual was found at, plus the two either side of where it closes.
#:
#: `lg` is 1024 and the Judged band splits into two columns there, so the argument stops being
#: the width of the section and becomes a `1fr` track beside a 20rem rail. The rail is fixed and
#: the track is not, so the narrower the viewport the narrower the argument — and the verdict's
#: sentence above it was capped at a *constant* 616px. Swept before the repair: 34.00px past the
#: argument's right edge at 1024, 18.00px at 1040, and agreeing to the deliberate -1.11px from
#: about 1060 up. 1280 is where the rail widens to 26rem, which moves the track again.
JUDGED_BAND_WIDTHS = (1024, 1040, 1060, 1280, 1440)

#: How far short of the argument's right edge the lede is allowed to stop, and how far past it.
#:
#: Past: nothing. The two are drawn one above the other and read as sharing an edge, and the
#: whole subject here is a case where they did not. One pixel of slack for the sub-pixel
#: rounding a fractional track width leaves on a bounding box.
#:
#: Short: the lede's own `max-w-[38.5rem]` is 616px against the argument's `58ch` = 617.12px, so
#: at any width where both caps bite the lede stops 1.12px short by a deliberate choice of round
#: number over matching `ch` count. Anything much larger than that means the sentence has been
#: given a cap of its own again.
LEDE_EDGE_SLACK_PX = 1.5


def test_the_lede_never_reaches_past_the_argument_it_stands_over(page, review_url: str) -> None:  # type: ignore[no-untyped-def]
    """Defect 9's residual, measured across the widths that produced it.

    The verdict's sentence sits directly above the model's argument and reads as sharing its
    right edge. `finding-detail.test.tsx` asserts that in jsdom by resolving both declared
    measures against both declared font sizes — which was the repair for the two of them wearing
    one `58ch`, and which is **blind by construction to this**: a declared measure is a cap, and
    what a block is drawn at is the smaller of that cap and the box it sits in. jsdom computes no
    layout, so it never has the second term. Two caps a pixel apart in boxes 34px apart pass it.

    Which is what the band did. The sentence stood above the grid at the section's full width,
    capped at 616px; the argument stood in a `1fr` track beside a 20rem rail. At 1024 that track
    is 582px. The repair is containment — the sentence is now placed in the argument's own column
    — and jsdom asserts *that*, as a fact about the document. This asserts the rectangles it
    produces, which is the half a class list cannot promise.

    Held at every width above `lg`, and checked below it too: there the band is one column, both
    blocks are laid out in the section, and the caps are all that separate them. The claim is the
    same claim and it is worth knowing it holds on both sides of the breakpoint.
    """

    page.goto(review_url, wait_until="networkidle")
    page.get_by_role("button", name="All", exact=False).click()
    open_first_candidate(page)
    page.get_by_text("Judged").first.wait_for(timeout=REVIEW_TIMEOUT_MS)
    page.evaluate("() => document.fonts.ready")

    for width in (390, *JUDGED_BAND_WIDTHS):
        page.set_viewport_size({"width": width, "height": 1000})
        measured = page.evaluate(
            """
            () => {
              // The argument is the one block on the surface set at the reading size, which is
              // the property `design-system.test.ts` enforces — so it is found by the thing that
              // is guarded rather than by a class list somebody may rewrite.
              const argument = [...document.querySelectorAll('[class*="text-[16px]"]')][0];
              if (!argument) return null;
              // The lede is the 13px semibold sentence above it, and it is identified by its
              // place rather than by its words: the three strings `lib/format` can put here are
              // product copy and this file does not own them.
              const above = [...document.querySelectorAll('p[class*="text-[13px]"]')].filter(
                (node) =>
                  node.compareDocumentPosition(argument) & Node.DOCUMENT_POSITION_FOLLOWING,
              );
              const lede = above[above.length - 1];
              if (!lede) return null;
              return {
                ledeRight: lede.getBoundingClientRect().right,
                argumentRight: argument.getBoundingClientRect().right,
                argumentWidth: argument.getBoundingClientRect().width,
                columns: getComputedStyle(argument.parentElement).gridTemplateColumns,
              };
            }
            """
        )
        assert measured is not None, f"at {width}px the band has no argument and lede to compare"

        past = measured["ledeRight"] - measured["argumentRight"]
        assert past <= LEDE_EDGE_SLACK_PX, (
            f"at {width}px the verdict's sentence ends {past:.2f}px past the argument it stands "
            f"over — argument column {measured['argumentWidth']:.0f}px, tracks "
            f"{measured['columns']}"
        )
        assert past >= -LEDE_EDGE_SLACK_PX, (
            f"at {width}px the sentence stops {-past:.2f}px short of the argument. Both are "
            "capped by the same column, so the only gap they can honestly show is the 1.12px "
            "between 38.5rem and 58ch — anything wider is a second measure that has grown back"
        )


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
    page.get_by_text("question unanswered").first.wait_for(timeout=REVIEW_TIMEOUT_MS)
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
        "- No default that is really a policy\n\n"
        # Below the ramp's fourth step, which is where `ui/markdown.tsx` had no renderer at
        # all: a `#####` and a `######` came out as the browser's own block element, at the
        # panel's full width over paragraphs stopping at the measure. They are here so the
        # assertion below has one of each to measure, and the prose under them is long enough
        # to wrap at any measure this renderer could be given.
        "##### Where an adapter ends\n\n"
        "The line is the record it hands back, and everything past that line is a decision "
        "the domain owns rather than a translation of somebody else's shape.\n\n"
        "###### And where it begins\n\n"
        "At the vendor's own vocabulary, which is the only thing an adapter is allowed to "
        "know that nothing else in the system knows.",
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
    _every_block_stops_at_one_edge(page)
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


#: The blocks a rendered document is allowed to draw past its measure, keyed by the tag.
#:
#: A fence and a table scroll inside themselves, so capping them would take the panel's width
#: away from the excerpt or the readings somebody came to read; a rule is not text at all and
#: spans what it divides. `ui/markdown.tsx` argues all three where the wrapper is left at
#: `max-w-none`, and `ui/markdown.test.tsx` holds the same three names.
_REACHES_PAST_THE_MEASURE = ("PRE", "HR")


def _every_block_stops_at_one_edge(page) -> None:  # type: ignore[no-untyped-def]
    """The measure a document is read at, as rectangles rather than as declared class lists.

    `ui/markdown.test.tsx` asserts this in jsdom, which lays nothing out: it resolves each
    declared measure against the declared type and checks the answers agree. That is the right
    test for the arithmetic and it cannot see the failure this one is about — an element with
    **no renderer at all**, which declares nothing to resolve and is drawn by the browser's own
    sheet at the full width of the panel. `#####` and `######` shipped that way, at 1168px over
    paragraphs stopping at 428px, and every measure assertion in the suite passed because every
    element that *had* a measure agreed about it.

    So this asks the layout engine instead. Every direct child of the rendered document either
    stops at the one edge the text blocks share or is one of the two that deliberately reach
    past it. A table is excluded by ancestry rather than by tag, because it is drawn inside an
    `overflow-x-auto` wrapper that is a plain `<div>` and a `<div>` is not a name worth
    excepting on.

    Delete the `h5` and `h6` entries from `RENDERERS`, rebuild, and this reports
    ``2 different right edges: [('H3', [428, ...]), ('H5', [1092]), ('H6', [1092]),
    ('P', [428, ...]), ('UL', [428])]`` — 1092px because that is the policy preview's own
    panel, where the finding's is 1168px. Which is the second reason this is a rectangle and
    not a class list: the number depends on the panel, and only one of the two blocks in that
    comparison has a number of its own at all.
    """
    document = page.locator("div.max-w-none").filter(
        has=page.get_by_role("heading", name="Guidance", exact=True)
    )
    blocks = document.locator("> *")
    widths: dict[str, list[float]] = {}
    for index in range(blocks.count()):
        block = blocks.nth(index)
        box = block.bounding_box()
        if box is None or box["width"] == 0:
            continue
        tag = block.evaluate("element => element.tagName")
        if tag in _REACHES_PAST_THE_MEASURE or block.locator("table").count():
            continue
        widths.setdefault(tag, []).append(round(box["width"], 2))

    measured = {width for group in widths.values() for width in group}
    assert len(measured) == 1, (
        "the blocks of a rendered document stop at "
        f"{len(measured)} different right edges: {sorted(widths.items())}"
    )
    # The two levels that had no renderer, named rather than left to the count: a fifth and a
    # sixth heading have to actually be in the document for the rule above to be about them.
    assert "H6" in widths, "the fixture no longer renders a heading below the ramp's fourth step"


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


# --------------------------------------------------------------------------------------
# The Ask composer: one box, and the pending question inside the measure it will be read at
# --------------------------------------------------------------------------------------

#: The composer's cap, in CSS pixels. `38.5rem`, and derived rather than chosen — the answer
#: above it is `ModelProse` at 58ch/16px, which draws 617.12px, so this is that column's edge
#: to within about a pixel. `conversation-thread.tsx` carries the argument; what is asserted
#: here is that the number survives a redesign of the element it sits on.
COMPOSER_WIDTH_PX = 616.0

#: A `getBoundingClientRect` is snapped to a 1/64px grid, and a hairline is a real pixel of
#: containment either way. One pixel absorbs the first and cannot hide the second.
COMPOSER_SLACK_PX = 1.0

#: The charter's fifth principle, and the size `ui/button.tsx` gives a `md` button so that it
#: clears the floor without a call site asking.
#:
#: It is checked *here*, in a narrow window with an ordinary pointer, and that is deliberate.
#: `test_mobile.py` sweeps every target on a real phone and now includes this surface, but a
#: phone reports a coarse pointer, and on a coarse pointer the dense `sm` size grows to 44 by
#: itself — so a composer whose button had been shrunk to fit inside the field would pass there
#: and be 32px on every desk. This is the context that can still tell the two sizes apart.
TAP_TARGET_MINIMUM_PX = 44

#: Where the parts of the composer are, and what draws an edge.
#:
#: The box is found by walking up from the textarea to the first ancestor with a border, which
#: is what "the field's edge" means as a fact about the drawing rather than as a class list.
#: On the old arrangement that walk stops on the textarea itself, and the button is not inside
#: it — which is the assertion, and the reason the walk is written this way rather than as a
#: parent lookup that would be true of any markup at all.
_COMPOSER = r"""
() => {
  const area = document.querySelector('textarea[aria-label]');
  if (!area) return null;
  const bordered = (el) => parseFloat(getComputedStyle(el).borderTopWidth) > 0;
  let box = area;
  while (box && !bordered(box)) box = box.parentElement;
  if (!box) return null;
  // `:not([role])` is load-bearing: the surface switcher above this panel has a tab that
  // also says Ask, and finding that one instead makes every assertion below a statement
  // about the tablist. Found document-wide rather than inside the box on purpose — asking
  // the box for its own button would make the containment true by construction.
  const button = [...document.querySelectorAll('button:not([role])')].find(
    (b) => (b.innerText || '').trim() === 'Ask',
  );
  if (!button) return null;
  const r = (el) => {
    const b = el.getBoundingClientRect();
    return {left: b.left, right: b.right, top: b.top, bottom: b.bottom,
            width: b.width, height: b.height};
  };
  return {
    box: r(box),
    area: r(area),
    button: r(button),
    boxIsTheTextarea: box === area,
    buttonInBox: box.contains(button),
    areaBorder: parseFloat(getComputedStyle(area).borderTopWidth),
    boxBorder: parseFloat(getComputedStyle(box).borderTopWidth),
  };
}
"""

#: A question long enough to fill the field and then some, so "the text never runs under the
#: button" is asked of text that would if anything could.
_A_LONG_QUESTION = (
    "Why does archcompass.reasoning.adapters.selected depend on archcompass.bootstrap, and "
    "is that the deliberate seam the boundary policy describes or the leak it forbids, given "
    "that the module is imported by the factory and by the cache and by nothing else at all?"
)


def _open_ask(page) -> None:  # type: ignore[no-untyped-def]
    """The Ask surface, with the composer rendered.

    The tab is reached through the surface tablist rather than by name-on-the-page, for the
    reason `harness.py` gives about copy being rewritten around these tests.
    """

    page.locator('[role="tablist"]').first.wait_for(state="visible", timeout=REVIEW_TIMEOUT_MS)
    page.locator('[role="tablist"]').first.get_by_role("tab", name="Ask").click()
    page.locator("textarea[aria-label]").first.wait_for(state="visible", timeout=20_000)


@pytest.mark.parametrize("theme", ["light", "dark"])
@pytest.mark.parametrize("width", [1440, 390])
def test_the_ask_composer_reads_as_one_control(  # type: ignore[no-untyped-def]
    browser, review_url: str, theme: str, width: int
) -> None:
    """The button is inside the field it acts on, and that is a rectangle rather than a class.

    `conversation-thread.test.tsx` asserts the containment as a fact about the document, which
    is the half jsdom can see. This is the half it cannot: that the element carrying the field's
    edge really does enclose the button, that the composer still stops at the width somebody
    derived for it, and that the text and the button never share any of the same vertical — the
    cost that sank the chat-app arrangement where the button floats over the field's corner.

    Both themes, because the composer's edge is `--rule-control` and the whole reason that token
    exists is that in light `--control` and `--surface` are both `#ffffff`, so the hairline is
    the entire affordance on one of the two grounds and nothing else says where the box is.

    Both widths, because "reads as part of the field" is the claim at 390 and at 1440 alike.
    390 here is a narrow window rather than a phone — a real phone, with the coarse-pointer
    branches that come with one, is `test_mobile.py`'s, for the reason `TAP_TARGET_MINIMUM_PX`
    gives above.
    """

    context = browser.new_context(
        viewport={"width": width, "height": 900}, color_scheme=theme
    )
    page = context.new_page()
    try:
        page.goto(review_url, wait_until="networkidle")
        _open_ask(page)
        page.evaluate("() => document.fonts.ready")

        # Empty, then holding more than it can show. The second is what asks whether a long
        # question runs under the button; the first is what asks about the placeholder, which
        # occupies the same lines the first line of a question would.
        for state, typed in (("empty", ""), ("a long question", _A_LONG_QUESTION)):
            if typed:
                page.locator("textarea[aria-label]").first.fill(typed)
            measured = page.evaluate(_COMPOSER)
            assert measured is not None, (
                f"at {width}px in {theme} the Ask surface has no composer to measure"
            )
            where = f"at {width}px in {theme}, {state}"

            # The redesign, as a rectangle. On the arrangement this replaced the walk above
            # stops on the textarea and this line is what fails.
            assert not measured["boxIsTheTextarea"], (
                f"{where}: the only bordered element is the textarea itself, so the button is "
                "outside the field again"
            )
            assert measured["buttonInBox"], f"{where}: the Ask button is not inside the field's box"
            box, button, area = measured["box"], measured["button"], measured["area"]
            for side, inside, outside in (
                ("left", button["left"], box["left"]),
                ("top", button["top"], box["top"]),
            ):
                assert inside >= outside - COMPOSER_SLACK_PX, (
                    f"{where}: the button's {side} edge is {outside - inside:.2f}px outside the box"
                )
            for side, inside, outside in (
                ("right", button["right"], box["right"]),
                ("bottom", button["bottom"], box["bottom"]),
            ):
                assert inside <= outside + COMPOSER_SLACK_PX, (
                    f"{where}: the button's {side} edge is {inside - outside:.2f}px outside the box"
                )

            # One edge, on the box. Two would be the two-boxes look coming back by another route.
            assert measured["boxBorder"] > 0 and measured["areaBorder"] == 0, (
                f"{where}: the field is drawn with {measured['boxBorder']}px on the box and "
                f"{measured['areaBorder']}px on the textarea, which is two edges, not one"
            )

            # Nothing typed can reach the button, because the two never share a row.
            assert area["bottom"] <= button["top"] + COMPOSER_SLACK_PX, (
                f"{where}: the text area overlaps the button by "
                f"{area['bottom'] - button['top']:.2f}px, so a long question runs under it"
            )

            # The derived cap, on the element that is now drawn at it.
            if width == 1440:
                assert abs(box["width"] - COMPOSER_WIDTH_PX) <= COMPOSER_SLACK_PX, (
                    f"{where}: the composer is {box['width']:.2f}px wide rather than "
                    f"{COMPOSER_WIDTH_PX:.0f}px — the answer above it is read at 617.12px and "
                    "this is the edge that was derived from it"
                )
            else:
                # At 390 the cap is not what binds; the phone is. What has to hold is that the
                # box is inside the viewport and still holds a thumb-sized target.
                assert box["right"] <= width + COMPOSER_SLACK_PX, (
                    f"{where}: the composer reaches {box['right'] - width:.2f}px past the "
                    f"{width}px viewport"
                )
                smaller = min(button["width"], button["height"])
                assert smaller + 0.5 >= TAP_TARGET_MINIMUM_PX, (
                    f"{where}: the Ask button is {button['width']:.0f}x{button['height']:.0f}px, "
                    f"{smaller:.0f}px in its smaller dimension against a {TAP_TARGET_MINIMUM_PX}px "
                    "floor — moving a button inside a field is the change that makes shrinking "
                    "it look reasonable, and this is where the two sizes are still distinguishable"
                )
    finally:
        context.close()


#: The pending question, and what it would measure with its cap taken off.
#:
#: Both, in one pass and on the same element, because the second is what stops the first being
#: a number that happens to be true. A cap that binds and a cap that binds nothing look
#: identical from the capped side.
_PENDING_QUESTION = r"""
() => {
  const p = document.querySelector('li[aria-live] p');
  if (!p) return null;
  const had = p.className;
  const capped = p.getBoundingClientRect().width;
  p.className = had.replace(/\s*max-w-\[\d+ch\]/, '');
  const uncapped = p.getBoundingClientRect().width;
  p.className = had;
  return {capped, uncapped, className: had};
}
"""


def test_the_pending_question_is_drawn_at_the_measure_the_answer_will_be(  # type: ignore[no-untyped-def]
    browser, review_url: str
) -> None:
    """A placeholder exists so that nothing jumps, and this one jumped.

    `surfaces.tsx` draws the reader's own question while the agent works, through the class list
    `ConversationExchange` uses for the same string a render later — under a comment that said
    "exactly" and was missing `max-w-[62ch]`. So the question was set at the panel's full width
    for the tens of seconds an ask takes and then snapped to the exchange's measure when the
    answer landed. Its sibling `question-help.tsx` copied the same device and carried the cap,
    which is what made this a divergence rather than a decision.

    Two assertions, and the second is the one that keeps the first honest: the placeholder is
    drawn at the width the real exchange is drawn at, **and** taking the cap off that very
    element moves it — otherwise this passes on a panel that was narrow anyway.

    No model is reached. The one request that would run an agent is intercepted and never
    fulfilled, which is precisely the state being measured; the conversation it would have been
    filed under is answered from here too, so nothing is written to the workspace either.
    """

    context = browser.new_context(**DESKTOP)
    page = context.new_page()
    try:
        page.route(
            re.compile(r"/api/review-conversations$"),
            lambda route: route.fulfill(
                status=201,
                content_type="application/json",
                body=json.dumps(
                    {
                        "id": "conversation-held",
                        "review_id": "review",
                        "question_id": "",
                        "messages": [],
                    }
                ),
            ),
        )
        # Never fulfilled: the surface stays pending, which is the whole subject.
        page.route(re.compile(r"/api/review-conversations/[^/]+/messages$"), lambda route: None)

        page.goto(review_url, wait_until="networkidle")
        _open_ask(page)
        page.evaluate("() => document.fonts.ready")
        page.locator("textarea[aria-label]").first.fill(_A_LONG_QUESTION)
        page.get_by_role("button", name="Ask").click()
        page.locator("li[aria-live] p").first.wait_for(state="visible", timeout=20_000)

        measured = page.evaluate(_PENDING_QUESTION)
        assert measured is not None, "the question is not kept on screen while it is answered"

        # The measure the answer will be read at, which is the exchange's own and is stated in
        # `conversation-thread.tsx`: 62ch at 14px is 577.22px.
        assert abs(measured["capped"] - 577.22) <= COMPOSER_SLACK_PX, (
            f"the pending question is drawn at {measured['capped']:.2f}px rather than the "
            f"577.22px the exchange replacing it is drawn at: {measured['className']}"
        )
        # And the cap is what is holding it there. Without this the line above passes on any
        # panel narrower than 62ch, including one somebody has just broken.
        assert measured["uncapped"] > measured["capped"] + 100, (
            f"taking the measure off this paragraph moves it from {measured['capped']:.2f}px to "
            f"{measured['uncapped']:.2f}px, which is not far enough for the cap to be the thing "
            "holding it — this check would pass with no cap at all"
        )
    finally:
        context.close()
