"""What a browser downloads before it can paint, weighed in the browser that downloads it.

**The question this answers.** Six of the eight routes are ordinary static imports —
`frontend/src/App.tsx` carries the argument — so one screen importing one component can drag
a dependency the size of the Atlas layout engine into the chunk that every first load parses.
Nothing in a review of `import { X } from "./y"` shows that, and nothing in the source shows
whether rollup left a dependency eager or deferred.

**Why this is a measurement and not a walk over the build.** The guard that shipped with the
route change walked the *static* import graph out of `index.html` and weighed what it reached.
That is a different quantity from the one in the question, and the gap is not small: it put a
cold `/` at 528,204 bytes where a browser downloads 766,070, and it asserted the syntax
highlighter was unreachable while `highlight-*.js` was fetched on every cold load of `/`.

The cause is the approach rather than a bug in it. `LandingPage` mounts `CaseFileDocket`
through `lazy()` on its first render, so that boundary defers nothing — the chunk is fetched
in a second round trip on the same load — and no static walk can tell it from a boundary
behind a tab nobody opens, because the difference is whether the component renders, not how it
was imported. The recipe that shows it, which builds and runs as written: put these two lines
at the top of `frontend/src/features/landing/exhibit.tsx`, above its own imports —

    import ELK from "elkjs/lib/elk.bundled.js";
    if (typeof ELK !== "function") throw new Error("elk");

— and `make frontend-build` succeeds with the entry chunk at 528,288 bytes, which is the
whole of what that walk weighed, while Chromium downloads 2,207,514 for the same page. (The
second line is not decoration. `tsc -b` runs before `vite build` under `npm run build` with
`noUnusedLocals`, so the import alone is `error TS6133: 'ELK' is declared but its value is
never read` and the build exits 2 before a byte is emitted; a recipe that does not compile
demonstrates nothing. Any use of the binding does, and a throw is one rollup cannot drop as
having no effect.)

A browser has already done the walking, and it does not care how an edge was spelled. So this
loads the pages the rest of this directory already drives a browser to, sums
`len(response.body())` over every response each one receives, and asserts on that. It needs no
reasoning about rollup's absorption or about dynamic-versus-static edges, and no import trick
can walk past it.

**Every response, not every script.** This weighed only responses whose path ended `.js`,
which made the noun in "first-load ceiling" false: on a clean build it was blind to 133,657 of
the 766,070 bytes a cold `/` downloads — the 77,030-byte stylesheet, three woff2 faces
totalling 52,428, and the 4,199-byte document. Weight moved into any of those was weight the
ceiling could not see, and the extension was not even the build's to keep: pointing
`build.rollupOptions.output.entryFileNames` and `chunkFileNames` at `.mjs` renamed every
emitted chunk, which under the old definition summed to 0 bytes on a page that downloads
766,086 — the ceiling and both boot checks passing on nothing at all. Weighing the response
rather than its filename closes all four channels at once, needs no list of extensions to keep
current, and made that build measure 766,086 with all nine checks still true. It also
means the API payloads a route fetches to paint are part of its budget, which is the honest
reading of "before it can paint" and is why the two workbench ceilings below are the size they
are.

**What "a cold load" means here.** A context that has fetched nothing, so the HTTP cache is
empty, and `wait_until="networkidle"` — five hundred milliseconds with no request in flight.
That is what makes the second round trip part of the measurement rather than something it
races: a chunk a rendering component asks for is requested while the network is still busy
with the entry chunk, and a 1.4 MB chunk that is downloading is a request in flight.

**What this cannot see, measured rather than apologised for.** A budget test bounds accidents,
not an adversary, and three ways past it were measured on this build rather than imagined:

* **Weight that arrives after the load settles.** `setTimeout(() => import(…), 700)` in a
  module the landing page loads pulled 1,441,210 bytes that no figure here counted: `/` still
  weighed 766,395 at `networkidle`, the kernel arrived after it, and all nine checks passed. At
  3,000 ms the same, at 766,563. A `scroll` listener is past it for a different reason and by a
  wider margin — in that same build a chunk imported from one never arrived at all, because
  nothing in this file scrolls anything.
* **Weight behind a media query this suite never opens.** Every context here is `DESKTOP`,
  1440 by 960, in the default colour scheme. Imports gated on
  `matchMedia("(prefers-color-scheme: dark)")` and on `(max-width: 640px)` left `/` at 766,564
  here and at 2,207,774 in a dark context and in a 390-wide one — the same 1,441,210 bytes,
  paid by the reader and by nobody in this file, with all nine checks green.
* **Weight nobody thought to name.** The ceilings are a backstop for that, and they are the
  reason the fingerprint checks are not the whole guard.

What it *does* see, and what the widening above bought: bytes inlined into `index.html` are
weighed, because the document is a response like any other; a stylesheet or a font is weighed;
and a chunk renamed out of `.js` is weighed. What it will not do is bound the first two cases
in this list, and a docstring implying otherwise would be worse than the gap.
"""

