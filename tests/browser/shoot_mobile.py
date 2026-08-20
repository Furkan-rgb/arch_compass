"""Every screen of the workbench, at both widths, in both themes, as PNGs on disk.

    uv run python tests/browser/shoot_mobile.py

Not a test: nothing here asserts anything. `test_mobile.py` answers the questions that have
an answer — does it fit, can a thumb hit it — and this answers the one that does not, which
is whether it looks right. It runs the same bootstrap the suite runs (a real workspace, a
real server, a real deterministic review of the example repository) and drives the same
states through the same helpers, so a shot and a failure are always of the same thing.

The theme is set the way a returning visitor's is: the preference is written to
`localStorage` before first paint and the inline script in `index.html` stamps `data-theme`
on `<html>` from it, with the emulated `prefers-color-scheme` set to match so that anything
keyed off the media query agrees with anything keyed off the attribute. The script checks
the attribute afterwards and says so if the two ever disagree.

Writes to `.artifacts/shots/`, which is gitignored.
"""

from __future__ import annotations

import re
import shutil
import sys
import tempfile
from collections.abc import Iterator
from pathlib import Path

# Run by hand rather than by pytest, and `python tests/browser/shoot_mobile.py` puts this
# file's own directory on the path rather than the repository root — so the package this
# file belongs to is not importable until the root is added.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from tests.browser.harness import (
    DESKTOP,
    PHONE,
    ROOT,
    close_dialog,
    open_first_candidate,
    open_judgement_context,
    open_queue,
    run_review,
    serve,
    show_everything,
    surface_tabs,
    wait_for_review,
    workspace_runtime,
)

OUT = ROOT / ".artifacts/shots"

#: The phone this is designed for and the laptop it is checked on. The queue is a column
#: above 1024px and a bottom sheet below it, which is the one structural difference between
#: the two and the reason both are shot.
WIDTHS = {"390": PHONE, "1440": DESKTOP}

THEMES = ("light", "dark")

#: Same key `lib/theme.ts` reads and the inline script in `index.html` reads before paint.
THEME_KEY = "archcompass.theme"


def _slug(text: str) -> str:
    first = text.strip().splitlines()[0] if text.strip() else "untitled"
    return re.sub(r"[^a-z0-9]+", "-", first.lower()).strip("-") or "untitled"


def _settle(page, pause: int = 350) -> None:  # type: ignore[no-untyped-def]
    """Let the drawers finish sliding and the fonts finish swapping before the shutter."""

    page.wait_for_timeout(pause)
    page.evaluate(
        """() => Promise.all([
             document.fonts ? document.fonts.ready : null,
             ...document.getAnimations()
               .filter((a) => a.effect && a.effect.getComputedTiming().iterations !== Infinity)
               .map((a) => a.finished.catch(() => {})),
           ])"""
    )


def capture(page, workspace_url: str, review_url: str, width: str, theme: str) -> Iterator[Path]:  # type: ignore[no-untyped-def]
    """One pass over every screen, at one width in one theme."""

    def shoot(slug: str) -> Path:
        _settle(page)
        path = OUT / f"{slug}-{width}-{theme}.png"
        page.screenshot(path=str(path), full_page=True)
        return path

    page.goto(f"{workspace_url}/", wait_until="networkidle")
    stamped = page.evaluate("() => document.documentElement.dataset.theme")
    if stamped != theme:
        print(f"  ! asked for {theme}, the page stamped {stamped!r}", file=sys.stderr)
    yield shoot("landing")

    page.goto(f"{workspace_url}/start", wait_until="networkidle")
    yield shoot("start")

    wait_for_review(page, review_url)
    tabs = surface_tabs(page)
    for index in range(tabs.count()):
        tab = tabs.nth(index)
        slug = _slug(tab.inner_text())
        tab.click()
        yield shoot(f"review-{slug}")

    tabs.first.click()

    # The one structural difference between the two widths: below the tablet breakpoint the
    # queue is a sheet that has to be opened, above it the queue is already the left column.
    phone = width == "390"
    if phone:
        queue = open_queue(page)
        yield shoot("review-queue")
    else:
        queue = page
    show_everything(queue)
    yield shoot("review-queue-all")

    open_first_candidate(queue)
    yield shoot("review-finding")

    open_judgement_context(page)
    yield shoot("review-judgement-context")
    close_dialog(page)


def main() -> int:
    from playwright.sync_api import sync_playwright

    if not (ROOT / "src/archcompass/presentation/web/static/index.html").is_file():
        print("run `make frontend-build` first — there is no bundle to shoot", file=sys.stderr)
        return 1

    if OUT.exists():
        shutil.rmtree(OUT)
    OUT.mkdir(parents=True)

    root = Path(tempfile.mkdtemp(prefix="archcompass-shots-"))
    written: list[Path] = []
    try:
        with (
            workspace_runtime(root) as runtime,
            serve(runtime) as workspace_url,
            sync_playwright() as driver,
        ):
            browser = driver.chromium.launch()
            try:
                print("running one deterministic review of the example repository…")
                review_url = run_review(browser, workspace_url)
                for width, emulation in WIDTHS.items():
                    for theme in THEMES:
                        print(f"{width}px, {theme}")
                        context = browser.new_context(**emulation, color_scheme=theme)
                        # Before first paint, so nothing flashes the other theme into a
                        # screenshot and no page has to be reloaded to change it.
                        context.add_init_script(
                            f"try {{ localStorage.setItem('{THEME_KEY}', '{theme}'); }}"
                            f" catch (e) {{}}"
                        )
                        page = context.new_page()
                        try:
                            for path in capture(page, workspace_url, review_url, width, theme):
                                written.append(path)
                                print(f"  {path}")
                        finally:
                            context.close()
            finally:
                browser.close()
    finally:
        shutil.rmtree(root, ignore_errors=True)

    print(f"\n{len(written)} screenshots in {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
