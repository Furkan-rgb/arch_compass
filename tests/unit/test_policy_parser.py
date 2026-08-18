from __future__ import annotations

import re
from pathlib import Path

import pytest

from archcompass.adapters.retrieval.policy_markdown import (
    REQUIRED_SECTIONS,
    MarkdownPolicySourceInspector,
    load_policy_sources,
    parse_policy,
)
from archcompass.bootstrap import BUNDLED_POLICY_SOURCE
from archcompass.boundary.base import stable_id
from archcompass.domain.errors import PolicyFormatError


def _section(body: str, heading: str) -> str:
    """The text under one `##` heading.

    The parser used to hand these back as chunks, because they were the unit an embedding
    index retrieved. Nothing retrieves, so a policy is now parsed whole and a test that
    wants one section cuts it out here — where the cutting is the test's business rather
    than a shape the production code carries for it.
    """

    matches = list(re.finditer(r"^##\s+(.+?)\s*$", body, flags=re.MULTILINE))
    for ordinal, match in enumerate(matches):
        if match.group(1).strip().casefold() != heading.casefold():
            continue
        end = matches[ordinal + 1].start() if ordinal + 1 < len(matches) else len(body)
        return body[match.end() : end].strip()
    raise AssertionError(f"no {heading} section")


def _policy_text(front_matter: str) -> str:
    """A whole policy file with the front matter a test wants over a valid body.

    The other fixtures below start from a bundled policy and rewrite one of its lines, which
    is the right shape when the subject is a section or a path. Front matter is the subject
    here, so these carry their own rather than editing a file the corpus owns.
    """

    sections = "".join(f"## {heading.title()}\nText.\n\n" for heading in sorted(REQUIRED_SECTIONS))
    return f"---\n{front_matter}\n---\n{sections}"


def test_general_policy_has_all_required_sections() -> None:
    policy = parse_policy(BUNDLED_POLICY_SOURCE / "hide-implementation-details.md")

    assert policy.id == "hide-implementation-details"
    # Parsing succeeding is the assertion — the parser refuses a policy missing any
    # required section, or carrying an empty or duplicated one — and this states what
    # that means: all nine are there to read.
    for heading in REQUIRED_SECTIONS:
        assert _section(policy.body, heading)


def test_bundled_corpus_includes_provider_boundary_and_ousterhout_guidance() -> None:
    policies = {
        policy.id: policy for policy in load_policy_sources([BUNDLED_POLICY_SOURCE])
    }

    expected_ids = {
        "separate-model-context-from-provider-transport",
        "different-layer-different-abstraction",
        "design-it-twice",
    }
    assert expected_ids <= policies.keys()
    assert policies["separate-model-context-from-provider-transport"].strength.value == "preferred"
    for policy_id in {"different-layer-different-abstraction", "design-it-twice"}:
        assert any(
            "John Ousterhout" in inspiration
            for inspiration in policies[policy_id].source.inspiration
        )


def test_bundled_policy_relationships_and_ousterhout_provenance_are_resolved() -> None:
    loaded = load_policy_sources([BUNDLED_POLICY_SOURCE])
    policy_ids = {policy.id for policy in loaded}
    ousterhout_policy_ids = {
        "design-it-twice",
        "different-layer-different-abstraction",
        "eliminate-errors-by-design",
        "hide-implementation-details",
        "organize-by-responsibility",
        "prefer-deep-modules",
        "pull-complexity-downward",
    }

    for policy in loaded:
        related = _section(policy.body, "Related policies")
        referenced_ids = set(re.findall(r"`([a-z0-9-]+)`", related))
        assert referenced_ids <= policy_ids
        if policy.id in ousterhout_policy_ids:
            assert any(
                inspiration.startswith("John Ousterhout")
                for inspiration in policy.source.inspiration
            )


def test_authored_description_is_parsed_and_stripped(tmp_path: Path) -> None:
    path = tmp_path / "described.md"
    path.write_text(
        _policy_text(
            "id: described\n"
            "title: Described\n"
            "description: '  Keep the rule where its consequences land.  '\n"
            "scope: general\n"
            "strength: guidance\n"
            "tags: [described]\n"
            "source: {author: Test, inspiration: []}"
        ),
        encoding="utf-8",
    )

    assert parse_policy(path).description == "Keep the rule where its consequences land."


def test_policy_without_a_description_parses_with_none(tmp_path: Path) -> None:
    path = tmp_path / "undescribed.md"
    path.write_text(
        _policy_text(
            "id: undescribed\n"
            "title: Undescribed\n"
            "scope: general\n"
            "strength: guidance\n"
            "tags: [undescribed]\n"
            "source: {author: Test, inspiration: []}"
        ),
        encoding="utf-8",
    )

    assert parse_policy(path).description is None


