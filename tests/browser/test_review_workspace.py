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
            page.goto(f"{workspace_url}/reviews", wait_until="networkidle")

            # 1. The bundled examples are offered, and the scored one is marked.
            page.wait_for_selector("text=Task scheduler boundary review", timeout=20_000)
            assert page.locator("text=scored").count() >= 1

            # 2. Running one indexes its repository, creates the case and reviews it.
            page.get_by_role("button", name="Review this").first.click()
            page.wait_for_url("**/reviews/rev_*", timeout=120_000)
            page.wait_for_selector("text=boundaries examined", timeout=60_000)

            # 3. Every boundary is on the page, cleared ones included. A report that
            #    listed only problems would look identical whether the advisor examined
            #    six boundaries or none.
            references = page.locator(".finding__ref")
            assert references.count() == 6, page.content()[:2000]
            assert page.locator(".finding").count() == 6

            # 4. Detection limits are stated on each boundary, not once in a footer.
            assert page.locator(".finding__limits").count() == 6

            # 5. The example ships answers, so the run is graded rather than only read.
            #    Six rows, every one accounted for — a page that silently scored fewer
            #    would read as a complete result while measuring less than it claims.
            page.wait_for_selector(".scorebar", timeout=20_000)
            assert page.locator(".scorebar__rows li").count() == 6
            assert "Not scored" not in page.content()

            # 6. A follow-up question is answered and its grounding shown.
            page.get_by_label("Question about this review").fill(
                "Why was the TaskFormatter boundary judged the way it was?"
            )
            page.get_by_role("button", name="Ask").click()
            page.wait_for_selector(".dock__a", timeout=60_000)
            grounding = page.locator(".dock__grounding").first.inner_text()
            assert "BR-" in grounding, grounding

            # 7. The atlas visualisation reads the same indexed repository.
            page.goto(f"{workspace_url}/repositories", wait_until="networkidle")
            page.wait_for_selector("text=boundary-review", timeout=20_000)
        finally:
            browser.close()
