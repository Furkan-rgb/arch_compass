# Local web workspace

Arch Compass includes a single-user browser workspace served from the Python package:

```bash
archcompass web
```

The current directory is the default workspace. Use
`archcompass web --workspace /path/to/workspace` to override it. The command initializes missing
workspace configuration without overwriting existing files,
binds only to `127.0.0.1`, and serves the packaged React application and FastAPI routes from one
origin. It has no authentication or remote-binding mode.

## Workflow

The interface supports one flow: pick a repository to review and read the result.

A **bundled example** is the shortest path — each ships a written case and a repository to
run it against, so a new workspace can produce a real review without a case being written
first. Loading one indexes the repository and creates the case in a single step.

Repository paths are validated and indexed through the same application service the CLI
uses, and every workspace/repository separation, symlink, traversal and atlas-freshness
rule remains in force.

A review runs synchronously inside its request. It is one model call per boundary, so it
takes minutes; there is no job queue and no progress stream, because re-running a review
costs nothing that has to be reconciled — the atlas is already indexed and the result is
immutable either way.

The review page shows every boundary examined, cleared ones included, each with its
reasoning, the policies that bear on it, and what the detection method could not see. A
box on the same page asks follow-up questions: the whole review goes to the model with
each one, and the answer names the boundaries it rests on. An answer grounded on none of
them is labelled rather than presented as something the review supports.

The atlas graph is served separately under **Repositories** and reads the indexed atlas
directly, so it needs no review to have been run.

## The atlas explorer

The interactive `RepositoryAtlas` renders from the latest freshness-checked summary,
hotspot and node-inspection APIs. Selecting a node updates its metrics and relationship
inspector; hotspot and contained-complexity states use labels and symbols in addition to
colour. It reads the indexed atlas directly and is independent of whether any review has
been run.

Atlas placement is deterministic and connection-aware: containment and allocation relationships
establish layers, homogeneous subgraphs use graph distance, and barycentric ordering keeps connected
children close to their parents while reducing crossings. Dense maps support fit-to-view, zoom
controls, native scrolling, click-drag panning, a recenterable minimap, and connection-aware
keyboard navigation. Trackpad and two-pointer pinch gestures zoom around the gesture location
inside the atlas without taking over browser zoom elsewhere on the page.

Visible nodes are arranged as architecture clusters rather than a single rigid rank grid.
Structure clusters follow top-level containment ownership, while dependency and risk clusters use
deterministic graph-distance seeds chosen from connected hubs and hotspots. A bounded relaxation
pass combines link attraction, cluster gravity, weak hierarchy constraints, repulsion, and final
rectangle collision resolution. The result remains reproducible across refreshes while allowing
connected areas to form more natural islands. Subtle labelled cluster regions make those
communities explicit without implying boundaries that are absent from the persisted evidence. A
final geometric separation pass keeps island bounds apart even when cross-cluster dependencies
pull their nodes together.

Fit-to-view and fullscreen are separate controls. Fullscreen expands the atlas and its inspector
to the available viewport, then refits the visible graph; browsers without the Fullscreen API use
an equivalent fixed-viewport fallback. Clicking empty canvas space clears the current node
selection, while node clicks, pinch gestures, and drag-panning do not.

Repository atlases provide separate structure, dependency, and risk lenses so containment is not
conflated with imports and calls. Relationship types can be filtered independently and use
distinct line treatments for imports, calls, inheritance, implementation, tests, and configuration.
Search falls back to the persisted atlas when a node is outside the current bounded view. From a
selected node, users can progressively add descendants, dependencies, dependants, or a two-hop
neighbourhood without loading the entire repository. Incoming and outgoing relationships remain
separate in the inspector, and any two surfaced nodes can be used to trace and highlight the
shortest known dependency path. Every expansion is freshness-checked through application-level
atlas operations.

The interface supports persistent system, light, and dark appearance preferences. Graph colors,
semantic statuses, focus rings, surfaces, and evidence states all use the shared semantic token
layer.

The typography system maintains a 13–15px working range for normal interface text, reserves
11–12px only for short metadata and identifiers, and uses a relaxed reading line-height for
reports and policy content. Inputs, tabs, graph controls, disclosure rows, and primary actions use
larger keyboard and pointer targets. Atlas nodes and inspectors scale independently from dense
repository metadata, while long-form reports use a narrower line length for comfortable reading.

## Frontend development

The React, TypeScript, and Vite source lives in `frontend/`. During development, run the Python
workspace on port 8765 and Vite on port 5173:

```bash
archcompass web --no-open
cd frontend
npm run dev
```

Vite proxies `/api` to the local Python process. `npm run build` writes production assets into
the Python presentation package so an installed wheel does not require Node.

FastAPI owns the browser API contract. Run `make api-types` after changing a web route or response
model; it regenerates `frontend/src/openapi.generated.ts` directly from the application OpenAPI
document without starting a server. Every operation documents runtime request-validation failures
with `ProblemDetail` rather than FastAPI's unused default error shape. Review-conversation routes
reuse that schema for 404 not-found, 409 state-conflict, 422 request/evidence-validation, and 503
provider-unavailable responses. A missing review is a 404 rather than a generic persistence
failure.

The active frontend error path aliases the generated `ProblemDetail` contract, and the case,
review and conversation response types are aliases of it rather than hand-maintained copies.
`make check` verifies that the committed OpenAPI declarations are current, and that the committed
bundle under `presentation/web/static` still matches `frontend/`.
