"""What every browser check needs before it can look at anything: a workspace, a server,
a browser, and one real review.

`conftest.py` wraps the pieces here as pytest fixtures. `shoot_mobile.py` calls them
directly, because a screenshot dump is not a test and should not need pytest to produce
one. Keeping the bootstrap in a plain module is what lets both do that from one definition.

Nothing here is stubbed on the browser side. The bundle under `presentation/web/static` is
what is served, the API is the real application, and the review that runs is a real review
of a repository on disk — only the two models are substituted, and neither is reached over
the network:

* reasoning is pinned to the deterministic provider, so verdicts are reproducible;
* embedding is pinned to a local Ollama identity, which is recorded on the retrieval
  provenance but never called, because deterministic mode retrieves the whole corpus.
"""

from __future__ import annotations

import os
import re
import socket
import threading
import time
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import uvicorn

from archcompass.bootstrap import Runtime, build_runtime, pinned_model
from archcompass.presentation.web import create_app
from archcompass.reasoning.adapters.providers import DETERMINISTIC_MODEL

#: The repository a review is run against, and the bundle that has to exist before a browser
#: is worth opening. Both are resolved from this file rather than from the working
#: directory, because `shoot_mobile.py` is run by hand and not always from the repository
#: root, while pytest always sets it.
ROOT = Path(__file__).resolve().parents[2]
REPOSITORY = ROOT / "examples/cases/boundary-review/repository"
BUNDLE = ROOT / "src/archcompass/presentation/web/static/index.html"

#: Long enough for a full deterministic review of the example repository on a cold workspace.
REVIEW_TIMEOUT_MS = 180_000

#: The phone this suite is written against: an iPhone 15 in portrait, reported as a phone so
#: the page gets the mobile viewport and the touch-only branches of any hover rule, and
#: rendered at the density it actually ships at so a screenshot is worth looking at.
PHONE = {
    "viewport": {"width": 390, "height": 844},
    "device_scale_factor": 3,
    "is_mobile": True,
    "has_touch": True,
}

#: An iPad in portrait: past the 1024px breakpoint where a finding's argument and its
#: short of the 1280px one where the model's argument and the code it rests on sit side by
#: side. It is the width where both of those decisions have to hold at once, which is why it
#: is worth shooting rather than interpolating between the other two.
TABLET = {
    "viewport": {"width": 1024, "height": 1180},
    "device_scale_factor": 2,
    "is_mobile": False,
    "has_touch": True,
}

#: The width the rest of the suite already used. A laptop, not a monitor.
DESKTOP = {"viewport": {"width": 1440, "height": 960}}


def free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1])


@contextmanager
def workspace_runtime(root: Path) -> Iterator[Runtime]:
    """A workspace rooted at `root`, with both models pinned.

    Pinned rather than selected, so the page has both models the moment it loads and the
    test is about the workbench rather than about clicking through the model chooser.
    """

    before = os.environ.copy()
    os.environ["ARCHCOMPASS_EMBEDDING_PROVIDER"] = "ollama"
    os.environ["ARCHCOMPASS_EMBEDDING_MODEL"] = "nomic-embed-text"
    os.environ["ARCHCOMPASS_EMBEDDING_DIMENSIONS"] = "768"
    try:
        yield build_runtime(root, pin=pinned_model("fake", DETERMINISTIC_MODEL))
    finally:
        os.environ.clear()
        os.environ.update(before)


@contextmanager
def serve(runtime: Runtime) -> Iterator[str]:
    """The real application over HTTP on a loopback port, and its address."""

    port = free_port()
    server = uvicorn.Server(
        uvicorn.Config(create_app(runtime), host="127.0.0.1", port=port, log_level="warning")
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


def run_review(browser, workspace_url: str) -> str:  # type: ignore[no-untyped-def]
    """One real review of the example repository, and the address of the result.

    A deterministic review still parses the repository, detects candidates and composes a
    review, which is the slowest thing in this directory by an order of magnitude — so it
    happens once and everything that reads a review navigates to the address this returns.

    Driven at desktop width on purpose: this is setup, and the narrow layout of `/start` is
    the subject of its own check rather than a thing to be exercised incidentally here.
    """

    context = browser.new_context(**DESKTOP)
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


# --------------------------------------------------------------------------------------
# Getting to a state, without depending on what it is called
#
# The frontend is under active redesign, so everything below finds things by role, by
# landmark, or by a data attribute the application itself navigates with. Where a word is
# unavoidable it is one of the product's own nouns from the charter ("queue", "judgement
# context"), matched case-insensitively as a substring so a rewording around it still
# matches. Nothing here asserts on copy; these are directions, not claims.
# --------------------------------------------------------------------------------------


def wait_for_review(page, review_url: str) -> None:  # type: ignore[no-untyped-def]
    """Open a review and wait until the workbench has actually rendered.

    Waits on the surface tablist rather than on a heading, because the tablist is the one
    element that exists in every state of this page — composing, awaiting answers, done —
    and its labels are being rewritten while its structure is not.
    """

    page.goto(review_url, wait_until="networkidle")
    page.locator('[role="tablist"]').first.wait_for(state="visible", timeout=REVIEW_TIMEOUT_MS)
    page.locator('[role="tabpanel"]').first.wait_for(state="visible", timeout=REVIEW_TIMEOUT_MS)


def surface_tabs(page):  # type: ignore[no-untyped-def]
    """The tabs that switch which document about the review the page is showing.

    The first tablist in the document is the surface switcher: the review page renders it
    before any panel content, and the only other tablists in this app live inside surfaces
    or inside the judgement-context drawer, both of which are downstream of it.
    """

    return page.locator('[role="tablist"]').first.get_by_role("tab")


def show_everything(page) -> None:  # type: ignore[no-untyped-def]
    """Widen the docket's filter to the one that hides nothing.

    Located as the last control in the docket's only filter group rather than by its label:
    the three filters run narrowest to widest, so the widest is the last, and that ordering
    is structural in a way "All" is not.
    """

    group = page.get_by_role("group").first
    toggles = group.get_by_role("button")
    assert toggles.count() >= 2, "the docket filter is no longer a group of toggles"
    toggles.last.click()


def open_first_candidate(page) -> None:  # type: ignore[no-untyped-def]
    """Open the first row of the docket, which expands the assessment under it.

    `[data-candidate]` is the hook the docket's own `j`/`k` navigation reads, so it is
    load-bearing application code rather than a test seam, and it survives a redesign of
    everything visible about the row.
    """

    rows = page.locator("[data-candidate]")
    rows.first.wait_for(state="visible", timeout=REVIEW_TIMEOUT_MS)
    rows.first.click()


def open_judgement_context(page):  # type: ignore[no-untyped-def]
    """The drawer behind an open finding, holding case, policies, structure and provenance.

    Provenance is where this page keeps its longest machine-produced strings, which is
    exactly where a narrow layout gives way, so it is worth reaching.
    """

    page.get_by_role("button", name=re.compile(r"judgement context", re.I)).first.click()
    dialog = page.get_by_role("dialog")
    dialog.wait_for(state="visible")
    return dialog


def close_dialog(page) -> None:  # type: ignore[no-untyped-def]
    """Escape, because every drawer in this app closes on it and none of them need a name."""

    page.keyboard.press("Escape")
    page.get_by_role("dialog").first.wait_for(state="detached", timeout=10_000)
