from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path

import pytest

from archcompass.bootstrap import Runtime, build_runtime


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
def fake_config_text() -> str:
    return """models:
  reasoning:
    provider: fake
    model: deterministic-architecture-v1
    base_url: http://127.0.0.1:11434
    timeout_seconds: 1
    context_window_tokens: 32768
    max_output_tokens: 16384
"""


@pytest.fixture
def runtime(tmp_path: Path, fake_config_text: str) -> Runtime:
    config_path = tmp_path / "config" / "models.yaml"
    config_path.parent.mkdir(parents=True)
    config_path.write_text(fake_config_text, encoding="utf-8")
    # Named rather than discovered. A run reads `.env` from the working directory as well as
    # the workspace, so a developer who points their own workspace at a provider would
    # silently point the suite at it too — and every test here means to run against the
    # substitute written just above.
    return build_runtime(tmp_path, models_config=config_path)