from __future__ import annotations

import time
from collections.abc import Iterator
from contextlib import contextmanager
from urllib.parse import urlsplit

import pytest
from playwright.sync_api import Page, Response
from playwright.sync_api import TimeoutError as PlaywrightTimeout

from tests.browser.harness import DESKTOP, wait_for_review

pytestmark = pytest.mark.browser

#: The most a cold `/` may download, in bytes, and where the number comes from.
#:
#: A cold `/` measures 766,070 bytes on this build: the 4,199-byte document, the entry chunk
#: at 528,204, the three chunks the landing page's own `lazy()` boundary pulls behind it in a
#: second round trip — `exhibit` at 15,713, `finding-detail` at 29,618 and the syntax
#: highlighter at 58,878, which `finding-detail` reaches through the evidence excerpt it draws
#: — the 77,030-byte stylesheet and three woff2 faces at 52,428. It fetches no API. (Summed by
#: this module's own `weighed()` against a Chromium load of `/`; the chunk figures also match
#: `vite build`'s report and `stat` on `presentation/web/static/assets`.)
#:
#: 850,000 is 83,930 bytes of headroom, about eleven percent, for ordinary growth. It also
#: sits 78,200 bytes below 928,200 — a cold `/` plus the Markdown renderer, at 162,130 bytes
#: the *smallest* of the chunks that have to stay off this page. So any of them arriving trips
#: this whatever it is called and however it was imported: the review page is 193,380 bytes
#: and the Atlas kernel is 1,433,538. Raising the ceiling is then a decision somebody makes in
#: a diff, which is the point of having one.
COLD_LANDING_CEILING = 850_000

#: The most `/policies` may download, and why it is larger than `/`'s.
#:
#: `/policies` is one of the two remaining `lazy()` routes, so its budget is necessarily
#: bigger: it legitimately carries everything `/` does except the landing page's own two
#: chunks, plus `policies-page` at 20,293 and the Markdown renderer at 162,130 — which is the
#: whole reason the route is deferred — and 238,176 bytes of `/api/policies`, the corpus it
#: draws. That is 1,142,723 measured, and 1,300,000 is 157,277 bytes of headroom.
#:
#: It is a plain URL somebody can be linked to and nothing here weighed it at all. One static
#: import of the Atlas kernel into `policies-page.tsx` took it to 2,583,172 bytes with every
#: check in this file green; the same mutation now fails by 1,283,172. The ceiling also sits
#: 36,103 bytes below what the review page arriving would make it (1,336,103).
#:
#: The corpus payload is part of the number and is the part that can move without a frontend
#: change: it is the policy pack in this repository, read by a workspace this suite builds
#: from `examples/cases/boundary-review`, so it changes in a diff like everything else here.
POLICIES_CEILING = 1_300_000

#: The most a cold review page may download. The workbench's main screen, and the other
#: `lazy()` route, so this budget is larger than `/`'s for the same reason.
#:
#: Measured at 995,248: the document, the entry chunk, `review-page` at 193,380,
#: `finding-detail` at 29,618, the highlighter at 58,878, stylesheet and faces, and 51,511
#: bytes of API — chiefly the review itself at 50,308. 1,100,000 is 104,752 bytes of headroom,
#: about ten percent, and sits 57,378 below 1,157,378, which is this page plus the Markdown
#: renderer.
#:
#: This route was weighed by nothing either: 900,000 bytes of dead weight imported statically
#: by `review-page.tsx` passed every check in this file. The same file now measures 1,895,323
#: and fails by 795,323.
REVIEW_CEILING = 1_100_000

