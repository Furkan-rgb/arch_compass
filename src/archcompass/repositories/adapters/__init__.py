"""Adapters that put a repository's files on disk: version control, and archives."""

from archcompass.repositories.adapters.git_cli import GitCommandLineClient
from archcompass.repositories.adapters.https_tarball import HttpsTarballFetcher

__all__ = ["GitCommandLineClient", "HttpsTarballFetcher"]
