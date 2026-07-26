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

from archcompass.bootstrap import build_runtime
from archcompass.presentation.web import create_app

pytestmark = pytest.mark.browser

FAKE_CONFIG = """models:
  reasoning:
    provider: fake
    model: deterministic-architecture-v1
    base_url: http://127.0.0.1:11434
    timeout_seconds: 5
    context_window_tokens: 131072
    max_output_tokens: 8192
  embedding:
    provider: fake
    model: deterministic-token-hash-v1
    base_url: http://127.0.0.1:11434
    dimensions: 64
    timeout_seconds: 5
retrieval:
  top_k: 6
  max_sections_per_policy: 3
"""


def _free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1])


@pytest.fixture(scope="module")
def workspace_url(tmp_path_factory: pytest.TempPathFactory) -> Iterator[str]:
    workspace = tmp_path_factory.mktemp("browser-workspace")
    config = workspace / "config" / "models.yaml"
    config.parent.mkdir(parents=True)
    config.write_text(FAKE_CONFIG, encoding="utf-8")
    app = create_app(build_runtime(workspace))
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
            page.goto(workspace_url, wait_until="networkidle")

            # 1. The bundled examples are offered on the front door, scored one marked.
            page.wait_for_selector("text=Task scheduler boundary review", timeout=20_000)
            assert page.locator("text=scored").count() >= 1

            # 2. Nothing can run yet: the flow states what is missing rather than
            #    offering a button that fails.
            run = page.get_by_role("button", name="Run the review")
            assert run.is_disabled()

            # 3. One example click fills both rails — its repository is indexed and its
            #    case created — and then the run is the user's to start.
            page.get_by_role("button", name="Task scheduler boundary review").click()
            page.wait_for_selector(".rail--filled", timeout=60_000)
            assert page.locator(".rail--filled").count() == 2
            run.click()
            page.wait_for_url("**/reviews/rev_*", timeout=120_000)
            # Wait on something only the review page renders. The router changes the URL
            # before React commits the new page, and "boundaries examined" also appears on
            # the past-reviews card behind it — waiting for that would pass on the old DOM.
            page.wait_for_selector(".review-head", timeout=60_000)

            # 4. The page leads with what the verdicts amount to, and every claim in it
            #    names the boundaries it rests on.
            overview = page.locator(".overview")
            assert overview.count() == 1
            assert overview.locator(".overview__lead").inner_text().strip()
            assert overview.locator(".overview__limits").inner_text().strip()
            citations = overview.locator(".cite")
            assert citations.count() >= 1, overview.inner_text()

            # 5. A citation is a link into the evidence: clicking one lands on that
            #    boundary, which is the whole reason the overview is allowed to generalise.
            cited = citations.first.inner_text().strip()
            citations.first.click()
            page.wait_for_selector(f"#{cited}:target", timeout=10_000)

            # 6. Every boundary is on the page, cleared ones included. A report that
            #    listed only problems would look identical whether the advisor examined
            #    six boundaries or none.
            references = page.locator(".finding__ref")
            assert references.count() == 6, page.content()[:2000]
            assert page.locator(".finding").count() == 6
            # The verdict is a word, not only a colour.
            assert page.locator(".verdict").count() == 6

            # 7. Detection limits are stated on each boundary, not once in a footer.
            assert page.locator(".finding__limits").count() == 6

            # 8. The example ships answers, so the run is graded rather than only read.
            #    Six rows, every one accounted for — a page that silently scored fewer
            #    would read as a complete result while measuring less than it claims.
            page.wait_for_selector(".scorebar", timeout=20_000)
            assert page.locator(".scorebar__rows li").count() == 6
            assert "Not scored" not in page.content()

            # 9. A follow-up question is answered and its grounding shown.
            page.get_by_label("Question about this review").fill(
                "Why was the TaskFormatter boundary judged the way it was?"
            )
            page.get_by_role("button", name="Ask", exact=True).click()
            page.wait_for_selector(".dock__a", timeout=60_000)
            grounding = page.locator(".dock__grounding").first.inner_text()
            assert "BR-" in grounding, grounding

            # 10. Threads are durable and plural: a second one is kept apart from the
            #     first, and both stay reachable.
            page.get_by_role("button", name="New thread").click()
            page.get_by_label("Question about this review").fill("What should I do first?")
            page.get_by_role("button", name="Ask", exact=True).click()
            page.wait_for_selector(".dock__a", timeout=60_000)
            threads = page.locator(".dock__threads button")
            # Two threads plus the "new thread" control.
            assert threads.count() == 3, threads.all_inner_texts()
            assert page.locator(".dock__history li").count() == 1
            page.locator(".dock__threads button").first.click()
            page.wait_for_selector(".dock__history li", timeout=10_000)
            assert "TaskFormatter" in page.locator(".dock__history").inner_text()

            # 11. A finding opens the atlas on the boundary it is about, which is the
            #     explorer's way back in: entered from the question rather than as a map.
            atlas = page.get_by_role("link", name="Show BR-001 in the atlas")
            assert atlas.count() == 1
            atlas.click()
            page.wait_for_url("**/repositories?root=*node=*", timeout=20_000)
            page.wait_for_selector(".atlas-node--selected, .atlas-canvas", timeout=30_000)
            page.go_back()
            page.wait_for_selector(".review-head", timeout=20_000)

            # 12. The review is listed on the front door and reopens from there.
            page.goto(workspace_url, wait_until="networkidle")
            page.wait_for_selector("text=boundaries examined", timeout=20_000)

            # 13. The atlas explorer is no longer a navigation peer: it is entered from
            #     the repository rail, on the repository the flow is pointed at.
            assert page.get_by_role("link", name="Policies").count() == 1
            assert page.get_by_role("link", name="Repositories").count() == 0
            page.get_by_role("link", name="Explore this atlas").click()
            page.wait_for_url("**/repositories?root=*", timeout=20_000)
            page.wait_for_selector("text=boundary-review", timeout=20_000)

            # 14. Old paths do not 404; they land on the flow.
            for stale in ("/reviews", "/cases"):
                page.goto(f"{workspace_url}{stale}", wait_until="networkidle")
                page.wait_for_selector("text=Start a review", timeout=20_000)
        finally:
            browser.close()


