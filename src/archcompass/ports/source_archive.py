"""How a repository's source is fetched when git is not the way to fetch it.

A second way in, beside `ports.vcs`, rather than a variation on it. The git port makes a
remote's *history* appear on disk and keeps it current; this one makes a remote's *files*
appear on disk, once, and has no notion of a remote afterwards. They are different enough
that folding them together would mean a `GitClient` whose `fetch`, `remote_url`,
`head_commit`, `default_branch` and `force_checkout` all answered "not applicable".

The reason to want the second one is that the first drags git in with it: hooks, submodules,
`.gitattributes` filters, credential helpers, the `file://` and `ssh://` transports, and a
redirect policy of git's own. A public deployment reviewing a stranger's repository wants
none of that, and none of it can be present in a directory that was written by extracting an
archive.

What is lost is the history, and with it the first commit a durable `repo_id` is derived
from. `repositories.lineage` already treats that as an ordinary absence and falls back to the
path, which is what every bundled example does today.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol


@dataclass(frozen=True)
class FetchedSource:
    """Where a fetched repository landed, and what it was fetched from.

    `revision` is whatever the host called the thing it served — a commit sha when the host
    says one, otherwise the ref that was asked for. It is recorded rather than trusted: no
    freshness decision rests on it, because the content fingerprint the analyser computes
    from the files themselves is what every downstream comparison actually uses.
    """

    root_path: Path
    url: str
    revision: str | None


class SourceArchiveFetcher(Protocol):
    """Fetching a repository's files, for a deployment that will not run git."""

    def fetch(self, url: str, *, branch: str | None, destination: Path) -> FetchedSource:
        """Put the repository's files at `destination`, or leave nothing behind.

        `destination` is a directory that does not exist yet. An implementation that fails
        part way is required to remove it: a half-extracted tree that a later call mistakes
        for a complete one is a much worse failure than fetching twice.
        """
        ...