#: The string that says a response carries the Atlas layout engine, and why not a filename.
#:
#: `org.eclipse.elk.…` is a string literal in elkjs's own emitted code, so a minifier leaves
#: it alone, and it appears in exactly the two chunks that are the kernel: the worker build a
#: browser uses and the bundled build everything without workers falls back to.
#:
#: Matching the chunk's *name* instead would be the same hole from the other side. Rollup
#: absorbs a dynamically imported module into the chunk that needs it eagerly, and the
#: separate `elk-*.js` file then stops existing — so a name list reports elk absent in exactly
#: the case where it has arrived. These are the bytes the browser downloaded; the string is in
#: them or it is not.
ELK = b"org.eclipse.elk"

#: The string that says a response carries the Markdown renderer, on the same argument.
#:
#: `micromarkExtensions` is the key the unified pipeline reads its plugin list under —
#: `t.data("micromarkExtensions")` in remark's emitted code — so it is a string literal a
#: minifier cannot touch, and it survives a version bump of any one package in the stack. It
#: appears in exactly one emitted chunk, `markdown-*.js` at 162,130 bytes, and nowhere else in
#: this repository.
#:
#: It is checked by name because the arithmetic alone is not a guard. Markdown is the smallest
#: thing that must stay off `/`, so today it is kept off by 766,070 + 162,130 exceeding the
#: ceiling — which means raising the ceiling would silently stop protecting it. This is the
#: check that says so out loud, and it is the one thing `frontend/entry-graph.test.ts` asserted
#: that had no replacement when it was deleted: its Markdown reach check and the two vacuity
#: checks under it.
MARKDOWN = b"micromarkExtensions"

#: How long to wait for something a click puts on the screen, or for the chunk it fetches.
#:
#: Not `REVIEW_TIMEOUT_MS`, which is 180,000 because it is sized for a whole deterministic
#: review of a repository. Waiting that long for an attribute that appears in about 130 ms is
#: what turned a rename of `data-atlas-node-id` — a redesign this suite's own comments say to
#: expect — into a 186.88-second run ending in a bare `TimeoutError` with none of the message
#: anybody had written. Fifteen seconds is a hundred times the measured time to draw and still
#: fails inside a minute with a sentence that names the cause.
DRAW_TIMEOUT_MS = 15_000


