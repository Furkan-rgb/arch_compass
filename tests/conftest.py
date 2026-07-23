from __future__ import annotations

from pathlib import Path

import pytest

from archcompass.bootstrap import Runtime, build_runtime


@pytest.fixture
def fake_config_text() -> str:
    return """models:
  reasoning:
    provider: fake
    model: deterministic-architecture-v1
    base_url: http://127.0.0.1:11434
    temperature: 0.0
    timeout_seconds: 1
  embedding:
    provider: fake
    model: deterministic-token-hash-v1
    base_url: http://127.0.0.1:11434
    dimensions: 64
    timeout_seconds: 1
retrieval:
  top_k: 6
  max_sections_per_policy: 3
consultation:
  max_zoom_iterations: 3
  max_queries_per_iteration: 8
  max_query_results: 30
  max_excerpt_lines: 80
"""


@pytest.fixture
def runtime(tmp_path: Path, fake_config_text: str) -> Runtime:
    config_path = tmp_path / "config" / "models.yaml"
    config_path.parent.mkdir(parents=True)
    config_path.write_text(fake_config_text, encoding="utf-8")
    return build_runtime(tmp_path)