def test_a_person_can_write_a_case_in_the_browser_and_review_with_it(
    workspace_url: str,
) -> None:
    """The second rail, without a CLI detour.

    Runs after the example test in file order and depends on the repository that test
    indexed — deliberately, because the point being proved is that only the case is
    authored here: the same repository, a different case, a different review.
    """

    playwright = pytest.importorskip("playwright.sync_api")

    with playwright.sync_playwright() as driver:
        browser = driver.chromium.launch()
        page = browser.new_page(viewport={"width": 1280, "height": 900})
        try:
            page.goto(workspace_url, wait_until="networkidle")
            page.wait_for_selector(".rail", timeout=20_000)

            # 1. The form asks questions rather than presenting a schema, and marks the
            #    three fields that decide verdicts as the ones that do.
            page.get_by_role("button", name="New case").click()
            page.wait_for_selector(".case-form", timeout=20_000)
            assert page.locator(".case-form__group--decisive").count() == 1
            page.get_by_label("Name for this case").fill(
                "Formatter boundary, authored in the browser"
            )
            page.get_by_label("What decision are you facing?").fill(
                "One formatter port with a single implementation, and a label format fixed "
                "by a downstream reporting system that parses it."
            )
            page.get_by_label("What would a good answer give you?").fill(
                "A verdict on whether the formatter boundary is earning its place."
            )
            page.get_by_label("What changes are actually coming?").fill(
                "Reminder delivery over SMS is scheduled for the next release."
            )
            page.get_by_label("What have you decided against?").fill(
                "Any alternative label format or output rendering."
            )
            page.get_by_label("What is settled, and why?").fill(
                "The label format is fixed by a downstream parser and no change is planned."
            )

            # 2. The case is created, selected in the rail, and ready to run.
            page.get_by_role("button", name="Create the case").click()
            page.wait_for_selector(
                "text=Formatter boundary, authored in the browser", timeout=20_000
            )
            assert page.locator(".rail--filled").count() == 2

            # 3. The YAML escape hatch is still there, and the server is still the only
            #    validator: its complaint is shown rather than paraphrased.
            page.get_by_role("button", name="Paste YAML").click()
            page.get_by_label("Case YAML").fill("title: Missing everything else\n")
            page.get_by_role("button", name="Create the case").click()
            page.wait_for_selector(".notice--error", timeout=20_000)
            assert "problem_statement" in page.locator(".notice--error").inner_text()
            page.get_by_role("button", name="Close the editor").click()

            # 4. The stored case reads back as the same format the escape hatch takes.
            page.get_by_role("button", name="View", exact=True).click()
            page.wait_for_selector(".case-editor__source--read", timeout=20_000)
            written = page.locator(".case-editor__source--read").inner_text()
            assert "expected_future_changes" in written
            assert "case_id" not in written, written
            page.get_by_role("button", name="Close the case").click()

            # 5. The whole flow, completed in the browser: authored case, indexed
            #    repository, one review.
            page.get_by_role("button", name="Run the review").click()
            page.wait_for_url("**/reviews/rev_*", timeout=120_000)
            page.wait_for_selector(".review-head", timeout=60_000)
            assert "Formatter boundary, authored in the browser" in page.inner_text(
                ".review-head"
            )
            assert page.locator(".finding").count() == 6
        finally:
            browser.close()


