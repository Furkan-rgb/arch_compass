from __future__ import annotations

from pathlib import Path

import pytest

from archcompass.adapters.retrieval.policy_markdown import (
    MarkdownPolicySourceInspector,
    load_policy_sources,
    parse_policy,
)
from archcompass.bootstrap import BUNDLED_POLICY_SOURCE
from archcompass.domain.errors import PolicyFormatError


def test_general_policy_has_all_required_sections() -> None:
    policy, chunks = parse_policy(
        BUNDLED_POLICY_SOURCE / "hide-implementation-details.md"
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


def test_duplicate_policy_sections_are_rejected_case_insensitively(
    tmp_path: Path,
) -> None:
    source = BUNDLED_POLICY_SOURCE / "hide-implementation-details.md"
    path = tmp_path / "duplicate.md"
    path.write_text(
        source.read_text(encoding="utf-8") + "\n## intent\nDuplicate intent.\n",
        encoding="utf-8",
    )

    with pytest.raises(PolicyFormatError, match="duplicate section heading"):
        parse_policy(path)


def test_empty_required_policy_section_is_rejected(tmp_path: Path) -> None:
    source = BUNDLED_POLICY_SOURCE / "hide-implementation-details.md"
    text = source.read_text(encoding="utf-8")
    path = tmp_path / "empty.md"
    path.write_text(
        text.replace(
            "## Intent\nPrevent callers from depending on decisions that belong to another module.",
            "## Intent\n",
            1,
        ),
        encoding="utf-8",
    )

    with pytest.raises(PolicyFormatError, match="empty required sections: intent"):
        parse_policy(path)


def test_policy_source_rejects_a_symlink_escape(tmp_path: Path) -> None:
    source = tmp_path / "policies"
    source.mkdir()
    outside = tmp_path / "outside.md"
    outside.write_text(
        (BUNDLED_POLICY_SOURCE / "hide-implementation-details.md").read_text(
            encoding="utf-8"
        ),
        encoding="utf-8",
    )
    (source / "escaped.md").symlink_to(outside)

    with pytest.raises(PolicyFormatError, match="escapes source directory"):
        load_policy_sources([source])


def test_registered_policy_source_must_not_be_a_symlink(tmp_path: Path) -> None:
    source = tmp_path / "policies"
    source.mkdir()
    alias = tmp_path / "policy-alias"
    alias.symlink_to(source, target_is_directory=True)

    with pytest.raises(PolicyFormatError, match="must not be a symlink"):
        MarkdownPolicySourceInspector().canonicalize(alias)
    with pytest.raises(PolicyFormatError, match="must not be a symlink"):
        load_policy_sources([alias])
