> **Half superseded.** Sections 1–12 describe a two-pane sidebar interface that was
> replaced; they are kept for the reasoning, not as a plan. Sections 13 onward describe
> backend behaviour and are mostly still read. Where this file and the code disagree, the
> code is right — the retry schedule is one place they do, and **§14 and §17 describe the
> Google Batch path, which was deleted**: there is no batch judging, no batch refusal and
> no `review_candidates` node any more.

# Frontend rebuild plan

Derived from `docs/todo-frontend.md` (the master brief) and `docs/frontend-mockup.md` (UX
ideas only, not a visual template). The backend, its routes, and the generated OpenAPI types
are fixed; everything above `src/api` is rebuilt.

## 1. Audit of what exists today

| Problem | Where |
| --- | --- |
| One 91-line `ui.tsx` holding every primitive, each a single unwrapped JSX line | `components/ui.tsx` |
| Findings rendered as a flat list of long cards — no queue, no triage, no way to see what needs a human | `components/findings-panel.tsx` |
| Review page is seven sibling tabs; evidence, policies and provenance are separate destinations rather than context beside the finding | `pages/ReviewPage.tsx` |
| Everything is one column at every breakpoint; "responsive" is a shrunken desktop | all pages |
| No landing surface at all — `/` redirects into the app | `App.tsx` |
| Start page is a settings form: a bare path input with no picker, no example integration beyond a button | `pages/StartPage.tsx` |
| Repositories show node/edge counts only — no branch, no commit, no indexed time, no latest review | `pages/RepositoriesPage.tsx` |
| Policies cannot be edited even though `PUT /api/policies/{id}` exists; no scope filter; body Markdown rendered inside a `text-sm` wrapper that fights the renderer | `pages/PoliciesPage.tsx` |
| Model settings do not explain what each model *does*, and the pinned state is a footnote | `pages/SettingsPage.tsx` |
| Dark mode only via `prefers-color-scheme`, though `index.html` already stamps `data-theme` and expects a `theme.ts` that was never written | `styles.css`, `index.html` |
| No motion, no skeletons, no reveals, no focus-visible system, no skip link, no reduced-motion path | everywhere |
| Unused backend capability: directory browser, repository re-index/refresh, hotspots, node inspect, folder tree, policy update, decision history, bulk decisions | `api.ts` |

## 2. Design direction

**Serious engineering review workbench.** Warm-neutral paper canvas, near-black ink, one
restrained indigo accent, and a three-colour verdict system (material / held / cleared) that
never carries meaning by colour alone — every verdict also has a glyph and a word.

- Typography: Schibsted Grotesk for display, Instrument Sans for UI, system mono for every
  identifier, path, commit, fingerprint and model identity.
- Surfaces: 1px rules over shadows; shadows only for genuinely floating things (drawers,
  popovers, the landing preview). Radii 6/10/14 — no giant pills.
- Gradient: one, in the landing hero and the brand mark. Nowhere in the workbench.
- Motion: 150–420ms, ease-out, transform + opacity only. Scroll reveals on the landing page,
  staggered list entrances in the app, drawer slides, expansion transitions, skeleton
  shimmer. All of it behind `prefers-reduced-motion`.

## 3. Component system

Small composable pieces under `src/ui/`, one semantic role each, no boolean-prop monsters:

`button` · `badge` (Status / Verdict / Strength) · `panel` (Panel, PanelHeader, PanelBody,
PanelFooter) · `field` (Field, Input, Textarea, Select, Search) · `tabs` · `drawer` ·
`dialog` · `states` (Loading, Skeleton, ErrorNotice, EmptyState) · `page-header` · `meta`
(MetaRow, MetaItem, Mono, PathRef) · `code` (CodeBlock, EvidenceExcerpt) · `markdown` ·
`timeline` · `reveal` (IntersectionObserver + reduced motion) · `toast`.

Shared logic in `src/lib/`: `cn`, `format` (relative time, path shortening, verdict and
status vocabulary), `theme` (light/dark/system, matching the pre-paint script in
`index.html`), `motion`.

## 4. Information architecture

```
Landing  /                    marketing + product, integrated with the app shell's language
Start    /start               guided review launch
Reviews  /reviews /reviews/:id  history → workbench
Repos    /repositories        indexed atlases, freshness, actions
Cases    /cases               architecture context and its revisions
Policies /policies            corpus, search, authoring
Models   /settings            reasoning vs embedding
```

