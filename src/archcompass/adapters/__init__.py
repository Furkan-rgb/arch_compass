"""Infrastructure adapters.

Everything that touches the world outside the process, one package per kind: `analysis/`
reads a repository into an atlas, `persistence/` stores what the workspace knows,
`models/` talks to reasoning providers, `retrieval/` parses the policy corpus, `sources/`
and `vcs/` get code onto the machine. Nothing here may import `application/`, and
`tests/unit/test_boundaries.py` is what keeps that true.
"""
