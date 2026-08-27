"""The build's cache contract: the entry point revalidates, the hashed assets do not.

And what a *missing* asset is answered with, which belongs here because it is the same
question one step on: a browser holding an old `index.html` asks for hashed names the build
has removed, and what it is told about them decides whether the page can recover.
"""

from __future__ import annotations

import re

import pytest

pytest.importorskip("fastapi")

from fastapi.testclient import TestClient

from archcompass.bootstrap import Runtime
from archcompass.presentation.web import create_app


def test_the_entry_point_is_never_kept_but_its_assets_are(runtime: Runtime) -> None:
    with TestClient(create_app(runtime)) as client:
        index = client.get("/")
        assert index.status_code == 200
        assert index.headers["cache-control"] == "no-cache"

        asset = re.search(r'/assets/[\w.-]+', index.text)
        assert asset is not None, "the built entry point names no hashed asset"
        served = client.get(asset.group())
        assert served.status_code == 200
        assert served.headers["cache-control"] == "public, max-age=31536000, immutable"

        # A route the SPA owns is the entry point again, so it must revalidate too.
        deep = client.get("/reviews")
        assert deep.headers["cache-control"] == "no-cache"


def test_a_hashed_asset_that_is_gone_is_a_404_and_not_the_application(runtime: Runtime) -> None:
    """A tab open across a build asks for chunks that no longer exist, and must be told so.

    The catch-all answers every unknown path with `index.html`, which is right for
    `/reviews/abc` — a screen the single-page app draws — and wrong for a file. A chunk the
    build has removed is not there, and `200` with a page of HTML says it is: the wrong answer
    to give a browser, a cache or a log, whatever the page then does about it.

    What it does *not* decide is what the reader sees, which this docstring used to claim.
    Driven with that branch taken out, the MIME-type complaint goes to the console alone; the
    dynamic import still rejects with `Failed to fetch dynamically imported module`,
    `isChunkLoadError` in `frontend/src/app/error-boundary.tsx` still matches it, and the same
    screen still leads with the reload that works. This is a claim about the resource, not
    about the recovery.
    """

    with TestClient(create_app(runtime)) as client:
        missing = client.get("/assets/run-page-CNwucsBs.js")
        assert missing.status_code == 404
        assert missing.json()["code"] == "not_found"

        # And the distinction still holds in the other direction: a route is still the app.
        assert client.get("/reviews/does-not-exist").status_code == 200
