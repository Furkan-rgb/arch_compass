"""Real-browser smoke test for the active clean-break frontend and API."""

from __future__ import annotations

import socket
import threading
import time
from collections.abc import Iterator
from pathlib import Path

import pytest
import uvicorn

from archcompass.adapters.models.catalog import DETERMINISTIC_MODEL
from archcompass.bootstrap import Runtime, build_runtime, pinned_model
from archcompass.presentation.web import create_app

pytestmark = pytest.mark.browser


def _free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1])


@pytest.fixture(scope="module")
def workspace(tmp_path_factory: pytest.TempPathFactory) -> Runtime:
    return build_runtime(
        tmp_path_factory.mktemp("clean-break-browser"),
        pin=pinned_model("fake", DETERMINISTIC_MODEL),
    )


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


def test_browser_starts_and_reaches_a_clean_break_review(workspace_url: str) -> None:
    playwright = pytest.importorskip("playwright.sync_api")
    static = Path("src/archcompass/presentation/web/static/index.html")
    assert static.is_file(), "run `make frontend-build` before the browser test"
    repository = Path("eval/cases/boundary-review/repository").resolve()

    with playwright.sync_playwright() as driver:
        browser = driver.chromium.launch()
        page = browser.new_page(viewport={"width": 1280, "height": 900})
        try:
            page.goto(f"{workspace_url}/start", wait_until="networkidle")
            page.get_by_label("Repository path").fill(str(repository))
            page.get_by_role("button", name="Run review").click()
            page.wait_for_url("**/reviews/**", timeout=120_000)
            page.get_by_text("Clarification round 1").wait_for(timeout=120_000)
            assert page.get_by_text("Review lineage").is_visible()
            assert page.get_by_role("tab", name="Findings 6").is_visible()
            assert page.get_by_role("tab", name="Evidence").is_visible()
            page.get_by_role("tab", name="Retrieval 6").click()
            page.get_by_text("full-corpus-test-oracle", exact=False).first.wait_for()
            page.get_by_role("tab", name="Overview").click()
            page.get_by_text("The code cannot answer these").wait_for()
            assert page.get_by_role(
                "button", name="Conclude with remaining uncertainty"
            ).is_visible()
        finally:
            browser.close()
