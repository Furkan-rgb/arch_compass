from __future__ import annotations

from pathlib import Path

import pytest

from archcompass.adapters.retrieval.policy_markdown import parse_policy
from archcompass.domain.errors import PolicyFormatError


def test_general_policy_has_all_required_sections() -> None:
    policy, chunks = parse_policy(
        Path("policies/general/hide-implementation-details.md").resolve()
    )
    assert policy.id == "hide-implementation-details"
    assert len(chunks) == 9
    assert len({chunk.chunk_id for chunk in chunks}) == 9


def test_incomplete_policy_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "bad.md"
    path.write_text(
        """---
id: bad
title: Bad
scope: general
strength: guidance
tags: [bad]
source: {author: Test, inspiration: []}
---
## Intent
Incomplete
""",
        encoding="utf-8",
    )
    with pytest.raises(PolicyFormatError):
        parse_policy(path)

