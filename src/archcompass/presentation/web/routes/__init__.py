"""One module per thing the API is about, each exposing a `routes()` builder.

`app.py` assembles them and adds nothing of its own beyond middleware, error handlers and
the static files. A module here declares its own request and response models beside the
routes that speak them, because a body is part of what a route is; what more than one of
them needs lives a level up, in `schemas.py`, `dependencies.py` and `errors.py`.

Read `reviews.py` first. It is the flow everything else exists to serve.
"""