The workbench is the product surface, and it is laid out as:

- **left rail** — attention queue (findings ordered by what needs a human), plus revision
  lineage;
- **centre** — the selected finding as a structured assessment, or the clarification round
  when the review is waiting;
- **right rail** — judgement context in tabs: case, policies, evidence, provenance.

On tablet the right rail becomes a drawer; on mobile the three panes become a stacked view
with a sticky action bar and bottom-sheet context.

## 5. Order of work

1. Tokens, `styles.css`, theme module, motion utilities.
2. `src/lib` and `src/ui` primitives.
3. App shell: sidebar, workspace context, model chips, mobile drawer, skip link.
4. Review workbench (queue, finding, context rail, clarification, delta, decisions).
5. Policies, Cases, Repositories, Reviews, Start, Settings.
6. Landing page.
7. Motion and polish.
8. Tests: vitest component/unit suite, then the Playwright end-to-end run against a real
   server and a real browser.

## 6. Success criterion

A staff engineer opening this should see a review workbench they trust: deterministic
analysis, auditable retrieval, structured judgement, revisioned reviews, and human decisions
kept visibly separate from model output.

## 7. What was built

Every page was rewritten. The old component set was replaced rather than adapted, so no
component from the previous frontend survives and nothing dead was left behind.

**Design system.** Tokens in `frontend/src/styles.css`: a warm neutral canvas (`#f7f6f3`,
`#0d0e0c` dark), one accent, and three verdict tones. `frontend/src/lib/format.ts` holds the
product vocabulary — a verdict is `{label, tone, glyph}`, so *material ▲*, *held ◆* and
*cleared ●* each carry a word and a shape and never rely on colour alone. Primitives live in
`frontend/src/ui/`: button, badge, panel, field, tabs, drawer, states, meta, code, markdown,
page, reveal, timeline. They are small and composable — `Panel` + `PanelHeader` + `PanelBody`
rather than one panel with a dozen booleans.

**Pages.** Landing (`/`) is one route with the app shell's own language rather than a
separate marketing skin. Start is three numbered steps with a filesystem browser, a clone
form and examples. The workbench is the three-pane layout above. Policies gained an editor
that scaffolds and validates the document shape the workspace requires. Repositories, Cases,
Reviews and Models were rebuilt on the same primitives.

**Responsive.** The workbench genuinely changes structure by width — three panes ≥1280px,
two panes with a context drawer ≥1024px, and a single column with a bottom sheet below that,
decided in `frontend/src/lib/media.ts` rather than by hiding shrunken desktop panes. Tabs
scroll horizontally; the sidebar becomes a focus-trapped drawer.

**Accessibility.** Skip link to `<main>`; roving arrow-key focus in tabs; `Drawer` traps
focus, closes on Escape and locks body scroll; every input is labelled through `Field`'s
`useId`; mutations announce through a live region; verdicts carry text and glyph; all motion
is behind `prefers-reduced-motion`.

## 8. Results

| Check | Result |
| --- | --- |
| `tsc -b` | clean |
| `vitest run` | 60 passing, 10 files |
| `pnpm run build` | clean, routes code-split per page |
| `pytest -m browser` | 4 passing against a real uvicorn server and a real Chromium |
| `make check` | ruff clean, pyright 0 errors, 351 backend tests, OpenAPI types in sync |

Three defects were found by reading screenshots of the running app rather than by tests: an
unlayered `button { color: inherit }` that outranked every Tailwind text-colour utility and
made selected tab labels invisible; a repository path chip overflowing a 390px viewport; and
an Atlas panel reporting a capped query's page length (30/30/30) as if it were the atlas
total (54/130/46).

## 9. Backend limitations found, and not worked around

- **Policy documents must carry nine `##` sections.** The workspace re-reads a saved policy
  with the same Markdown parser it uses for the bundled corpus, which rejects a file missing
  any of *Intent, Guidance, Signals, Diagnostic questions, Likely consequences, Exceptions,
  Positive example, Counterexample, Related policies*. The old form accepted any prose and
  failed on save. The editor now scaffolds those sections and shows which are outstanding;
  `frontend/src/features/policies/sections.test.ts` reads `REQUIRED_SECTIONS` out of
  `src/archcompass/policies/adapters/markdown.py` so the two cannot drift apart.
