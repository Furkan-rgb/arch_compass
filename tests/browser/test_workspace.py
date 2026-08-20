"""End-to-end: the built workbench, a real browser, and a real workspace server.

Nothing here is stubbed on the browser side. The bundle under `presentation/web/static` is
what is served, the API is the real application, and the review that runs is a real review of
a repository on disk — only the two models are substituted, and neither is reached over the
network:

* reasoning is pinned to the deterministic provider, so verdicts are reproducible;
* embedding is pinned to a local Ollama identity, which is recorded on the retrieval
  provenance but never called, because deterministic mode retrieves the whole corpus.
"""

from __future__ import annotations

import os
import socket
import threading
import time
from collections.abc import Iterator
from pathlib import Path

import pytest
import uvicorn

from archcompass.bootstrap import Runtime, build_runtime, pinned_model
from archcompass.presentation.web import create_app
from archcompass.reasoning.adapters.providers import DETERMINISTIC_MODEL

pytestmark = pytest.mark.browser

REPOSITORY = Path("examples/cases/boundary-review/repository").resolve()
BUNDLE = Path("src/archcompass/presentation/web/static/index.html")

#: Long enough for a full deterministic review of the example repository on a cold workspace.
REVIEW_TIMEOUT_MS = 180_000


def _free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1])


@pytest.fixture(scope="module")
def workspace(tmp_path_factory: pytest.TempPathFactory) -> Iterator[Runtime]:
    # Pinned rather than selected, so the page has both models the moment it loads and the
    # test is about the workbench rather than about clicking through the model chooser.
    before = os.environ.copy()
    os.environ["ARCHCOMPASS_EMBEDDING_PROVIDER"] = "ollama"
    os.environ["ARCHCOMPASS_EMBEDDING_MODEL"] = "nomic-embed-text"
    os.environ["ARCHCOMPASS_EMBEDDING_DIMENSIONS"] = "768"
    try:
        yield build_runtime(
            tmp_path_factory.mktemp("workbench-browser"),
            pin=pinned_model("fake", DETERMINISTIC_MODEL),
        )
    finally:
        os.environ.clear()
        os.environ.update(before)


@pytest.fixture(scope="module")
def workspace_url(workspace: Runtime) -> Iterator[str]:
    port = _free_port()
    server = uvicorn.Server(
        uvicorn.Config(create_app(workspace), host="127.0.0.1", port=port, log_level="warning")
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


@pytest.fixture(scope="module")
def browser():  # type: ignore[no-untyped-def]
    playwright = pytest.importorskip("playwright.sync_api")
    assert BUNDLE.is_file(), "run `make frontend-build` before the browser test"
    with playwright.sync_playwright() as driver:
        instance = driver.chromium.launch()
        try:
            yield instance
        finally:
            instance.close()


@pytest.fixture
def page(browser, workspace_url: str):  # type: ignore[no-untyped-def]
    context = browser.new_context(viewport={"width": 1440, "height": 960})
    opened = context.new_page()
    try:
        yield opened
    finally:
        context.close()


@pytest.fixture(scope="module")
def review_url(browser, workspace_url: str) -> str:  # type: ignore[no-untyped-def]
    """One real review, run once, and its address.

    A deterministic review of the example repository still parses it, detects candidates and
    composes a review, which is the slowest thing in this file — so it happens once and the
    tests that read it navigate to the result.
    """

    context = browser.new_context(viewport={"width": 1440, "height": 960})
    opened = context.new_page()
    try:
        opened.goto(f"{workspace_url}/start", wait_until="networkidle")
        opened.get_by_role("tab", name="Browse").click()
        opened.get_by_label("Repository path").fill(str(REPOSITORY))
        run = opened.get_by_role("button", name="Run review")
        run.wait_for(state="visible")
        run.click()
        # Starting a review hands it to the workspace and moves to the run, which is what
        # makes the page reloadable; the run redirects to the review once there is one.
        opened.wait_for_url("**/runs/**", timeout=30_000)
        run_url = opened.url
        # The proof that the fix is a fix: a reload lands back on the same run rather than
        # on a page that has forgotten it, and the review is still being produced.
        opened.reload(wait_until="networkidle")
        assert opened.url == run_url
        opened.wait_for_url("**/reviews/**", timeout=REVIEW_TIMEOUT_MS)
        return opened.url
    finally:
        context.close()


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
            name="Architecture review grounded in your code, policies, and decisions.",
        )
    )
    # The product's own claim about itself, answered plainly and open by default.
    assert _visible(page.get_by_text("It does not edit code, open branches"))
    page.get_by_role("button", name="Can I use Ollama?").click()
    assert _visible(page.get_by_text("Yes, for both roles").first)

    page.get_by_role("link", name="Review a repository").first.click()
    page.wait_for_url("**/start")
    assert _visible(page.get_by_role("heading", name="Review a repository", level=1))


def test_a_review_produces_a_workbench_with_a_clarification(page, review_url: str) -> None:  # type: ignore[no-untyped-def]
    page.goto(review_url, wait_until="networkidle")

    # The queue is the first thing a reviewer sees, and it opens on what needs a human.
    page.get_by_text("Attention queue").first.wait_for(timeout=REVIEW_TIMEOUT_MS)
    page.get_by_text("The repository cannot answer these").wait_for(timeout=REVIEW_TIMEOUT_MS)
    assert _visible(page.get_by_role("button", name="Save and rejudge"))
    assert _visible(page.get_by_role("button", name="Conclude with remaining uncertainty"))
    assert _visible(page.get_by_text("Review lineage"))

    # A finding reads as an assessment, with its provenance folded away until asked for.
    page.get_by_role("button", name="All", exact=False).click()
    page.get_by_role("list", name="Candidates").get_by_role("button").first.click()
    assert _visible(page.get_by_text("Why this matters"))
    assert _visible(page.get_by_text("Standing decision · human"))
    assert page.get_by_text("judge:deterministic-v1").count() == 0
    page.get_by_role("button", name="Technical detail").click()
    assert _visible(page.get_by_text("judge:deterministic-v1").first)

    # Retrieval is auditable from its own surface, naming the retriever that ran.
    page.get_by_role("tab", name="Retrieval").click()
    page.get_by_text("full-corpus-test-oracle").first.wait_for()

    # Deterministic retrieval takes the whole corpus and embeds nothing, and the provenance
    # says exactly that rather than naming a model it never called.
    assert _visible(page.get_by_text("non-embedding strategy").first)

    # The embedding this workspace would use is still stated in the shell, beside the
    # reasoning model, because they are two independent selections.
    assert _visible(page.get_by_role("link", name="Embedding").first)
    assert "nomic-embed-text" in page.get_by_role("link", name="Embedding").first.inner_text()


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
