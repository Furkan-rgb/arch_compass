"""The build's cache contract: the entry point revalidates, the hashed assets do not."""

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
