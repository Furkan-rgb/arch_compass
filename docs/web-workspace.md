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

The navigation is the flow (master plan §6B). Primary navigation is two entries: **Home**,
which is the flow, and **Policies**, the standing library it reads. Cases and repositories
are not destinations; they are the two rails of Home's start step.

**Home** starts a review and lists past ones. The start step presents two order-free rails
— the repository to examine and the case to judge it against — converging on one Run
button that enables when both are filled. A case that names an indexed repository fills the
repository rail too; a case naming an unindexed path offers that path to the index field
rather than selecting it, because indexing is an action with its own failure modes. A
single indexed repository is pre-selected: the atlas is substrate (§9.2) and one candidate
is not a choice. The case is never pre-selected however few exist, because it is the input
that decides the answer.

A **bundled example** fills both rails in one click — each ships a written case and a
repository to run it against, so a new workspace can produce a real review without a case
being written first. Loading one indexes the repository and creates the case in a single
step, then leaves the run to the user.

**Cases are authored in the browser as YAML.** The case rail opens a full-width editor
pre-filled with a commented skeleton, and creates the case through
`POST /api/cases/import-yaml` — the same route and the same document the CLI takes, so the
two surfaces author the same thing. YAML rather than a form because the fields that decide
verdicts (`expected_future_changes`, `non_goals`, `confirmed_facts`) are prose with
structure, which is exactly what a form flattens; a structured form can follow beside it.

The browser checks syntax and nothing else. What a case must contain is the domain's rule,
and the server's validation message is shown verbatim: it names the field and what it
needed, which is more than a paraphrase could say. A created case is selected in the rail
immediately, and a selected case can be read back — rendered as the same YAML it was
written in, with generated identity and empty fields left out, so what is displayed is what
could be pasted back into the editor.

Repository paths are validated and indexed through the same application service the CLI
uses, and every workspace/repository separation, symlink, traversal and atlas-freshness
rule remains in force.

`/reviews` and `/cases` redirect to Home rather than 404, so bookmarks from the earlier
noun-organised workspace still land somewhere sensible.

## The run

A review runs synchronously inside its request. It is one model call per boundary, so it
takes minutes; there is no job queue and no background worker, because re-running a review
costs nothing that has to be reconciled — the atlas is already indexed and the result is
immutable either way (master plan §18).

The workspace still has to make that wait countable. Detection is deterministic and
complete, so the moment it finishes the run has a known length, and the browser shows
*judging boundary k of n* with the boundary under judgement named.

**The mechanism: a streamed response.** `POST /api/reviews/stream` runs the same review as
`POST /api/reviews` and answers with newline-delimited JSON — one `ReviewProgress` object
per line: `detected` once, carrying the count and the boundary names in judgement order,
then `judged` per boundary, then `completed` with the composed review or `failed` with a
`ProblemDetail`.

It was chosen over a progress side-channel because progress is a property of the request
doing the work, and streaming is the only option that needs no second place to keep it. A
poll-able progress endpoint would require server-side transient state for a run — a
lifetime, an eviction rule, a key invented by the client — which is the beginning of the
job queue §18 rules out, for a value that stops existing the moment the run ends. Nothing
is shared here beyond a queue that lives as long as the request.

The review still runs in the application service, which owns detection, judgement order and
composition; the route only reports what the service reports through its `on_detected` and
`on_verdict` callbacks. The CLI path is unchanged.

Consequences worth stating plainly:

- The run happens on a worker thread so the response can be written while it proceeds. That
  is not background execution: the work is still this request's work, and nothing outlives
  it.
- Once a response has started, its status code can no longer say anything, so a failure
  arrives as a `failed` line carrying the same `ProblemDetail` the non-streaming route would
  have returned. The stream always ends in a verdict about itself.
- Navigating away is safe. A review is persisted once, composed, at the end: leaving mid-run
  means the run finishes or fails on its own and either a whole review exists afterwards or
  none does — the same two outcomes as before.
- `POST /api/reviews` stays as the plain contract for a client that wants one request and
  one review with no lines to parse.

The review page shows every boundary examined, cleared ones included, each with its
reasoning, the policies that bear on it, and what the detection method could not see. A
box on the same page asks follow-up questions: the whole review goes to the model with
each one, and the answer names the boundaries it rests on. An answer grounded on none of
them is labelled rather than presented as something the review supports.

## The atlas explorer

The graph explorer keeps its route at `/repositories` and has left the navigation. It is
entered from the repository rail — "explore this atlas", carrying the chosen root as
`?root=` — so it opens on the repository the flow is pointed at rather than on whichever
was indexed last. It will re-enter the flow properly as an evidence drill-down from a
finding (workspace-design §4); until then it stays routed, tested and reachable rather than
rotting unrouted. It reads the indexed atlas directly, so it needs no review to have been
run.

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