class Downloaded:
    """Every response one page received, whatever it was made of.

    Collected from the `response` event rather than read back off the page afterwards,
    because the question is what the browser *fetched*. A chunk that was fetched and then
    thrown away by a failed import still cost the load, and a module graph read after the
    fact would not mention it.
    """

    def __init__(self) -> None:
        self.responses: list[Response] = []

    def collect(self, response: Response) -> None:
        """The `response` listener, as a bound method rather than a lambda over the list.

        This used to be `lambda response: downloaded.responses.append(response)`, beside a
        comment saying Playwright's sync wrapper sets an attribute on the handler it is given
        and a bound method does not accept one. Half true, and the false half is the half the
        comment was about. `_impl_to_api_mapping.wrap_handler` branches on
        `inspect.ismethod(handler)` and stashes the wrapper on `handler.__self__`, so a bound
        method is exactly what it does accept. What raises is a *builtin* method —
        `list.append` is `builtin_function_or_method`, `ismethod` is False for it, and the
        `setattr` then lands on the function object: `AttributeError: … has no attribute
        '_pw_impl_instance_'`, measured. The lambda worked; the reason beside it did not.
        """

        self.responses.append(response)

    def weighed(self) -> list[tuple[str, bytes]]:
        """Each successful response, as its path and its body.

        No test on the extension, which is the whole point: a stylesheet, a font, an API
        payload, the document itself and a chunk somebody renamed to `.mjs` are all weight the
        browser paid for. Worker scripts are included by the same silence —
        `elk-worker.min-*.js` is fetched by a `new Worker(…)` and is 1,433,538 of the
        1,438,649 bytes the Atlas costs, so a definition that excluded it would exclude the
        whole subject.

        Only successful responses. A 404 for a chunk that is gone answers with a body of JSON
        — `spa` in `presentation/web/app.py` — and weighing that would be weighing the error
        rather than the page.

        The bodies are read while the browser context is still open. Playwright discards a
        response body when its context closes, so every caller here does its arithmetic inside
        `cold_page` below.
        """

        found: list[tuple[str, bytes]] = []
        for response in self.responses:
            if response.status != 200:
                continue
            found.append((urlsplit(response.url).path, response.body()))
        return found

    def total(self) -> int:
        return sum(len(body) for _, body in self.weighed())

    def carrying(self, fingerprint: bytes) -> list[tuple[str, int]]:
        """The responses whose bytes contain a string, and how big each one is."""

        return [(path, len(body)) for path, body in self.weighed() if fingerprint in body]

    def settle(self, fingerprint: bytes, page: Page, timeout_ms: int) -> list[tuple[str, int]]:
        """Wait, briefly, for a response carrying `fingerprint`, and answer with what arrived.

        A wait and not an assertion: an empty answer is the caller's to fail on, with the
        caller's sentence. What it removes is a race that made the positive check below pass
        by luck. `page.wait_for_load_state("networkidle")` is a no-op once a page has already
        settled — it reports a lifecycle the initial `goto` reached, not the quiet of the
        network now — and the Atlas kernel is fetched by a `new Worker(…)`, which no load
        lifecycle covers at all. Measured over three runs the first node attached 1 to 5 ms
        before the 1,433,538-byte worker script's response event arrived, so the old check read
        a list that was still being appended to.
        """

        deadline = time.monotonic() + timeout_ms / 1000
        while True:
            arrived = self.carrying(fingerprint)
            if arrived or time.monotonic() > deadline:
                return arrived
            page.wait_for_timeout(50)

    def itemised(self) -> str:
        """The breakdown, for a failure message. A total alone names nothing to go and look at."""

        return ", ".join(f"{path} {len(body):,} B" for path, body in self.weighed())


@contextmanager
def cold_page(browser) -> Iterator[tuple[Page, Downloaded]]:  # type: ignore[no-untyped-def]
    """A page in a context that has fetched nothing, and a record of everything it fetches.

    A fresh context per measurement is what makes the load cold: Chromium's HTTP cache is per
    context, and the assets are served `immutable` for a year (`_static_cache_headers` in
    `presentation/web/app.py`), so a second load in the same context would download nothing at
    all and measure zero.

    It hands back a page that has not navigated, rather than navigating itself, so the caller
    can arrive the way the rest of this directory arrives — `wait_for_review` for a review.
    The listener has to be attached before that navigation: the entry chunk is requested by
    the document, and there is no later point at which to ask for it.
    """

    context = browser.new_context(**DESKTOP)
    page = context.new_page()
    downloaded = Downloaded()
    page.on("response", downloaded.collect)
    try:
        yield page, downloaded
    finally:
        context.close()


def test_a_cold_landing_page_stays_under_its_ceiling(browser, workspace_url: str) -> None:  # type: ignore[no-untyped-def]
    """`/` is the one route guaranteed to be somebody's first, and the heaviest static one.

    The five routes in the entry chunk that are reachable by URL alone — `/reviews`,
    `/repositories`, `/cases`, `/settings`, `/start` — draw no deferred component, so each
    downloads the entry chunk and nothing else beside its own API. `/` draws one, so it is the
    biggest first load outside the two `lazy()` routes and the only one where a second round
    trip can carry something in unnoticed. Holding this route holds the rest of the entry
    chunk with it.
    """

    with cold_page(browser) as (page, downloaded):
        page.goto(f"{workspace_url}/", wait_until="networkidle")
        total = downloaded.total()
        assert total < COLD_LANDING_CEILING, (
            f"a cold `/` now downloads {total:,} bytes, over the "
            f"{COLD_LANDING_CEILING:,} ceiling: {downloaded.itemised()}"
        )