def test_a_person_can_revise_the_case_and_review_again(workspace_url: str) -> None:
    """The iterate loop: a changed case is a new question, not a corrected answer.

    Depends on the reviews the tests above produced, which is the point: what is proved
    here is that a second review of the same case exists alongside the first and that the
    two can be walked between.
    """

    playwright = pytest.importorskip("playwright.sync_api")

    with playwright.sync_playwright() as driver:
        browser = driver.chromium.launch()
        page = browser.new_page(viewport={"width": 1280, "height": 900})
        try:
            page.goto(workspace_url, wait_until="networkidle")
            page.wait_for_selector(".card-list .card", timeout=20_000)
            page.get_by_role("link", name="Open").first.click()
            page.wait_for_selector(".review-head", timeout=20_000)
            first = page.url

            # 1. What the review is pinned to is printed, not implied. The labels are
            #    uppercased by the stylesheet, so compare against rendered text.
            provenance = page.locator(".provenance").inner_text().lower()
            assert "case revision" in provenance
            assert "atlas version" in provenance
            assert "policies presented" in provenance
            assert "rev 1" in provenance

            # 2. The action says what it will do before it is confirmed: a new revision
            #    and a new review, with this one left alone.
            page.get_by_role("button", name="Revise case & review again").click()
            warning = page.locator(".case-editor__warning").inner_text()
            assert "does not change the review you are reading" in warning

            # 3. The pinned case opens prefilled — not empty, and not the latest revision
            #    but the one this review judged — and a real edit is submitted.
            page.wait_for_selector(".case-form", timeout=20_000)
            expected = page.get_by_label("What changes are actually coming?")
            existing = expected.input_value()
            assert existing.strip(), "the form must open with the pinned case's answers"
            expected.fill(existing + "\nA second delivery channel is committed.")
            page.get_by_role("button", name="Create revision & review again").click()

            # 4. A second review, at the next case revision, and this is a different one.
            page.wait_for_url("**/reviews/rev_*", timeout=120_000)
            page.wait_for_function(
                "url => window.location.href !== url", arg=first, timeout=120_000
            )
            page.wait_for_selector(".review-head", timeout=60_000)
            second = page.url
            assert second != first

            # 5. The two are linked, derived from the reviews of this case rather than
            #    stored on either of them.
            page.wait_for_selector(".review-siblings", timeout=20_000)
            assert "reviews of this case" in page.locator(".review-siblings").inner_text()
            page.get_by_role("link", name="Earlier review").click()
            page.wait_for_url(first, timeout=20_000)
            page.wait_for_selector(".review-siblings", timeout=20_000)
            page.get_by_role("link", name="Newer review").click()
            page.wait_for_url(second, timeout=20_000)
        finally:
            browser.close()