- **The atlas overview query is capped.** `AtlasQueryResult` returns at most `limit` (30)
  nodes, relationships and signals, so its arrays cannot be counted as totals. The indexer's
  recorded counts are used instead.
- **A review's questions are answered as a round, not individually.** There is no endpoint
  for a single answer, so the clarification is a form that submits once, with an explicit
  skip per question.

No backend file was changed. The only file touched outside `frontend/` is
`tests/browser/test_workspace.py`, the end-to-end suite.


---

# Second pass

Three things were wrong with the first pass, and one thing was wrong underneath it.

## 10. The rail could be wider than its column

Reported as "the attention queue is wide so there is horizontal scroll", and reproducible
once a real repository was used instead of the example one. The queue's scroller is
`overflow-y-auto`, and CSS resolves `overflow-x` to `auto` alongside it — a scroller is a
scroller in both directions. Nothing in a row broke a dotted identifier, so one realistic
name took the content from **266px to 651px inside a 266px box**. The example repository's
names are `ports.Clock`, which is why nothing caught it.

The same bug had a second instance: the sidebar's workspace path is `truncate`d, which sets
`white-space: nowrap` and therefore makes the element's min-content width the whole string —
so a grid ancestor left at its default `min-width: auto` was widened by the very thing the
truncation was meant to hide.

It is fixed as an invariant rather than in two places:

- `min-width: 0` on every grid and flex child that carries text;
- `overflow-wrap: anywhere` on identifiers, so a name wraps rather than pushes;
- `overflow-x: clip` on vertical scrollers, so the pair cannot resolve to `auto`;
- `frontend/src/features/review/overflow.test.tsx`, which renders a 90-character identifier
  and a deep workspace path and asserts the properties that make the pixels impossible.

Measured after the change in Chromium at 1440px, with a hostile identifier injected into
every row: queue `scrollWidth` 302 against `clientWidth` 302, sidebar 231 against 231.

## 11. The middle column was the smallest thing on screen

Three panes at 1440 left the finding — the only part anyone reads — with about 500px, while
two rails held 650 between them. The workbench is now **two panes**, and the context rail is
dissolved into the *margin of the document*: the case goal sits beside "why this matters",
the measurements beside the involved code, the retrieval counts beside the policies. A
citation belongs next to what it supports, not in a third column to be correlated by eye.

- Reading column at a 62-character measure; margin notes at 15rem.
- Evidence rows span both columns, because prose wants a measure and code wants width.
- The queue can be hidden once you are working down the list rather than choosing from it.
- The four-statistic panel is one divided ribbon line, giving back about 120px above the
  work.
- Below the two-pane breakpoint the margin notes stack under the prose, and the context is
  still reachable as a drawer.

## 12. A coloured selection reads as a grade

In this interface a hue states a judgement, so tinting the selected row said "this one
passed" as loudly as it said "you are here". Selection is now an ink bar and a change of
surface — weight and position, not colour — in the queue and in the sidebar alike. The
palette itself is unchanged.

## 13. Underneath: a review was owned by a browser tab

`StartPage` held the whole review inside one streaming HTTP response and only navigated when
it ended. Reloading aborted the fetch, which closed the server's generator mid-iteration —
so a refresh did not merely lose the page, it abandoned the run.

A review is now a record before it is a request:

- `POST /api/reviews/runs` starts it and answers `202` with a run id immediately;
- `GET /api/reviews/runs/{id}` reports status, stage and the review id as soon as one exists;
- `ReviewRunner` (`src/archcompass/workflow/runs.py`) owns the thread; the durable status
  comes from the execution store, so it survives a restart, while the live stage does not
  pretend to;
- the browser goes to `/runs/:id`, watches, and hands over to `/reviews/:id`.

The end-to-end suite reloads the page mid-run and asserts the run is still there.

## 14. Batch judging

Interactive free tiers meter per minute, and a review asks for one judgement per candidate as
fast as the graph produces them — which is how a review that has already spent minutes
indexing fails on its fourth verdict. Judging is a pure fan-out, so the whole stage is one
submission.

- `BatchArchitectureJudge` is a capability asked at dispatch time, not at build time: which
  model is selected changes while the workspace runs.
