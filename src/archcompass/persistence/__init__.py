"""Durable workspace state, stored in SQLite.

One repository per aggregate, each implementing a port and owning its own SQL: cases and
reviews and the decisions taken on them, the atlas an analysis produced, the lineage that
says which repository and branch it belongs to, the caches that stop a judgement being paid
for twice. Read `sqlite/database.py` first — it is the connection policy every one of them
shares — then `sqlite/migrations/`, which is the schema's history. `ports.py` is what the
rest of the application sees; nothing above `bootstrap.py` names a class from here.

Deliberately without re-exports. It used to import all fifteen repositories eagerly, which
made `import archcompass.persistence.ports` — a file of protocols, imported by `analysis/`,
`repositories/` and `workflow/`, none of which may touch storage — drag `sqlite3` and every
SQL module in this package along with it. Two modules ever used the front door. They import
what they need directly now, and the port costs what a port should.
"""
