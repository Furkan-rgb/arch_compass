"""Model judgement, questions, conversation, and which model does them.

Everything ArchCompass asks a model for lives here: the verdict on a candidate, the
questions a review comes back with, the grounded answers to a follow-up, and the caching
that stops the same judgement being paid for twice. `model_catalog.py` and
`embedding_models.py` are the two independent selections a workspace makes; `adapters/`
holds LangChain and the provider SDKs, which nothing above it imports.
"""
