"""Fetching a repository as a gzipped tarball over HTTPS, from hosts named in advance.

The whole point of this adapter is what it cannot do. There is no git binary, so there are
no hooks, no submodules, no `.gitattributes` filters, no credential helper and no ssh agent.
There is no `file://` or `ssh://` transport, because the only scheme this module will build a
request for is `https`. There is no redirect, because redirects are refused rather than
followed. What is left is one GET and one extraction, and the standard library hardens the
extraction.

The address is matched against a whole-string pattern rather than parsed and inspected.
Parsing invites disagreement: `urlsplit`, curl and the average proxy do not agree about
backslashes, `%2f`, empty authorities or embedded control characters, and a check that
passes on one reading of a string while the request is made on another is the shape most
SSRF bugs have. A positive match over the entire input leaves nothing to disagree about —
no userinfo, no port, no query, no fragment, no newline, no `..`.

Because the host is compared literally and never resolved, there is nothing here to rebind:
no name is looked up twice, so there is no window between the check and the connection. That
property is what makes the IP-level defences this module deliberately does not have —
denylists, pinned sockets, an egress proxy — unnecessary rather than missing.
"""

from __future__ import annotations

import re
import shutil
import tarfile
import tempfile
from collections.abc import Iterable
from pathlib import Path

import httpx

from archcompass.domain.errors import RepositoryCheckoutError
from archcompass.ports.source_archive import FetchedSource

#: How each host is asked for a tarball of one ref. Hosts are values in a table rather than a
#: pattern with a wildcard, and this is load-bearing: the moment a suffix match like
#: `*.gitlab.com` is accepted here, an attacker who can register or influence any name under
#: that suffix has an SSRF primitive again, and the no-resolution argument above stops
#: holding. Adding a host means adding a row, deliberately.
ARCHIVE_URLS: dict[str, str] = {
    "github.com": "https://codeload.github.com/{owner}/{repository}/tar.gz/{ref}",
    "gitlab.com": "https://gitlab.com/{owner}/{repository}/-/archive/{ref}/{repository}-{ref}.tar.gz",
    "codeberg.org": "https://codeberg.org/{owner}/{repository}/archive/{ref}.tar.gz",
}

#: What the host serves when no branch was named. Every host in the table above understands
#: it, which is why the default branch never has to be discovered first — there is no second
#: request, and no name for this code to have to trust.
DEFAULT_REF = "HEAD"

#: One path segment of a repository address. Deliberately narrower than what the hosts
#: themselves accept: no percent-encoding, no unicode, nothing that normalises to something
#: else further down.
_SEGMENT = r"[A-Za-z0-9][A-Za-z0-9._-]{0,99}"

#: A branch, when one is asked for. `..` is excluded by the character class rather than by a
#: separate check, and a leading `-` cannot begin one, so the value is safe to interpolate.
_REF = re.compile(r"\A[A-Za-z0-9][A-Za-z0-9._/-]{0,199}\Z")

#: How many entries an archive may contain. A tar of a million empty files costs nothing to
#: serve and is a directory-entry exhaustion attack on the extracting side.
MAX_ENTRIES = 200_000


def address_pattern(hosts: Iterable[str]) -> re.Pattern[str]:
    """The one expression an address has to match, built from the hosts allowed right now.

    Built rather than written out because the allowed set is configuration: a deployment
    narrows it, and the pattern has to be the same rule the fetch will use.
    """

    allowed = "|".join(re.escape(host) for host in sorted(hosts))
    # `\A` and `\Z`, never `^` and `$`: Python's `$` also matches immediately before a
    # trailing newline, so an address ending in one would pass a check the request then
    # made without it. That is the entire bug class this pattern exists to close.
    return re.compile(rf"\Ahttps://({allowed})/({_SEGMENT})/({_SEGMENT})\Z")


