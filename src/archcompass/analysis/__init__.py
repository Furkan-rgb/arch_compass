"""Deterministic repository understanding.

What ArchCompass can say about a repository without asking a model: the atlas (`atlas.py`),
the metrics read off it (`metrics.py`), the structural detectors that turn it into review
candidates (`detectors.py`), what changed since the last review (`delta.py`), and the
queries an interface asks of it (`queries.py`). `adapters/` holds the Python AST parser and
the optional type oracle; nothing above it needs to know how a file was read.
"""