- `_dispatch_candidates` routes to `review_candidates` when the selected judge can batch, and
  keeps the existing per-candidate fan-out when it cannot. Ollama and the deterministic
  provider are untouched.
- `GoogleBatchJudge` submits every candidate with the same prompt and the same
  `response_schema` the interactive path validates against — shared functions, not restated
  ones, so a batched judgement cannot become a different judgement.
- The caching judge submits only what it has not already judged, and stitches the answers
  back into the caller's order.
- A partial batch is refused rather than composed, because a missing verdict would read as a
  cleared one.
- Half price, and a quota separate from the interactive one.

The cost is synchrony: a batch is guaranteed within 24 hours and usually much faster. That is
only acceptable because of §13 — the run no longer lives in a request. The run page says so
plainly rather than showing a spinner that never stops.

## 15. Rate limits, before batching helps

`archcompass.retrying` retries a call the provider itself describes as temporary — 429 and
the 5xx family — honouring Google's own `retryDelay` when it names one. The schedule has
since grown: `RetryPolicy` now defaults to **5 retries** from 4s, doubling, capped at 60s a
wait — about two minutes in total, so a per-minute quota window has fully closed before it
gives up. `retrying.py` is the number; this paragraph is not. A 400, 401, 403, 404 or a timeout raises immediately. Exhausted retries
raise `ProviderError`, which the API already reports as 503 and retryable. Applied at the two
choke points every provider call passes through: the structured reasoning call and both
embedding calls.

Also fixed: `gemini-3.5-flash-lite` and `gemini-3.6-flash` fix their own sampling, so passing
`temperature` was discarded and warned about on every call. It is now sent only to models
that honour it.

## 16. Results

| Check | Result |
| --- | --- |
| `make check` | ruff clean, pyright 0 errors, 384 backend tests, OpenAPI types in sync |
| `vitest run` | 65 passing, 11 files |
| `pnpm run build` | clean |
| `pytest -m browser` | 4 passing, including a reload mid-run |

## 17. Batching the corpus too, and what happens when the key is refused

Embedding the corpus is the other bulk job with nobody waiting on it — 486 chunks against a
per-minute limit — so where the provider offers an embedding batch, the whole corpus goes in
one submission. `embed_query` stays interactive: a search embeds one text to answer a
retrieval happening now, and a job promised within a day is not an answer to that.

The Batch API is refused outright on a key without billing enabled, and it says so with
`400 FAILED_PRECONDITION. {'error': {'message': 'Precondition check failed.'}}` — nothing a
reader can act on, and it failed the whole review. Now:

- the refusal is recognised and rewritten to say what it means and what to do about it,
  while keeping the provider's own words;
- judging and indexing both degrade to the interactive path rather than losing the work;
- the key is not asked again for the life of the process, because the refusal is about the
  project rather than about that batch;
- `ARCHCOMPASS_GOOGLE_BATCH=0` turns batching off without changing the model.

Which means the retry in §15 is doing the real work on a free-tier key, and the batch is the
optimisation it becomes when billing is on.

## 18. Code is coloured

Every excerpt and every fenced block in a policy or a report is syntax-highlighted.
`highlight.js` is used as a tokeniser only — it emits `hljs-…` class names and the palette
lives in `styles.css` with every other colour, so a keyword follows the workspace's theme
instead of a bundled stylesheet that would have to be kept in step with it. Nine grammars are
registered by hand rather than taking the full build, which is most of a megabyte for a tool
that reads Python.

It never guesses. An excerpt's language comes from the extension of the file it was read out
of, and a fence's from what the fence declares; anything else is left uncoloured. Detection
on a four-line excerpt is a coin toss, and confidently wrong colouring is worse than none,
because the colours are a claim about what the tokens mean.

Line numbers are a separate column from the code, so an excerpt is highlighted once as a
whole. Highlighting line by line would end a docstring at every newline and start a new one.

## 19. Still open

- A batch that outlives the process is not resumed on restart. The job name is logged and the
  execution is marked abandoned, so nothing is silently lost, but collecting an in-flight
  batch after a restart is not implemented.
- The batch judge polls in-process rather than through the graph's interrupt/resume, which is
  correct while the run owns a thread and would need revisiting for a multi-process
  deployment.
