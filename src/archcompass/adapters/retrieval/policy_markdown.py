"""Strict Markdown policy parser.

The nine required headings must be present, distinct and non-empty. The policy parser keeps
the authored document authoritative; the retrieval index separately derives heading chunks
with content hashes and policy metadata.
"""

from __future__ import annotations

import re
from hashlib import sha256
from pathlib import Path

import yaml
from pydantic import ValidationError

from archcompass.boundary.base import stable_id
from archcompass.boundary.policy import (
    PolicyDocument,
    PolicyDraft,
    PolicyScope,
    PolicySource,
    PolicyStrength,
)
from archcompass.domain.errors import PersistenceError, PolicyFormatError

REQUIRED_SECTIONS = {
    "intent",
    "guidance",
    "signals",
    "diagnostic questions",
    "likely consequences",
    "exceptions",
    "positive example",
    "counterexample",
    "related policies",
}


def canonicalize_policy_source(source: Path, *, require_exists: bool = True) -> Path:
    expanded = source.expanduser()
    if expanded.is_symlink():
        raise PolicyFormatError(f"Policy source must not be a symlink: {source}")
    try:
        canonical = expanded.resolve(strict=require_exists)
    except OSError as error:
        raise PolicyFormatError(f"Could not resolve policy source {source}: {error}") from error
    if require_exists and not (canonical.is_file() or canonical.is_dir()):
        raise PolicyFormatError(f"Policy source does not exist: {source}")
    return canonical


class MarkdownPolicySourceInspector:
    def canonicalize(self, source: Path, *, require_exists: bool = True) -> Path:
        canonical = canonicalize_policy_source(source, require_exists=require_exists)
        if require_exists:
            _policy_paths(canonical)
        return canonical

    def load_documents(self, sources: list[Path]) -> list[PolicyDocument]:
        return load_policy_sources(sources)


#: What the front matter of an authored policy says wrote it. Bundled policies name their
#: own corpus here; a policy written in this workspace has no other provenance to claim, and
#: the field is not a form question — nothing downstream weighs a policy by its author.
AUTHORED_POLICY_AUTHOR = "Workspace"

#: The name a policy is written under before it has been parsed. Deliberately not `*.md`,
#: which is the glob a source directory is read by: a draft that never passes the parser is
#: never a member of the corpus, not even for the moment between writing and checking it.
STAGED_SUFFIX = ".md.staged"


class MarkdownPolicyStore:
    """The authored directory, written in the format the parser above reads.

    Rendered through `yaml.safe_dump` rather than by formatting the front matter by hand, so
    a title with a colon in it stays one scalar. What the dump cannot defend against is a
    `---` inside a value, which would close the front matter early — `PolicyDraft` refuses
    that at the door, and the parse this class is staged for catches whatever it missed.
    """

    def stage(self, directory: Path, policy_id: str, draft: PolicyDraft) -> Path:
        staged = directory / f"{policy_id}{STAGED_SUFFIX}"
        try:
            directory.mkdir(parents=True, exist_ok=True)
            staged.write_text(_render_policy(policy_id, draft), encoding="utf-8")
        except OSError as error:
            raise PersistenceError(
                f"Could not write the policy {policy_id} to {directory}: {error}"
            ) from error
        return staged

    def publish(self, staged: Path) -> Path:
        published = staged.with_name(staged.name.removesuffix(STAGED_SUFFIX) + ".md")
        try:
            # Replace rather than write-then-delete: an edit that survived the parse becomes
            # visible whole or not at all, and never as a half-written file a review reads.
            staged.replace(published)
        except OSError as error:
            raise PersistenceError(
                f"Could not put the policy {published.stem} in place: {error}"
            ) from error
        return published

    def discard(self, staged: Path) -> None:
        staged.unlink(missing_ok=True)

    def remove(self, directory: Path, policy_id: str) -> None:
        try:
            (directory / f"{policy_id}.md").unlink()
        except OSError as error:
            raise PersistenceError(
                f"Could not delete the policy {policy_id}: {error}"
            ) from error


def _render_policy(policy_id: str, draft: PolicyDraft) -> str:
    front_matter = yaml.safe_dump(
        {
            "id": policy_id,
            "title": draft.title,
            "scope": PolicyScope.GENERAL.value,
            "strength": draft.strength.value,
            "tags": list(draft.tags),
            "source": {"author": AUTHORED_POLICY_AUTHOR, "inspiration": []},
            "description": draft.description,
        },
        sort_keys=False,
        allow_unicode=True,
        # `None` is flow style for collections that hold no collection of their own, which
        # is what makes `tags: [layering, dependencies]` come out the way every bundled
        # policy already writes it. An authored file should be indistinguishable from one
        # of those in an editor: they are the same kind of file and get edited the same way.
        default_flow_style=None,
    )
    return f"---\n{front_matter}---\n{draft.body.strip()}\n"