def test_the_policies_page_stays_under_its_ceiling(browser, workspace_url: str) -> None:  # type: ignore[no-untyped-def]
    """The first of the two deferred routes, weighed because a URL is a URL.

    Nothing about `/policies` being behind `lazy()` stops somebody being linked to it, and
    what it defers is the Markdown renderer — the largest thing in the product after the
    Atlas. A budget on `/` alone says nothing about the page that legitimately holds it.
    """

    with cold_page(browser) as (page, downloaded):
        page.goto(f"{workspace_url}/policies", wait_until="networkidle")
        total = downloaded.total()
        assert total < POLICIES_CEILING, (
            f"a cold `/policies` now downloads {total:,} bytes, over the "
            f"{POLICIES_CEILING:,} ceiling: {downloaded.itemised()}"
        )


def test_a_cold_review_page_stays_under_its_ceiling(browser, review_url: str) -> None:  # type: ignore[no-untyped-def]
    """The other deferred route, and the screen the workbench is for.

    It is the page a reader is sent a link to more often than any other, and the one whose
    chunk everything about a finding hangs off. Weighed at rest: the Atlas is a tab on this
    page and its kernel is not part of this number, which is the claim the two checks below
    are about.
    """

    with cold_page(browser) as (page, downloaded):
        wait_for_review(page, review_url)
        total = downloaded.total()
        assert total < REVIEW_CEILING, (
            f"a cold review page now downloads {total:,} bytes, over the "
            f"{REVIEW_CEILING:,} ceiling: {downloaded.itemised()}"
        )


@pytest.mark.parametrize("route", ["/", "/reviews"])
def test_the_atlas_layout_engine_does_not_arrive_at_boot(  # type: ignore[no-untyped-def]
    browser, workspace_url: str, route: str
) -> None:
    """The largest dependency in the product, on the two routes that must not pay for it.

    `/` is the landing page and `/reviews` is the workbench's own front door; neither draws a
    map. Both measure zero bytes of kernel today.

    **What this catches that the ceiling does not.** A ceiling is one number about a total,
    and it cannot tell a dependency that is *deferred* from one that has been deleted — a
    broken Atlas would take a cold `/` further under the ceiling, not over it. Paired with the
    positive check below, this is a claim about deferral: the kernel is in the build, it does
    arrive when a map is drawn, and it does not arrive before one is. The ceilings stay as the
    backstop for whatever arrives without a name anybody thought to check.
    """

    with cold_page(browser) as (page, downloaded):
        page.goto(f"{workspace_url}{route}", wait_until="networkidle")
        arrived = downloaded.carrying(ELK)
        assert arrived == [], (
            f"loading {route} now downloads the Atlas layout engine — {arrived} — so a "
            f"component this route renders reaches it. Everything fetched: "
            f"{downloaded.itemised()}"
        )


def test_the_atlas_layout_engine_arrives_when_the_atlas_is_opened(  # type: ignore[no-untyped-def]
    browser, review_url: str
) -> None:
    """The positive half, without which the two checks above pass by the Atlas being broken.

    It is also what keeps `ELK` honest. A fingerprint that matches nothing anywhere asserts
    nothing — it would happen on an upgrade past the string, or on a swap to another layout
    engine — and the check for it would go on passing, silently, about a library that is no
    longer there.

    Measured on this build: the review page boots on 995,248 bytes and opening the tab adds
    1,438,649 of Atlas machinery, of which the 1,433,538 of `elk-worker.min-*.js`, fetched by
    a `new Worker(…)`, carry the string. The canvas draws 21 nodes about 130 ms after the
    click.

    The wait for a node is the assertion that the tab drew one; there is no count under it,
    because 21 is a property of the example repository under `examples/cases/boundary-review`,
    which this suite is entitled to change, while "the canvas put a node on the screen" is the
    claim being made. `[data-atlas-node-id]` is the identity `atlas/canvas.tsx` writes onto
    each node group — the graph's own node id — so it survives a redesign of everything
    visible about a node, and when that identity does change this fails in fifteen seconds
    saying which of the two things went.
    """

    with cold_page(browser) as (page, downloaded):
        wait_for_review(page, review_url)
        assert downloaded.carrying(ELK) == [], (
            "the review page reached the Atlas layout engine before its tab was opened"
        )

        page.get_by_role("tab", name="Atlas").click()
        nodes = page.locator("[data-atlas-node-id]")
        try:
            nodes.first.wait_for(state="attached", timeout=DRAW_TIMEOUT_MS)
        except PlaywrightTimeout as timed_out:
            raise AssertionError(
                f"the Atlas tab drew no `[data-atlas-node-id]` in {DRAW_TIMEOUT_MS:,} ms, so "
                "either the canvas did not draw or that attribute has been renamed and this "
                f"check has to follow it. Everything fetched: {downloaded.itemised()}"
            ) from timed_out

        arrived = downloaded.settle(ELK, page, DRAW_TIMEOUT_MS)
        assert arrived != [], (
            "the Atlas drew a map without downloading anything containing "
            f"`{ELK.decode()}`, so the check that it stays off the first load is vacuous. "
            f"Everything fetched: {downloaded.itemised()}"
        )