class HttpsTarballFetcher:
    """The `SourceArchiveFetcher` port over an HTTPS request for a source archive."""

    def __init__(
        self,
        *,
        hosts: frozenset[str],
        max_bytes: int,
        timeout: int,
    ) -> None:
        unknown = sorted(hosts - ARCHIVE_URLS.keys())
        if unknown:
            raise ValueError(
                f"No archive address is known for {', '.join(unknown)}. Add a row to "
                "ARCHIVE_URLS rather than widening the match."
            )
        self._hosts = hosts
        self._pattern = address_pattern(hosts)
        self._max_bytes = max_bytes
        self._timeout = timeout

    def fetch(self, url: str, *, branch: str | None, destination: Path) -> FetchedSource:
        host, owner, repository = self._validated(url)
        ref = self._validated_ref(branch)
        archive = ARCHIVE_URLS[host].format(owner=owner, repository=repository, ref=ref)
        # A directory of its own, alongside the destination rather than inside it, so that
        # nothing half-written is ever visible at the path a caller was handed.
        staging = Path(tempfile.mkdtemp(prefix=".fetch-", dir=destination.parent))
        try:
            downloaded = self._download(archive, staging / "source.tar.gz")
            extracted = self._extract(downloaded, staging / "tree")
            revision = _revision_of(extracted.name, repository)
            extracted.rename(destination)
        except BaseException:
            shutil.rmtree(staging, ignore_errors=True)
            raise
        shutil.rmtree(staging, ignore_errors=True)
        return FetchedSource(root_path=destination, url=url, revision=revision)

    def _validated(self, url: str) -> tuple[str, str, str]:
        matched = self._pattern.match(url)
        if matched is None:
            allowed = ", ".join(sorted(self._hosts))
            raise RepositoryCheckoutError(
                f"{url!r} is not an address this workspace will fetch. It reads public "
                f"repositories over https from {allowed}, in the form "
                "https://github.com/owner/repository."
            )
        # `owner/repository.git` is the form people copy out of a clone button, and the
        # segment pattern already accepted the suffix as part of the name. Dropped here
        # rather than in the pattern, where an optional group would also have made the
        # repository name itself optional.
        repository = matched.group(3)
        return matched.group(1), matched.group(2), repository.removesuffix(".git")

    def _validated_ref(self, branch: str | None) -> str:
        named = (branch or "").strip()
        if not named:
            return DEFAULT_REF
        if not _REF.match(named) or ".." in named:
            raise RepositoryCheckoutError(f"{named!r} is not a branch name.")
        return named

    def _download(self, archive: str, into: Path) -> Path:
        """Stream the archive to disk, giving up the moment it is too big.

        Counted while it arrives rather than measured afterwards. On a deployment whose
        writable filesystem is memory — which is what a container's `/tmp` usually is — a
        file that has finished being written has already cost what the cap existed to
        prevent, and checking its size then is checking after the damage.

        `Content-Length` is not consulted: a server that wants to send more than it declared
        can, so the running total is the only number worth believing.
        """

        written = 0
        try:
            with httpx.stream(
                "GET",
                archive,
                timeout=self._timeout,
                # Refused, not re-validated. A redirect is the host proposing a different
                # address, and the whole argument for this module is that the address was
                # decided before the request rather than during it.
                follow_redirects=False,
                headers={"accept": "application/x-gzip"},
            ) as response:
                # Exactly 200. Anything else is the host declining, and with redirects off
                # that includes the 3xx it would have used to send us somewhere else.
                if response.status_code != httpx.codes.OK.value:
                    raise RepositoryCheckoutError(_unavailable(archive, response.status_code))
                with into.open("wb") as sink:
                    for chunk in response.iter_bytes():
                        written += len(chunk)
                        if written > self._max_bytes:
                            raise RepositoryCheckoutError(
                                f"This repository is larger than this workspace will fetch "
                                f"({self._max_bytes // (1024 * 1024)} MB)."
                            )
                        sink.write(chunk)
        except httpx.HTTPError as error:
            raise RepositoryCheckoutError(
                f"{archive} could not be reached. It may not exist, or it may not be public."
            ) from error
        return into

    def _extract(self, archive: Path, into: Path) -> Path:
        """Unpack the archive and answer with the single directory it contained.

        Two things are checked that the archive itself asserts: the total size of the members
        and how many there are. Compression hides both — a few hundred kilobytes on the wire
        expands to whatever the sender chose — so the cap the download enforced has to be
        enforced again over what the members declare, before any of it is written.

        Everything else is `tarfile`'s `data` filter, which refuses absolute paths, `..`
        components, symlinks, hard links, device nodes and setuid bits. It is the standard
        library's own statement of what is safe to extract from an untrusted archive, and
        re-deriving it here by hand would only be a second, worse copy.
        """

        into.mkdir(parents=True)
        try:
            # `r:gz` rather than `r:*`: gzip is what the hosts serve, and accepting whatever
            # the bytes turn out to be would accept bzip2 and xz too, whose expansion ratios
            # are far higher for the same bytes on the wire.
            with tarfile.open(archive, mode="r:gz") as tar:
                declared = 0
                for entries, member in enumerate(tar, start=1):
                    if entries > MAX_ENTRIES:
                        raise RepositoryCheckoutError(
                            f"This repository has more than {MAX_ENTRIES} files in it."
                        )
                    declared += member.size
                    if declared > self._max_bytes:
                        raise RepositoryCheckoutError(
                            f"This repository unpacks to more than this workspace will hold "
                            f"({self._max_bytes // (1024 * 1024)} MB)."
                        )
                tar.extractall(into, filter="data")
        except tarfile.TarError as error:
            raise RepositoryCheckoutError(
                "The archive this address served could not be read as a source tarball."
            ) from error
        return _single_directory(into)


def _single_directory(extracted: Path) -> Path:
    """The one directory a source tarball holds, which is the repository itself.

    Every host in the table wraps the tree in a directory named after the repository and the
    revision, so unwrapping it is what makes the result the same shape a checkout would have
    been. An archive shaped any other way is not one of theirs.
    """

    entries = list(extracted.iterdir())
    if len(entries) != 1 or not entries[0].is_dir():
        raise RepositoryCheckoutError(
            "The archive this address served is not laid out like a source tarball."
        )
    return entries[0]


def _revision_of(directory: str, repository: str) -> str | None:
    """What the host says it served, read out of the name of the directory it wrapped.

    Every host in the table names that directory after the repository and the revision, so
    the revision is what is left when the repository's name and the separator are taken off
    the front. Read rather than asked for, because asking would be a second request to a
    host that already answered.

    `None` when the name is not that shape. A repository that cannot say which commit it is
    can still be reviewed; it just cannot be fetched again later and be guaranteed to be the
    same code, and the caller is told that by the absence rather than by a value invented
    for it.
    """

    prefix = f"{repository}-"
    if not directory.startswith(prefix):
        return None
    return directory[len(prefix) :] or None


def _unavailable(archive: str, status: int) -> str:
    if status in {httpx.codes.NOT_FOUND, httpx.codes.FORBIDDEN}:
        return (
            f"{archive} was not found. This workspace reads public repositories only, so a "
            "private one answers the same way as one that does not exist."
        )
    if status in {httpx.codes.MOVED_PERMANENTLY, httpx.codes.FOUND}:
        return (
            f"{archive} answered with a redirect, which is not followed. The repository may "
            "have been renamed or moved."
        )
    return f"{archive} answered {status}."
