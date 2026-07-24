# Local web workspace

Arch Compass includes a single-user browser workspace served from the Python package:

```bash
archcompass web --workspace /path/to/workspace
```

The command initializes missing workspace configuration without overwriting existing files,
binds only to `127.0.0.1`, and serves the packaged React application and FastAPI routes from one
origin. It has no authentication or remote-binding mode.

## Workflow

The interface supports greenfield cases and existing Python repositories through one guided
flow. Users can create a case, import case YAML, or begin from an evaluation-case template.
Repository paths are validated and indexed through the same application service used by the
CLI. All existing workspace/repository separation, symlink, traversal, and atlas-freshness rules
remain in force.

Consultations execute in a single-worker queue so local reasoning providers do not compete for
the same GPU. A run ID and input case revision are fixed when the job is queued. Ordered progress
events are written to SQLite and streamed with server-sent events; reconnecting clients replay
events after their last sequence ID. Jobs left unfinished by a stopped web process are marked
interrupted and are never silently resumed.

The live trace includes stage transitions and validated structured artifacts: design forces,
concern clusters, atlas query plans and result summaries, focused packets, retrieved policies,
concern analyses, alternatives, scenarios, and evidence-repair history. It does not persist or
display hidden chain-of-thought or full prompt payloads.

## Architecture workspace

Completed consultations open as an architecture-analysis workspace rather than a chat transcript.
It keeps the `ArchitectureCase`, design forces, recommendation, policies, classified claim ledger,
alternatives, future-change scenarios, and ADR preview visible around the central analysis surface.
Claim IDs and atlas references remain interactive and open their persisted evidence.

Brownfield consultations render a bounded interactive `RepositoryAtlas` from the nodes, metrics,
relationships, excerpts, and signals persisted in the run's focused evidence packets. Selecting a
node updates its metrics and relationship inspector; hotspot and contained-complexity states use
both labels and symbols in addition to color. The repository library provides the same interaction
against the latest freshness-checked summary, hotspot, and node-inspection APIs.

Atlas placement is deterministic and connection-aware: containment and allocation relationships
establish layers, homogeneous subgraphs use graph distance, and barycentric ordering keeps connected
children close to their parents while reducing crossings. Dense maps support fit-to-view, zoom
controls, native scrolling, click-drag panning, and connection-aware keyboard navigation.

Greenfield consultations never invent repository structure. Their architecture canvas is derived
from recommended responsibilities and conceptual boundaries and labels every node as advisor
inference. Alternatives and future-change scenarios are selectable, the ADR can be copied or
exported, and the advisor composer can append an unresolved question to the immutable case history
and start a new consultation revision.

The interface supports persistent system, light, and dark appearance preferences. Graph colors,
semantic statuses, focus rings, surfaces, and evidence states all use the shared semantic token
layer.

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
document without starting a server. `make check` verifies that the committed declarations are
current.
