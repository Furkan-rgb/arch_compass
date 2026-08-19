"""The policy corpus and the retrieval that selects from it.

`general/` is the corpus ArchCompass ships. `service.py` is where a corpus comes from —
Markdown sources, registered and read — and `corpus.py` presents it to the review graph.
`retrieval.py` is the strategy-independent selection contract, `evaluation.py` scores an
implementation of it, and `adapters/` holds the Markdown parser and the dense index.
"""
