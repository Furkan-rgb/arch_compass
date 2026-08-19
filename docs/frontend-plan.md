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