@pytest.mark.parametrize(
    "description",
    ["'   '", "[a, list, not, a, sentence]"],
    ids=["blank", "not-a-string"],
)
def test_unusable_policy_description_is_rejected(tmp_path: Path, description: str) -> None:
    path = tmp_path / "unusable.md"
    path.write_text(
        _policy_text(
            "id: unusable\n"
            "title: Unusable\n"
            f"description: {description}\n"
            "scope: general\n"
            "strength: guidance\n"
            "tags: [unusable]\n"
            "source: {author: Test, inspiration: []}"
        ),
        encoding="utf-8",
    )

    with pytest.raises(PolicyFormatError, match="Invalid front matter"):
        parse_policy(path)


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
    # The heading is there and the body under it is not. An empty section is the subject, so
    # the policy carries its own body rather than blanking a line the bundled corpus owns.
    text = _policy_text(
        "id: empty\n"
        "title: Empty\n"
        "scope: general\n"
        "strength: guidance\n"
        "tags: [empty]\n"
        "source: {author: Test, inspiration: []}"
    ).replace("## Intent\nText.\n", "## Intent\n", 1)
    path = tmp_path / "empty.md"
    path.write_text(text, encoding="utf-8")

    with pytest.raises(PolicyFormatError, match="empty required sections: intent"):
        parse_policy(path)


def test_policy_source_rejects_a_symlink_escape(tmp_path: Path) -> None:
    source = tmp_path / "policies"
    source.mkdir()
    outside = tmp_path / "outside.md"
    outside.write_text(
        (BUNDLED_POLICY_SOURCE / "hide-implementation-details.md").read_text(encoding="utf-8"),
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


@pytest.mark.parametrize("scope", ["user", "organisation"])
def test_user_and_organisation_policies_require_explicit_applicability(
    tmp_path: Path,
    scope: str,
) -> None:
    template = (BUNDLED_POLICY_SOURCE / "contain-dependencies.md").read_text(encoding="utf-8")
    path = tmp_path / f"{scope}.md"
    path.write_text(
        template.replace("scope: general", f"scope: {scope}", 1),
        encoding="utf-8",
    )

    with pytest.raises(PolicyFormatError, match=f"{scope} policies must declare applies_to"):
        parse_policy(path)


@pytest.mark.parametrize("scope", ["repository", "accepted_adr"])
def test_repository_scoped_policy_derives_atlas_repository_identity_when_local(
    tmp_path: Path,
    scope: str,
) -> None:
    repository = tmp_path / "repository"
    path = repository / ".archcompass" / "policies" / f"{scope}.md"
    path.parent.mkdir(parents=True)
    template = (BUNDLED_POLICY_SOURCE / "contain-dependencies.md").read_text(encoding="utf-8")
    path.write_text(
        template.replace("scope: general", f"scope: {scope}", 1),
        encoding="utf-8",
    )

    policy = parse_policy(path)

    assert policy.applies_to == stable_id("repo", str(repository.resolve()))


def test_repository_policy_outside_repository_source_requires_explicit_subject(
    tmp_path: Path,
) -> None:
    template = (BUNDLED_POLICY_SOURCE / "contain-dependencies.md").read_text(encoding="utf-8")
    path = tmp_path / "repository.md"
    path.write_text(
        template.replace("scope: general", "scope: repository", 1),
        encoding="utf-8",
    )

    with pytest.raises(
        PolicyFormatError,
        match=r"outside <repository>/\.archcompass/policies must declare applies_to",
    ):
        parse_policy(path)


def test_scoped_policy_accepts_an_explicit_subject(tmp_path: Path) -> None:
    template = (BUNDLED_POLICY_SOURCE / "contain-dependencies.md").read_text(encoding="utf-8")
    path = tmp_path / "organisation.md"
    path.write_text(
        template.replace(
            "scope: general",
            "scope: organisation\napplies_to: example-organisation",
            1,
        ),
        encoding="utf-8",
    )

    policy = parse_policy(path)

    assert policy.applies_to == "example-organisation"


def test_general_policy_rejects_misleading_applicability(tmp_path: Path) -> None:
    template = (BUNDLED_POLICY_SOURCE / "contain-dependencies.md").read_text(encoding="utf-8")
    path = tmp_path / "general.md"
    path.write_text(
        template.replace(
            "scope: general",
            "scope: general\napplies_to: example-organisation",
            1,
        ),
        encoding="utf-8",
    )

    with pytest.raises(PolicyFormatError, match="must not declare applies_to"):
        parse_policy(path)
