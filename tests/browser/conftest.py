"""Fixtures shared by every module in this directory.

They used to live inside `test_workspace.py`, which was fine while it was the only module
that drove a browser. It is not any more: `test_mobile.py` asks the same running review a
different set of questions, and the review is far too expensive to produce twice.

**Scope is the point of this file.** The fixtures were module-scoped, which ran the whole
bootstrap — workspace, server, browser, and one real deterministic review of the example
repository — once per module. With two modules that is twice, and the second time costs
the same forty seconds as the first. They are session-scoped here so it happens once for
the run, which is the difference between a forty-second suite and a five-minute one. Only
the scope changed; the bodies are what they were.

Two consequences of a session-scoped review worth knowing before adding a module:

* The workspace is shared, so a test that mutates it (answering a clarification composes a
  new review; authoring a policy changes what the *next* review retrieves) is visible to
  everything that runs after it. Existing revisions are immutable, so the address
  `review_url` returns keeps rendering the review it named.
* pytest collects files in alphabetical order, so `test_mobile.py` runs before
  `test_workspace.py` and reads the review before anything has answered anything.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest

from archcompass.bootstrap import Runtime
from tests.browser.harness import (
    BUNDLE,
    DESKTOP,
    PHONE,
    run_review,
    serve,
    workspace_runtime,
)


@pytest.fixture(scope="session")
def workspace(tmp_path_factory: pytest.TempPathFactory) -> Iterator[Runtime]:
    root: Path = tmp_path_factory.mktemp("workbench-browser")
    with workspace_runtime(root) as runtime:
        yield runtime


@pytest.fixture(scope="session")
def workspace_url(workspace: Runtime) -> Iterator[str]:
    with serve(workspace) as url:
        yield url


@pytest.fixture(scope="session")
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
    context = browser.new_context(**DESKTOP)
    opened = context.new_page()
    try:
        yield opened
    finally:
        context.close()


@pytest.fixture
def phone_page(browser, workspace_url: str):  # type: ignore[no-untyped-def]
    """The same application on a phone, emulated rather than merely made narrow.

    `set_viewport_size` on a desktop context changes the width and nothing else: the page
    still reports a fine pointer, no touch, and a device pixel ratio of one. Half of what
    goes wrong on a phone goes wrong in that gap — a hover rule that never lifts, a
    `@media (pointer: coarse)` branch that never applies — so this asks for a real mobile
    context instead.
    """

    context = browser.new_context(**PHONE)
    opened = context.new_page()
    try:
        yield opened
    finally:
        context.close()


@pytest.fixture(scope="session")
def review_url(browser, workspace_url: str) -> str:  # type: ignore[no-untyped-def]
    return run_review(browser, workspace_url)
