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

The navigation is the flow (master plan §6B). Primary navigation is three entries: **Home**,
which is the flow, **Policies**, the standing library the judgement reads, and **Reviews**,
the standing record it writes. Cases and repositories are not destinations; they are the
two rails of Home's start step.

**Home** starts a review. The start step presents two order-free rails
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

**Cases are authored in the browser as a form.** The case rail opens a full-width form
whose labels are the questions the fields answer and whose hints say why the answers matter.
The three fields that decide verdicts — `expected_future_changes`, `non_goals`,
`confirmed_facts` — are grouped together and marked as decisive; the rest of the context sits
behind "more", because a form that opens as eleven empty boxes reads as work rather than as
questions. List fields are one entry per line rather than rows of inputs: the entries are
sentences a person writes, edits and pastes in batches, and per-item chrome makes all three
harder.

Every field in those two groups carries **two examples, one that decides something and one
that does not** — "billing moves to a second provider in Q4, the contract is signed" beside
"we might need to support other providers one day". Both, never only the good one: each of
these fields has a plausible-looking answer that settles nothing, and a reader shown only a
good example takes it for a formatting convention and writes the empty answer anyway. The
pair is what lets them see which of the two theirs resembles.

Revising a case opens the same form, prefilled from the stored revision — on the start step
from the selected case, and on the review page from the revision that review was judged
against, which is not necessarily the latest. Submitting writes a new revision; earlier
reviews stay pinned to what they judged.

**YAML remains the escape hatch.** "Paste YAML" creates a case through
`POST /api/cases/import-yaml` — the same route and document the CLI takes — for a case
someone already has in that form, or a field the form does not ask for. A stored case reads
back as that same YAML, with generated identity and empty fields left out, so what is
displayed is what could be pasted back.

The browser validates almost nothing: the form asks for the three fields the domain requires
before submitting, and everything else is the server's judgement. Its message is shown
verbatim — it names the field and what it needed, which is more than a paraphrase could
say.

Repository paths are validated and indexed through the same application service the CLI
uses, and every workspace/repository separation, symlink, traversal and atlas-freshness
rule remains in force.

**Reviews** is the workspace's own record, at `/reviews`. It is grouped by case rather than
listed flat: revising a case and reviewing again is the loop this tool is built around, so
two runs of one case are one history, and read as a flat list they look like unrelated
results with no way to tell a re-run from a review of a changed case. Each row states the
revision it judged and whether anything came out material — "all six earning their place"
and "nothing found to examine" are different results, and only the examined count separates
them. Home keeps a one-line pointer to it, because the way back after a run belongs where
the run ended; the listing itself does not, since it grows without limit and the start step
does not.

So a listing can be read without opening every row, `boundary_reviews` carries the case
title in a column of its own, denormalised from the report exactly as the boundary counts
already are. A review that failed before composing a report has no title to carry, and the
row is rendered by its identifier rather than by a placeholder that would be
indistinguishable from a case actually called that.

Each row can be acted on: a running one carries a **Cancel** control, and every row has an
overflow menu with **Delete**. Both sit outside the row's link rather than inside it — a
button nested in an anchor is neither reliably clickable nor announced as its own control,
and deleting is the last action that should depend on a click landing where the reader
meant it. Delete asks once, in place, with the row still visible behind the question.

`/cases` redirects to Home rather than 404, so bookmarks from the earlier noun-organised
workspace still land somewhere sensible.

## The run

A review runs synchronously inside its request. It is one model call per boundary, so it
takes minutes; there is no job queue and no background worker, because re-running a review
costs nothing that has to be reconciled — the atlas is already indexed and the result is
immutable either way (master plan §18).

The workspace still has to make that wait countable. Detection is deterministic and
complete, so the moment it finishes the run has a known length.

**The wait is drawn as the stages it has**, not as a spinner: sweep the atlas, judge each
boundary, read the verdicts as a set. The three take very different times and fail in
different ways, and a single indeterminate spinner would make a two-minute run
indistinguishable from a hung request. Under the stages, every detected boundary is named,
and each one's verdict appears as it lands — a reader watching their own repository be
judged can see which boundary is under the model right now, and read a verdict before the
page it belongs to exists.

**One place to watch it: the review's own page.** Starting a run goes there immediately —
before the first model call — and the page becomes the review when the run ends. There used
to be two renderings of a run in progress, one on the start step and a thinner one on the
review page, and two renderings of one fact drift until the reader has to work out which to
believe. Now `ReviewInProgress` is the component and that page is the place, whichever way
the run was started: from the start step, from *revise case & review again*, or from another
tab entirely.