def parse_policy(path: Path) -> PolicyDocument:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as error:
        raise PolicyFormatError(f"Could not read policy {path}: {error}") from error
    if not text.startswith("---\n"):
        raise PolicyFormatError(f"Policy {path} must begin with YAML front matter")
    try:
        _, front_matter, body = text.split("---", maxsplit=2)
        metadata = yaml.safe_load(front_matter)
        source = PolicySource.model_validate(metadata["source"])
        scope = PolicyScope(metadata["scope"])
        policy = PolicyDocument(
            id=metadata["id"],
            title=metadata["title"],
            description=metadata.get("description"),
            scope=scope,
            applies_to=_resolve_applicability(
                path=path,
                scope=scope,
                authored_subject=metadata.get("applies_to"),
            ),
            strength=PolicyStrength(metadata["strength"]),
            tags=metadata["tags"],
            source=source,
            body=body.strip(),
            source_path=str(path),
            content_hash=sha256(text.encode("utf-8")).hexdigest(),
        )
    except (ValueError, KeyError, TypeError, yaml.YAMLError, ValidationError) as error:
        raise PolicyFormatError(f"Invalid front matter in {path}: {error}") from error

    matches = list(re.finditer(r"^##\s+(.+?)\s*$", policy.body, flags=re.MULTILINE))
    sections: dict[str, str] = {}
    for ordinal, match in enumerate(matches):
        heading = match.group(1).strip()
        normalized_heading = heading.casefold()
        if normalized_heading in sections:
            raise PolicyFormatError(
                f"Policy {path} contains duplicate section heading: {heading}"
            )
        start = match.end()
        end = matches[ordinal + 1].start() if ordinal + 1 < len(matches) else len(policy.body)
        sections[normalized_heading] = policy.body[start:end].strip()
    missing = REQUIRED_SECTIONS - sections.keys()
    if missing:
        raise PolicyFormatError(f"Policy {path} is missing sections: {', '.join(sorted(missing))}")
    empty = sorted(section for section in REQUIRED_SECTIONS if not sections[section])
    if empty:
        raise PolicyFormatError(
            f"Policy {path} has empty required sections: {', '.join(empty)}"
        )
    return policy


def _resolve_applicability(
    *,
    path: Path,
    scope: PolicyScope,
    authored_subject: object,
) -> str | None:
    if scope is PolicyScope.GENERAL:
        if authored_subject is not None:
            raise ValueError("General policies must not declare applies_to")
        return None
    if authored_subject is not None:
        if not isinstance(authored_subject, str) or not authored_subject.strip():
            raise ValueError("applies_to must be a nonempty string")
        return authored_subject.strip()
    if scope in {PolicyScope.USER, PolicyScope.ORGANISATION}:
        raise ValueError(f"{scope.value} policies must declare applies_to")

    repository_root = _repository_root_for_local_policy(path)
    if repository_root is None:
        raise ValueError(
            f"{scope.value} policies outside <repository>/.archcompass/policies "
            "must declare applies_to"
        )
    return stable_id("repo", str(repository_root))


def _repository_root_for_local_policy(path: Path) -> Path | None:
    resolved = path.expanduser().resolve(strict=True)
    for parent in resolved.parents:
        if parent.name == "policies" and parent.parent.name == ".archcompass":
            return parent.parent.parent
    return None


def load_policy_sources(sources: list[Path]) -> list[PolicyDocument]:
    parsed: list[PolicyDocument] = []
    seen: dict[str, Path] = {}
    canonical_sources: dict[Path, None] = {}
    for source in sources:
        expanded = source.expanduser()
        require_exists = expanded.exists() or expanded.is_symlink()
        canonical_sources[
            canonicalize_policy_source(source, require_exists=require_exists)
        ] = None
    for source in canonical_sources:
        if not source.exists():
            continue
        for path in _policy_paths(source):
            policy = parse_policy(path)
            if policy.id in seen:
                raise PolicyFormatError(
                    f"Duplicate policy ID {policy.id} in {seen[policy.id]} and {path}"
                )
            seen[policy.id] = path
            parsed.append(policy)
    return sorted(parsed, key=lambda item: item.id)


def _policy_paths(source: Path) -> list[Path]:
    raw_paths = [source] if source.is_file() else sorted(source.rglob("*.md"))
    paths: list[Path] = []
    for raw_path in raw_paths:
        try:
            path = raw_path.resolve(strict=True)
        except OSError as error:
            raise PolicyFormatError(
                f"Could not resolve policy path {raw_path}: {error}"
            ) from error
        if source.is_dir() and not path.is_relative_to(source):
            raise PolicyFormatError(
                f"Policy path escapes source directory through a symlink: {raw_path}"
            )
        if source.is_file() and path != source:
            raise PolicyFormatError(f"Policy path escapes registered source: {raw_path}")
        paths.append(path)
    return list(dict.fromkeys(paths))
