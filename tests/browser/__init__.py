"""Checks that drive the built bundle in a real browser.

A package rather than a bare directory so `conftest.py`, the test modules and the
standalone screenshot script can all import the one bootstrap in `harness.py`, the way
`tests/e2e` already does.
"""