It reads from whichever source knows more. The browser holding the stream has the boundary
names and each verdict as it lands; any other browser — a second tab, a reload, a run
started from the CLI — has the counts the run writes to its own record, and the panel says
which of the two it is looking at rather than presenting the thinner one as complete. The
run itself is held above the router, because a run is not a property of any page: it
outlives the one that started it.

**The mechanism: a streamed response.** `POST /api/reviews/stream` runs the same review as
`POST /api/reviews` and answers with newline-delimited JSON — one `ReviewProgress` object
per line: `started` first, carrying the review's identity, then `detected` once with the
count and the boundary names in judgement order, then `judged` per boundary, then
`completed` with the composed review or `failed` with a `ProblemDetail`.

`started` is what makes one place possible. It is sent the moment the run has a record,
which is the first moment it has an identity and everything that could refuse it has passed
— so the client can leave the page it started from and go to the review, which by then
exists and can be opened, reloaded or cancelled from anywhere.

It was chosen over a progress side-channel because progress is a property of the request
doing the work, and streaming is the only option that needs no second place to keep it. A
poll-able progress endpoint would require server-side transient state for a run — a
lifetime, an eviction rule, a key invented by the client — which is the beginning of the
job queue §18 rules out, for a value that stops existing the moment the run ends. Nothing
is shared here beyond a queue that lives as long as the request.

The review still runs in the application service, which owns detection, judgement order and
composition; the route only reports what the service reports through its `on_detected` and
`on_verdict` callbacks. The CLI path is unchanged.

**The review exists while it runs.** Its row is written when the run begins — after the
case, the atlas and its freshness are settled, so a row that exists is a run that could
start — with status `running` and no report. Detection fills in how many boundaries there
are; each verdict moves the count. The Reviews page shows it immediately, *judging 3 of 6*,
and polls only while something is running. Opening it lands on the review's own page, which
waits for its subject and then becomes it: the identifier never changes.

That is not the job queue §18 rules out. Nothing picks work up from this row — the run is
still the work of the request that started it, and the row is only how that request is seen
from elsewhere. What it does buy is that a review is findable during the minutes it takes,
which is the difference between navigating away and losing it.

A run cannot outlive its process, so a row still marked `running` when the workspace starts
belongs to a process that is gone; the web server marks those failed at startup rather than
leaving them saying "in progress" for ever. The one case that gets this wrong — a review
running in another process at that moment — corrects itself, because the process doing the
work writes the real outcome when it finishes.

**A run can be stopped.** `POST /api/reviews/{id}/cancel` marks the record cancelled, and
the record is what stops the run: the service reads it between model calls, so cancelling
takes effect within one call rather than at once — up to a few minutes on a local model.
There is no channel to the thread doing the work, and inventing one would mean shared
mutable state outliving the request that owns it.

`cancelled` is a status of its own, not a flavour of `failed`: a review nobody wanted any
more is not a review that broke, and a listing that coloured them alike would have the
reader looking for a problem that never existed. The verdicts already reached are discarded
— a review is every boundary or none, and half of one would read as a complete answer.
Cancelling writes nothing back afterwards, which is also what leaves the row free to delete
straight away.

**A review can be deleted**, with `DELETE /api/reviews/{id}`, from the overflow menu on its
row. Deleting is not editing: it removes the record rather than leaving one that says
something else, which is what immutability is about. Its question threads go with it — a
thread whose review is gone has nothing to be about, and every answer in it cited boundaries
that no longer exist. A running review is refused with a 409 rather than deleted out from
under its own run; cancel it first, which is the honest order.

Consequences worth stating plainly:

- The run happens on a worker thread so the response can be written while it proceeds. That
  is not background execution: the work is still this request's work, and nothing outlives
  it.
- Once a response has started, its status code can no longer say anything, so a failure
  arrives as a `failed` line carrying the same `ProblemDetail` the non-streaming route would
  have returned. The stream always ends in a verdict about itself.
- Navigating away is safe, and no longer loses sight of the run: it continues, its row
  reports where it has got to, and the review is on the Reviews page when it ends. Leaving
  the review's own page costs only the boundary names, which live in the stream rather than
  in the record. A run that fails records why; nothing is written to the case or the atlas
  either way.
