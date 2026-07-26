# Workspace Design

**Status:** Direction document
**Authority:** Governs workspace structure; subordinate to master plan §6B
**Current implementation:** `docs/web-workspace.md`, updated as milestones land

This document says what the browser workspace is becoming and why. It is the argued
version of master plan §6B: the thesis, the surfaces, what dissolves, and the order the
change happens in.

## 1. The thesis

The product is one verb: *review this repository against this case, then interrogate the
result*. The workspace that shipped with the consultation era is organised by noun —
Cases, Repositories, Reviews, Policies as peer pages — and no page owns the verb. The
result is the scattered feeling the redesign exists to remove: the real entry point is a
panel halfway down one of five pages, the happy path is only the bundled demo, and the
one object that matters most (the case) cannot be authored in the browser at all.

The rule for every workspace decision:

> **The navigation is the flow.** A surface earns a place in primary navigation only by
> being a step of the review flow, a library the flow reads from, or the record it writes.
> Everything else is reached from within the flow, with a question attached, or not at all.

## 2. The flow, as surfaces

```text
HOME — the flow's front door
│
├── Start a review
│     RAIL A: repository            RAIL B: case
│     pick an indexed one,          pick an existing case,
│     or index a new path           import/author YAML,
│         │                         or revise a previous one
│         │                             │
│         └────────────┬────────────────┘
│                      │   (a bundled example fills both
│                      │    rails with one click)
│                      ▼
│              Run the review
│              "judging boundary k of n" — a countable
│              sequence, not an unexplained wait
│                      │
│                      ▼
│              THE REVIEW PAGE — the destination
│              every boundary, material and cleared ·
│              recommended responses · policy bearings ·
│              detection limits · score bar when the
│              example ships answers · the question dock
│              (each question carries the whole review)
│                      │
│                      └── "Revise case & review again"
│                          new case revision → new review,
│                          linked both ways
│
├── Policies — the standing library the judgement reads
│
└── Reviews — the standing record the flow writes, grouped by case,
    opening onto review pages
```

Primary navigation is exactly that: **Home** (start a review), **Policies**, and
**Reviews**. Cases and repositories stop being destinations and become the two rails of
the start step.

*Revised after the first pass.* Past reviews began on Home, which is what a front door with
"two jobs" implied. In use it made the start step longer every time the tool was used, and
put an unbounded list under the one surface that has to stay short. The record is the third
thing the rule already allows — the flow writes it as it reads the policy corpus — so it
earned its own entry. Home keeps a one-line pointer: the way back after a run belongs where
the run ended, the listing does not.

## 3. The surfaces in detail

### Home

One front door with one job: start a review.

- The start step presents the two rails side by side, order-free, with bundled examples
  as one-click fills of both rails (kept prominent — they remain the shortest path to a
  first review, and the scored one is how the tool proves itself).
- The hero cards, the `/new` links, and the aggregate stat tiles go. Workspace readiness
  (model, provider) collapses into the sidebar footer where it already lives.

### Reviews

The record of what this workspace has judged, grouped by case rather than listed flat.
Revising a case and reviewing again is the loop the tool is built around, so successive runs
of one case are one history; flat, they read as unrelated results, and the revision each
judged is the only thing separating a re-run from a review of a changed case.

Rows carry the examined count, the material count, and "all cleared" as a first-class
result — a review that cleared six boundaries and one that found nothing to examine are
different results.

### Starting a review — the two rails

**Rail A, repository.** Pick from indexed repositories or index a new path. Indexing is
a progress step here, not a page: the atlas is substrate (master plan §9.2), and the
user's concept is "point at my repo", not "manage atlas versions". Freshness-checking
stays where it is, in the application.

**Rail B, case.** Pick an existing case, author a new one, or revise one. The first
shippable authoring surface is a **YAML editor with validation** — `POST
/api/cases/import-yaml` already exists, the CLI already documents the format, and the
case fields that matter most (`expected_future_changes`, `non_goals`,
`confirmed_facts`) are exactly the ones a form flattens badly. A structured form can
follow once the flow is whole; it must not gate it.

The rails converge on one Run button, enabled when both are filled. This step absorbs
the Cases page (picking, history, revision) and the Repositories page (indexing,
selection) — the nouns live inside the verb.

### The run

A review is one model call per boundary: a countable sequence, known-length as soon as
detection finishes. The run surface shows the stages the run actually has — sweep, judge,
read as a set — with every detected boundary named under them and each verdict appearing as
it lands. That is a contract about what the user sees, not about infrastructure — no job
queue and no background workers (master plan §18); whether the count arrives by streaming
response or polling is an implementation choice.

What the first implementation did — a minutes-long synchronous request behind a
single notice line, ending in a full-page reload — read as *broken* rather than
*working*, and is the difference between a tool and a script with a UI. A single
indeterminate spinner is the same failure in a smaller form: three stages of very different
lengths, drawn as one, are indistinguishable from a hung request.

### The review page

Already the strongest surface, and it stays the centre of gravity. Every boundary with
its verdict rail, rationale, policy bearings with the denominator named, detection
limits printed against the boundary, the score bar for the scored example, and the
question dock riding the bottom of the page.

It gains, in order of value:

1. **Revise case & review again.** The iterate loop the two-rail architecture makes
   cheap: a new case revision re-runs judgement over unchanged candidates. The action
   states that it creates a new immutable revision and a new review; the two reviews
   link to each other. Nothing edits a review in place, ever.
2. **A provenance line.** Which case revision, which atlas version, which policy set —
   the pinning that already exists in the record, surfaced instead of implied.
3. **The atlas drill-down** (§4): from a finding to its neighbourhood in the graph, and
   the review's own map of the boundaries it examined, each node carrying its verdict.

The question dock stays a pure client of the review-conversation routes (ADR 0004) and
keeps grounding visible: answers name the boundaries they rest on, and an answer
grounded on nothing says so.

### Policies

Kept as the one standing library in the navigation: the corpus is user-authored
configuration with a life independent of any single review. Browsing, sources and
rebuild stay. The copy changes to say what is true now: the corpus is presented whole
with every boundary — nothing is retrieved, so nothing can be missed.

## 4. The atlas in the workspace

Master plan §9.2 names the atlas's three roles. In the workspace they land as:

- **Substrate — invisible.** Indexing is a progress state inside Rail A.
- **Evidence — inside findings.** Locations and measurements appear as the content of
  each reviewed boundary. No surface labelled "atlas" is involved.
- **Explorer — parked, then repossessed.** The graph explorer (`atlas.tsx`) leaves
  primary navigation now and re-enters later as an evidence drill-down *from a
  finding*: "show BR-003's neighbourhood" — what depends on the abstraction this
  verdict says to remove, what its sole implementation touches. Entered from the
  report it answers a question the reader has; entered from a sidebar it is a map with
  no question, competing with the flow.

The explorer code is a working investment and is kept routed but demoted — reachable
from the repository picker as well as from each finding — so it stays alive, tested and
ready for repossession rather than rotting unrouted.

**Repossessed, on the review page.** The review carries a map of its own, built from the
review outward: each examined abstraction is inspected and its neighbourhood is the map, so
what is drawn is where *these* boundaries sit rather than the repository at large. Each node
carries its verdict, including a cleared one — "examined and found to be earning its place"
is not the absence of a finding, and a map that drew the two alike would say the advisor
never looked. It sits after the verdicts: "where does this sit" is a question a reader has
only once they know what was decided.

## 5. What this dissolves or removes

Subtraction first; it is pure removal and deletes most of the scattered feeling on its
own.

| What | Why |
| --- | --- |
| Links to `/new` (Dashboard ×2, Cases ×1) | Route does not exist; silently bounces to the dashboard. |
| "Open report" link to `/runs/:id` | Consultation-era route; does not exist. |
| `architecture-workspace.tsx` + its test (~1,250 lines) | Unrouted consultation-era code; imports `ConsultationRun`, calls the removed `/api/runs/…`. |
| Consultation-era types and fields in the frontend (`ConsultationRun`, `RecommendationReport`, `current_recommendation`/`confidence` rendered on case cards) | The era is deleted server-side; the frontend keeps its vocabulary alive. |
| "Consultation" copy on Cases, Policies, Repositories pages | Says the superseded thing to every user. |
| `window.location.assign` full reload after a run | The app navigates; a page reload announces that it is not an app. |
| Dashboard and Reviews as separate pages | Merged into Home (§3). |
| Cases and Repositories as navigation destinations | Dissolved into the start step's two rails (§3). |

## 6. Non-goals for this surface

- **No job queue or background execution** (master plan §18). The run stays synchronous;
  visible progress is a presentation obligation, not an infrastructure project.
- **No authentication or multi-user.** The workspace binds to localhost for one person.
- **No atlas-first navigation.** The explorer re-enters through findings or not at all.
- **No editing of reviews or answers.** Reviews are immutable; conversations are
  append-only; changed circumstances are a new revision and a new review.
- **No generic chat.** The dock is pinned to one review and grounded by position; a
  free-floating assistant is a different product.
- **No new backend flows for the redesign.** Every surface above is a client of routes
  that exist today, plus at most a progress representation for the run. A workspace
  change that needs a new domain flow is out of scope here (echoing ADR 0004's line).

## 7. Sequencing

Ordered so every step leaves the workspace more coherent than before it. Steps 1–5 are
delivered:

1. **Subtraction** (delivered) — everything in §5's table that is deletion or copy. No
   behaviour added.
2. **The spine** (delivered) — Home replaces Dashboard + Reviews; the start step with both
   rails; Cases and Repositories dissolve into it; the explorer demotes per §4.
3. **The case rail** (delivered) — YAML authoring/import in the start step, and a stored
   case read back as the YAML it was written in. The first moment the whole flow is
   completable in the browser.
4. **The visible run** (delivered) — per-boundary progress replacing the notice line and
   reload, from a streamed response.
5. **The iterate loop** (delivered) — revise-and-review-again from the review page, with
   linked reviews and the provenance line.
6. **Later** — the finding-level atlas drill-down; a structured case form beside the
   YAML editor; the greenfield rail when master plan §4.1 is built.

Steps 1–2 change no contracts. Step 3 uses existing case endpoints. Step 4 is the only
one that may touch the API surface (a progress representation for a running review),
and `make api-types` follows it as always.
