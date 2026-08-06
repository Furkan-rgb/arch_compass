"""Adapters that make a repository's files appear on disk without version control."""

from archcompass.adapters.sources.https_tarball import HttpsTarballFetcher

__all__ = ["HttpsTarballFetcher"]