- `POST /api/reviews` stays as the plain contract for a client that wants one request and
  one review with no lines to parse.

## The review page

The review page shows every boundary examined, cleared ones included, each with its
reasoning, the policies that bear on it, and what the detection method could not see. A
box on the same page asks follow-up questions: the whole review goes to the model with
each one, and the answer names the boundaries it rests on. An answer grounded on none of
them is labelled rather than presented as something the review supports.

The page **leads with the conclusion** — what the verdicts amount to when read as a set:
the situation, the themes that run across boundaries, a recommended sequence, and what the
review could not see. It is headed *Conclusion* rather than *Findings*, which the boundaries
below already are: this is the one thing none of those separate calls could produce. Every theme and step carries the boundaries it rests on as links: click
`BR-003` and the page lands on that finding, highlighted. That link is why the overview is
allowed to generalise at all, and it is the shortest path from a claim to its evidence.

Each finding states its verdict in words — *should change* or *earning its place* — as well
as by the colour of its rail, and the policies that bear on it are shown open rather than
folded away. The substantiation is the reason to believe the verdict.

**Question threads are plural and durable.** Many threads may hang off one review; the dock
lists them oldest first, labelled by their first question, with the newest open by default.
A new thread is created when there is finally a question to put in it, so an empty
conversation never appears in a listing.

**An answer reads as it is written.** Where the configured provider can stream — Ollama today,
not yet Google — the prose arrives in fragments and is marked *still being written* until the
appended message lands; where it cannot, the answer simply arrives whole and nothing is marked. A preview carries no
grounding line, because grounding is derived from flags that do not exist until the reply is
complete — and a turn that showed text and then failed is a failed turn in the history, not a
half-answer (ADR 0008).

A **provenance line** states what the review is pinned to — case revision, atlas version,
the number of policies presented to every boundary, the reasoning model, when it ran. All
of it was already in the record; printing it answers the first question a second reading
asks.

**Revise case & review again** is the iterate loop. It opens the *pinned* revision of the
case — not the latest — as the same YAML the editor writes, and says before it is confirmed
what it will do: create the next immutable revision through `PATCH /api/cases/{id}`, then
run a new review against the same atlas, so only the case has changed. The review being read
is never altered; nothing in the workspace edits a review or a revision in place.

**Reviews of one case link to each other**, derived rather than stored: the page lists
`GET /api/reviews?case_id=…` and points at the neighbours either side of itself. A link
recorded at creation time would be a second copy of the same fact, and the earlier review
would have to be edited to hold it — which immutability forbids.

**The review carries its own atlas**, below the verdicts. It is built from the review
outward rather than from the repository inward: each reviewed abstraction is inspected and
its neighbourhood is the map, so what is drawn is where *these* boundaries sit and what
reaches them. A map of the whole repository beside a review would be a second, unrelated
thing on the page.

Each verdict is on its node — amber for a boundary that should change, green for one
examined and found to be earning its place, plain for everything else. A cleared boundary is
deliberately not drawn as an ordinary node: "examined and cleared" and "never looked at" are
different facts, and erasing the difference would undo what an exhaustive sweep is for.
Selecting a node shows its verdict beside the map, where the click was made. It sits after
the findings rather than before them, because "where does this sit" is a question a reader
has only once they know what was decided.

## The atlas explorer

The explorer has no route of its own. `/repositories` is gone and redirects to the flow, so
a bookmark does not 404. The only map is the one inside a review, where a boundary is
already the question being asked (workspace-design §4).

"Show BR-001 in the atlas" is therefore a move within the page, not a navigation: it selects
that boundary's node and scrolls to the map section below. Selection is held by the review
page rather than by the map, so a finding and the map cannot disagree about which node is
the current one.

The interactive `RepositoryAtlas` renders from the freshness-checked node-inspection and
explore APIs. Selecting a node updates its metrics and relationship inspector; hotspot and
contained-complexity states use labels and symbols in addition to colour.

Selecting a node answers where the click was made. It does not write a location hash — that
threw the reader back up to the finding, away from the map they had just started reading —
and it does not re-centre the canvas, which dragged the graph out from under the pointer.
Selections that arrive from anywhere else (search, keyboard, the detail panel, a finding
above) still centre, because those can land on a node that is nowhere in view.

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
pnpm run dev
```

Vite proxies `/api` to the local Python process. `pnpm run build` writes production assets into
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
