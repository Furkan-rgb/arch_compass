"""The SQLite plumbing every repository in this package shares.

`database.py` is the connection policy (WAL, a busy timeout, a connection per call),
`codecs.py` and `records.py` the encode/decode boundary between frozen domain snapshots and
stored JSON, and `migrations/` the schema's history — the only place it changes.
"""
