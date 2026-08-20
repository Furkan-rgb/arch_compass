# The hosted demo, built in one place: the bundle and the server that serves it are one
# deployment and are only correct together, so the image builds both rather than trusting a
# `static/` directory that happened to be on the machine.

FROM node:22-slim AS frontend
WORKDIR /app
RUN corepack enable
# Manifest first, so a change to a component does not re-resolve the dependency tree.
# `pnpm-workspace.yaml` comes with it: it is where pnpm 10+ keeps its settings, and the one
# install script this project allows is named in it.
COPY frontend/package.json frontend/pnpm-lock.yaml frontend/pnpm-workspace.yaml frontend/
RUN cd frontend && pnpm install --frozen-lockfile
COPY frontend/ frontend/
# Vite writes into ../src/archcompass/presentation/web/static, which is where the server
# looks. The path is the frontend's own configuration, not something this file chooses.
RUN cd frontend && pnpm run build

FROM python:3.12-slim AS runtime
COPY --from=ghcr.io/astral-sh/uv:0.8 /uv /usr/local/bin/uv
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never
WORKDIR /app
COPY pyproject.toml uv.lock README.md ./
COPY src/ src/
# Locked and without the dev group: the image runs the server, and pyright, pytest and
# playwright have no business in it. The project itself is installed from `src/` in place,
# which is what lets the two directories copied below be found at run time — the example
# repositories and the built bundle are both located relative to the package's own file.
# `--extra resolution` installs mypy, which the analyzer asks for typed edges: structural
# protocol conformance judged by a type checker rather than guessed from names. The hosted
# demo is the one place a visitor sees the atlas without choosing what went into it, so it
# gets the better edges. Absent, indexing still works and the edges are the parser's own.
RUN uv sync --frozen --no-dev --extra resolution
COPY examples/cases/ examples/cases/
COPY --from=frontend /app/src/archcompass/presentation/web/static/ \
    src/archcompass/presentation/web/static/

RUN useradd --create-home --uid 1001 archcompass && chown -R archcompass:archcompass /app
USER archcompass
ENV PATH="/app/.venv/bin:${PATH}" \
    PORT=8080 \
    ARCHCOMPASS_HOSTED=1
EXPOSE 8080
# Shell form because Cloud Run hands the port in as an environment variable, and a factory
# rather than a module attribute because the application refuses to be built at all when the
# deployment is misconfigured — that has to be a startup failure with a message, not an
# import-time traceback from somewhere inside uvicorn's loader.
CMD ["sh", "-c", "uvicorn archcompass.presentation.web.hosted:create_hosted_app --factory --host 0.0.0.0 --port ${PORT}"]
