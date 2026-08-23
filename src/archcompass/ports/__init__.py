"""The seams the review graph is sequenced out of.

Two modules, and both are typed purely in domain terms — no feature's records reach in here.
`capabilities.py` is the wider of them and the one to read first: sixteen protocols, one per
meaningful transition of a review, and the reason `workflow/nodes.py` is three lines a node.
`policy_retrieval.py` is the one seam a capability's *result* is stated in.

This package used to hold thirteen modules, of which six were a feature's own interface
hoisted one directory up: a reader of `policies/` had to come here for the index port, and a
reader of `ports/` got git, HTTP archives, conversations and model catalogues in the same
directory. Those live beside what they belong to now — `analysis/ports.py`,
`policies/ports.py`, `reasoning/ports.py`, `repositories/ports.py`, `persistence/ports.py` —
and what is left is one idea rather than two.

Deliberately without re-exports. The old `__init__` published six of forty-three names, which
made it a front door to a sixth of the package and a decision to make on every addition.
Import from the module.
"""
