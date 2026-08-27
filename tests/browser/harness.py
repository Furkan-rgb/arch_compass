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

#: Everything the emitted bundle is made of, for the staleness check below.
#:
#: `frontend/src` is the obvious one and was for a while the only one, which left the check
#: silent about four more, each of which the build reads:
#:
#: * `frontend/index.html` is the entry document. Adding one `<meta>` to it put that `<meta>`
#:   in the emitted `static/index.html` on the next build, measured.
#: * `frontend/vite.config.ts` decides the output names, the plugins and the aliases. Setting
#:   `entryFileNames` and `chunkFileNames` to `.mjs` renamed every emitted chunk, measured.
#: * `frontend/vite-plugins/` is the code that config composes, and one of those plugins
#:   decides which files survive in the output directory at all — `grace-window.test.ts`.
#: * `frontend/package.json` pins the version of every dependency that lands in a chunk.
#:
#: Editing any of the four without rebuilding left this check green, which is what makes a
#: stale bundle answer the browser tests in the wrong bytes.
BUNDLE_INPUTS = (
    ROOT / "frontend/src",
    ROOT / "frontend/index.html",
    ROOT / "frontend/vite.config.ts",
    ROOT / "frontend/vite-plugins",
    ROOT / "frontend/package.json",
)

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


def _is_test_only(name: str) -> bool:
    """Whether a file under `frontend/` is one no build ever reads.

    Two shapes, and the second is the one this check got wrong. `*.test.ts` and `*.test.tsx`
    are the suites themselves. `test-setup.ts` and `test-fixtures.ts` are the vitest
    environment and its fixtures: named by prefix rather than by suffix, imported by
    `vite.config.ts` under `test.setupFiles` and by the suites, and reachable from no module
    the browser build emits. Editing either cannot change a byte of the bundle, and a guard
    that fails when you edit a test is a guard people delete — which is the reason the whole
    exclusion exists, and the reason it has to cover both spellings.
    """

    return name.endswith((".test.ts", ".test.tsx")) or name.startswith("test-")


def _newer_than(built: float) -> list[Path]:
    """The files the bundle is built from that have changed since it was built.

    The list rather than the newest time, because the failure message is the useful half: a
    reader who has just edited three files wants to know which one this is about.
    """

    stale: list[Path] = []
    for source in BUNDLE_INPUTS:
        entries = source.rglob("*") if source.is_dir() else [source]
        for entry in entries:
            if not entry.is_file() or _is_test_only(entry.name):
                continue
            if entry.stat().st_mtime > built:
                stale.append(entry)
    return sorted(stale)


def assert_bundle_is_current() -> None:
    """Refuse to drive a browser against a bundle older than the code it is made of.

    A stale bundle is what makes this whole directory worse than nothing. Every module here
    drives whatever is on disk, and `test_first_load.py` now *weighs* what is on disk, so a
    build from before the change under test answers every question about the wrong bytes —
    and answers them green. That has produced false findings on this branch more than once,
    which is why the check is here rather than in anybody's head.

    `make check` and `make test-browser` both run `frontend-build` first, so this never fires
    on the ordinary paths. It is for `uv run pytest -m browser` typed by hand after an edit,
    which is the path that has actually gone wrong.

    This is the part of `frontend/entry-graph.test.ts` that outlived it, and it measures the
    one thing a browser cannot see: whether the bundle it is looking at is the bundle the
    source describes. The note left here when that file went said the rest of it was an
    approximation of what `test_first_load.py` measures in a browser directly. That was true of
    most of it and false of three assertions — the Markdown renderer's reach, and the two that
    kept its fingerprints from matching nothing at all — which had no replacement anywhere
    until `test_first_load.py` grew named Markdown checks of its own. A deletion note that
    accounts for a file it does not account for is how an assertion goes missing quietly.
    """

    assert BUNDLE.is_file(), f"no build at {BUNDLE.parent} — run `make frontend-build`"
    stale = _newer_than(BUNDLE.stat().st_mtime)
    assert not stale, (
        f"{len(stale)} of the files {BUNDLE} is built from are newer than it — "
        f"{', '.join(str(entry.relative_to(ROOT)) for entry in stale[:5])} — so the browser "
        "would be driving a bundle from before the change under test — run "
        "`make frontend-build`"
    )


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
# landmark, or by a data attribute carrying an identity the application itself works in —
# `data-candidate`, which holds `finding.candidate.id`. That used to read "a data attribute
# the application itself navigates with", which is the third place on this branch to have
# said so and is not true of any attribute here; `open_first_candidate` below has the
# measurement. Where a word is
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

    Located by the group's own accessible name, and then as the last control inside it: the
    three filters run narrowest to widest, so the widest is the last, and that ordering is
    structural in a way "All" is not.

    It used to take `get_by_role("group").first` on the argument that the docket's filter was
    the first group on the page. That stopped being true and nothing said so — the review
    grew surfaces with groups of their own, and `<details>` carries the group role
    implicitly, so "the first group" silently became something else and this helper failed on
    a count it could not explain. A name is the thing that identifies this control; its
    position among unrelated controls never was.

    The wait is the second half of the same lesson. `count()` is the one locator method that
    does not auto-wait: it asks the page what is there *now* and answers immediately, so
    called straight after the surface tabs put the docket back on screen it counted a filter
    React had not rendered yet and failed claiming the control was gone. Everything else in
    this module waits for the thing it is about to touch — `open_first_candidate` waits on
    its rows, `wait_for_review` on its tablist — and this was the one place that did not.
    Waiting for the toggle it is going to click is both the wait and the assertion that the
    control still exists, and `wait_for` reports which one it gave up on.
    """

    group = page.get_by_role("group", name="Filter the docket").first
    group.wait_for(state="visible", timeout=REVIEW_TIMEOUT_MS)
    toggles = group.get_by_role("button")
    # The widest filter, and the wait that makes the count below a real count.
    toggles.last.wait_for(state="visible", timeout=REVIEW_TIMEOUT_MS)
    assert toggles.count() >= 2, "the docket filter is no longer a group of toggles"
    toggles.last.click()


def open_first_candidate(page) -> None:  # type: ignore[no-untyped-def]
    """Open the first row of the docket, which expands the assessment under it.

    `[data-candidate]` is the row's stated identity, and this used to claim more than that:
    that the docket's own `j`/`k` navigation reads it, so it was load-bearing application
    code rather than a test seam. It is not. `docket.tsx:671` writes the attribute onto the
    row's button and no non-test line in `frontend/src` mentions it anywhere else; the walk
    steps through `visible.map((finding) => finding.candidate.id)` in React state
    (`docket.tsx:1468`). A false reason for a good choice is worse than no reason, because
    the next helper written beside it inherits the reason and not the check.

    The choice is still right, on the claim that survives measuring. What the attribute holds
    is `finding.candidate.id` — the identity the walk steps through, and the key every
    decision is filed under — put there by the row itself. That is why it survives a redesign
    of everything visible about the row, which a name, a position or a shape does not.
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
