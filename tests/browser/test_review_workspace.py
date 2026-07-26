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

            # 4. Every boundary is on the page, cleared ones included. A report that
            #    listed only problems would look identical whether the advisor examined
            #    six boundaries or none.
            references = page.locator(".finding__ref")
            assert references.count() == 6, page.content()[:2000]
            assert page.locator(".finding").count() == 6

            # 5. Detection limits are stated on each boundary, not once in a footer.
            assert page.locator(".finding__limits").count() == 6

            # 6. The example ships answers, so the run is graded rather than only read.
            #    Six rows, every one accounted for — a page that silently scored fewer
            #    would read as a complete result while measuring less than it claims.
            page.wait_for_selector(".scorebar", timeout=20_000)
            assert page.locator(".scorebar__rows li").count() == 6
            assert "Not scored" not in page.content()

            # 7. A follow-up question is answered and its grounding shown.
            page.get_by_label("Question about this review").fill(
                "Why was the TaskFormatter boundary judged the way it was?"
            )
            page.get_by_role("button", name="Ask").click()
            page.wait_for_selector(".dock__a", timeout=60_000)
            grounding = page.locator(".dock__grounding").first.inner_text()
            assert "BR-" in grounding, grounding

            # 8. The review is listed on the front door and reopens from there.
            page.goto(workspace_url, wait_until="networkidle")
            page.wait_for_selector("text=boundaries examined", timeout=20_000)

            # 9. The atlas explorer is no longer a navigation peer: it is entered from the
            #    repository rail, on the repository the flow is pointed at.
            assert page.get_by_role("link", name="Policies").count() == 1
            assert page.get_by_role("link", name="Repositories").count() == 0
            page.get_by_role("link", name="Explore this atlas").click()
            page.wait_for_url("**/repositories?root=*", timeout=20_000)
            page.wait_for_selector("text=boundary-review", timeout=20_000)

            # 10. Old paths do not 404; they land on the flow.
            for stale in ("/reviews", "/cases"):
                page.goto(f"{workspace_url}{stale}", wait_until="networkidle")
                page.wait_for_selector("text=Start a review", timeout=20_000)
        finally:
            browser.close()


AUTHORED_CASE = """title: Formatter boundary, authored in the browser
problem_statement: >-
  One formatter port with a single implementation, and a label format fixed by a
  downstream reporting system that parses it.
desired_outcome: >-
  A verdict on whether the formatter boundary is earning its place.
expected_future_changes:
  - Reminder delivery over SMS is scheduled for the next release.
non_goals:
  - Any alternative label format or output rendering.
confirmed_facts:
  - text: >-
      The label format is fixed by a downstream parser and no change to it is planned.
    kind: fact
"""


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

            # 1. An invalid case is refused by the server, and its complaint is shown
            #    rather than paraphrased. The browser does not carry a second copy of the
            #    domain's rules, so this is the only validation there is.
            page.get_by_role("button", name="Write a new case").click()
            editor = page.get_by_label("Case YAML")
            editor.fill("title: Missing everything else\n")
            page.get_by_role("button", name="Create the case").click()
            page.wait_for_selector(".notice--error", timeout=20_000)
            assert "problem_statement" in page.locator(".notice--error").inner_text()

            # 2. A complete case is created, selected in the rail, and ready to run.
            editor.fill(AUTHORED_CASE)
            page.get_by_role("button", name="Create the case").click()
            page.wait_for_selector(
                "text=Formatter boundary, authored in the browser", timeout=20_000
            )
            assert page.locator(".rail--filled").count() == 2

            # 3. The stored case reads back as the same format it was written in.
            page.get_by_role("button", name="View this case").click()
            page.wait_for_selector(".case-editor__source--read", timeout=20_000)
            written = page.locator(".case-editor__source--read").inner_text()
            assert "expected_future_changes" in written
            assert "case_id" not in written, written
            page.get_by_role("button", name="Close the case").click()

            # 4. The whole flow, completed in the browser: authored case, indexed
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