@pytest.mark.parametrize("route", ["/", "/reviews"])
def test_the_markdown_renderer_does_not_arrive_at_boot(  # type: ignore[no-untyped-def]
    browser, workspace_url: str, route: str
) -> None:
    """The second-largest dependency, on the two routes that must not pay for it either.

    This is the check the arithmetic was standing in for. 162,130 bytes is small enough that a
    cold `/` carrying it — 928,200 — is only 78,200 over the ceiling, so the ceiling protects
    it by a margin that a later, perfectly reasonable decision to raise the ceiling would
    remove without anybody noticing what else had gone. Named, it goes when somebody deletes
    this, which is a different kind of act.
    """

    with cold_page(browser) as (page, downloaded):
        page.goto(f"{workspace_url}{route}", wait_until="networkidle")
        arrived = downloaded.carrying(MARKDOWN)
        assert arrived == [], (
            f"loading {route} now downloads the Markdown renderer — {arrived} — so a "
            f"component this route renders reaches it. Everything fetched: "
            f"{downloaded.itemised()}"
        )


def test_the_markdown_renderer_arrives_when_a_policy_is_rendered(  # type: ignore[no-untyped-def]
    browser, workspace_url: str
) -> None:
    """The positive half, on the same argument as the Atlas one: a fingerprint that matches
    nothing asserts nothing, and `MARKDOWN` would keep passing about a renderer that had been
    swapped out from under it.

    A policy body is the one place in the product that renders authored Markdown, and it
    renders on demand: the row is a disclosure, and `policies-page.tsx` draws `<Markdown>`
    only for the expanded one. So this opens one and waits for the region the row's own
    `aria-controls` names — the relation the page declares between a control and what it
    controls, which is what makes this survive a redesign of the row.
    """

    with cold_page(browser) as (page, downloaded):
        page.goto(f"{workspace_url}/policies", wait_until="networkidle")
        disclosure = page.locator("h3 button[aria-expanded]").first
        disclosure.wait_for(state="visible", timeout=DRAW_TIMEOUT_MS)
        # The relation and not the attribute's presence in the selector, so that a row which
        # stops naming what it expands fails here with a sentence instead of matching nothing
        # and timing out on a locator.
        body = disclosure.get_attribute("aria-controls")
        assert body, (
            "a policy row no longer names the region it expands, so there is no way from the "
            "control to the body it draws"
        )
        disclosure.click()
        try:
            page.locator(f"#{body}").wait_for(state="visible", timeout=DRAW_TIMEOUT_MS)
        except PlaywrightTimeout as timed_out:
            raise AssertionError(
                f"expanding a policy drew nothing at `#{body}` in {DRAW_TIMEOUT_MS:,} ms, so "
                "this check cannot say a policy body was rendered at all"
            ) from timed_out

        arrived = downloaded.settle(MARKDOWN, page, DRAW_TIMEOUT_MS)
        assert arrived != [], (
            "a policy body rendered without anything downloaded containing "
            f"`{MARKDOWN.decode()}`, so the check that the Markdown renderer stays off the "
            f"first load is vacuous. Everything fetched: {downloaded.itemised()}"
        )
