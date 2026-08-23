"""Local web presentation adapter.

The HTTP surface and the built frontend it serves. `routes/` holds one module per thing the
API is about and is where a route is found; `app.py` only assembles them. Beside those sit
the three things every route uses — `dependencies.py`, `errors.py`, `schemas.py` — and the
two that decide which workspace a request gets and what a public deployment refuses:
`runtimes.py` and `restrictions.py`. `hosted.py` is the demo's entry point. Read
`routes/reviews.py` first.
"""

from archcompass.presentation.web.app import create_app

__all__ = ["create_app"]
