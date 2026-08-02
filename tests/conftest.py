from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path

import pytest

from archcompass.adapters.models.deterministic import DETERMINISTIC_MODEL
from archcompass.bootstrap import Runtime, build_runtime, pinned_model


@pytest.fixture(autouse=True)
def isolate_environment() -> Iterator[None]:
    """Take back what loading a `.env` puts into the process environment.

    `load_environment_file` writes into `os.environ` and nothing removes it, so one test
    that loads a workspace's `.env` would go on deciding the configuration for every test
    after it. That is the same leak that had this suite reading the developer's own `.env`,
    one scope smaller and just as invisible.
    """

    before = os.environ.copy()
    yield
    os.environ.clear()
    os.environ.update(before)


@pytest.fixture
def runtime(tmp_path: Path) -> Runtime:
    # Pinned rather than chosen. A workspace with no stored selection reasons with nothing,
    # and every test reaching this fixture means to run against the deterministic
    # substitute — pinning says so in one place instead of each of them clicking a model
    # first.
    return build_runtime(tmp_path, pin=pinned_model("fake", DETERMINISTIC_MODEL))
