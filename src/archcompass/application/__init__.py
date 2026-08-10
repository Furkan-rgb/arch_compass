"""Application use cases.

One module per thing a person can ask the workspace to do — index a repository, write a
case, run a review, ask a review a question, triage a boundary — each a service that
composes domain logic over ports and decides nothing about transport or storage. Read
`reviews.py` first: it is the advisory flow end to end, and most of what else is here is
something it calls.
"""
