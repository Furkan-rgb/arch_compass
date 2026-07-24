"""Strict Markdown policy parser and section-aware chunker."""

from __future__ import annotations

import re
from hashlib import sha256
from pathlib import Path

import yaml
from pydantic import ValidationError

from archcompass.domain.base import stable_id
from archcompass.domain.errors import PolicyFormatError
from archcompass.domain.policy import (
    PolicyChunk,
    PolicyDocument,
    PolicyScope,
    PolicySource,
    PolicyStrength,
)

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
        return [policy for policy, _chunks in load_policy_sources(sources)]


def parse_policy(path: Path) -> tuple[PolicyDocument, list[PolicyChunk]]:
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
        policy = PolicyDocument(
            id=metadata["id"],
            title=metadata["title"],
            scope=PolicyScope(metadata["scope"]),
            strength=PolicyStrength(metadata["strength"]),
            tags=metadata["tags"],
            source=source,
            body=body.strip(),
            source_path=str(path),
            content_hash=sha256(text.encode("utf-8")).hexdigest(),
        )
    except (ValueError, KeyError, TypeError, yaml.YAMLError, ValidationError) as error:
        raise PolicyFormatError(f"Invalid front matter in {path}: {error}") from error

    chunks: list[PolicyChunk] = []
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
        section_text = policy.body[start:end].strip()
        sections[normalized_heading] = section_text
        content_hash = sha256(section_text.encode("utf-8")).hexdigest()
        chunks.append(
            PolicyChunk(
                chunk_id=stable_id(
                    "pchunk", policy.id, normalized_heading, str(ordinal), content_hash
                ),
                policy_id=policy.id,
                section=heading,
                ordinal=ordinal,
                text=section_text,
                content_hash=content_hash,
            )
        )
    missing = REQUIRED_SECTIONS - sections.keys()
    if missing:
        raise PolicyFormatError(f"Policy {path} is missing sections: {', '.join(sorted(missing))}")
    empty = sorted(section for section in REQUIRED_SECTIONS if not sections[section])
    if empty:
        raise PolicyFormatError(
            f"Policy {path} has empty required sections: {', '.join(empty)}"
        )
    return policy, chunks


def load_policy_sources(sources: list[Path]) -> list[tuple[PolicyDocument, list[PolicyChunk]]]:
    parsed: list[tuple[PolicyDocument, list[PolicyChunk]]] = []
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
            policy, chunks = parse_policy(path)
            if policy.id in seen:
                raise PolicyFormatError(
                    f"Duplicate policy ID {policy.id} in {seen[policy.id]} and {path}"
                )
            seen[policy.id] = path
            parsed.append((policy, chunks))
    return sorted(parsed, key=lambda item: item[0].id)


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
