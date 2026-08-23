# What each region on screen is called

A shared vocabulary for talking about the interface. These are the *large* regions — the
ones worth pointing at in a sentence like "the docket row clips its own claim".
Anything smaller (a badge, a tag, a button) is named by what it is and is not listed here.

Every name here is a file to open. There are no line numbers, and there were: all
twenty-one had gone stale, and one pointed at a file the component had moved out of. A file
link stays true as long as the file does; a line number is wrong the next time anything
above it is edited, and a reader who follows one to the wrong place trusts this document
less than one who was never given the number.

Names are the component names in the code, so a name here is also a file to open. What each
region is *for* is [the charter](charter.md); what it looks like and why is
[the design system](design-system.md); how a person works it, and why the surfaces are the
ones they are, is [the experience](experience.md).

## Everywhere — the shell

One bar, and nothing else standing between a page and the viewport. The 232px sidebar is
gone: it carried six links and a workspace path down the full height of every screen, charged
to every surface including the one that needed the width most.

| Name | What it is | Where |
| --- | --- | --- |
| **Topbar** | The sticky 48px bar: wordmark, the six nav links above `lg`, search, model chips, theme toggle, New review. Dark in both themes — the one chrome in the product that does not invert, which is why its controls speak in the `band` tokens rather than `ink`/`surface`. | [shell.tsx](../frontend/src/app/shell.tsx) |
| **Navigation drawer** | The nav as a column, below `lg`, with the workspace path under it. | [shell.tsx](../frontend/src/app/shell.tsx) |
| **Command palette** | ⌘K. Everything the nav lists, plus every review and every repository by name. The reason the sidebar could go. | [command-palette.tsx](../frontend/src/ui/command-palette.tsx) |
| **Page area** | Everything below the topbar. A document route gets a measured column; the review page is handed the viewport. | [shell.tsx](../frontend/src/app/shell.tsx) |

## The review page — `/reviews/:id`

The docket **is** the review: the list and the assessments are one surface, in one column, at
every width. Atlas, Delta, Report and Ask are documents about the review rather than ways of
working through it, so they are peers of the docket rather than columns beside it.

| Name | What it is | Where |
| --- | --- | --- |
| **Review head** | One line: which review this is, and the repository, branch and commit it read, with the status and the Cancel / New review button. | [review-page.tsx](../frontend/src/features/review/review-page.tsx) |
| **Review counts** | Under the head: how many things still want you, then the verdict spread. Orientation, read once, on the way to the work. | [review-page.tsx](../frontend/src/features/review/review-page.tsx) |
| **Surface tabs** | Docket · Atlas · Delta · Report · Ask. Which document about this review is on screen. **In the URL**, not page state — `?tab=atlas` is a link somebody can send, and a refresh lands back on it. A query parameter rather than a path segment on purpose: a segment changes which route the URL matches, which remounts the page and costs the reader their open row and filter. The docket carries no parameter, because arriving at a review and arriving at its docket are the same arrival. Your place in the docket survives a trip to any of them. | [review-page.tsx](../frontend/src/features/review/review-page.tsx) |

### The docket

| Name | What it is | Where |
| --- | --- | --- |
| **Docket** | The single column a reviewer works down. The product's centre of gravity. Moves from the keyboard: `↑` `↓` `j` `k` walk the rows and open what they land on, `A` `P` `W` decide the open one. | [docket.tsx](../frontend/src/features/review/docket.tsx) |
| ├ **Progress** | One segment per candidate, filled as it settles, then "N of M settled" and the Attention / Settled / All filter. Ink and rule, never a verdict hue: how far through you are is not a grade anything was given. | [docket.tsx](../frontend/src/features/review/docket.tsx) |
| ├ **Clarification card** | The first item when the review is waiting on answers, holding the round itself. Nothing below it can be finished until it is answered. | [docket.tsx](../frontend/src/features/review/docket.tsx) |
| ├ **Docket group** | "Moved since review N" above "Carried forward", when there is a previous review and both have rows. Hoists a namespace every row in the group shares. | [docket.tsx](../frontend/src/features/review/docket.tsx) |
| ├ **Docket row** | One candidate: its verdict as a left edge and as a sign — alert, pause or tick — its name, **its claim as a sentence**, its pattern and movement, and its trajectory across the lineage. The sentence is what makes the list readable and the reason most rows never have to be opened. | [docket.tsx](../frontend/src/features/review/docket.tsx) |
| ├ **Candidate trajectory** | The verdict this candidate carried at each revision of the branch, as one node per review. The revision being read is at full strength, underlined, its number in ink; the rest recede to 45%. Never ringed — the marks are circles, so a ring reads as two concentric circles. | [trajectory.tsx](../frontend/src/features/review/trajectory.tsx) |
| └ **Worked through** | What the list becomes when nothing needs a person: what was decided, and the two things done next. | [docket.tsx](../frontend/src/features/review/docket.tsx) |
| **Revision rail** | The lineage of reviews for this branch and case, plus any run in flight. Under the work rather than beside it — which revision you are reading is a fact about the page, not something consulted while deciding. | [revision-rail.tsx](../frontend/src/features/review/revision-rail.tsx) |

### Inside an open row

| Name | What it is | Where |
| --- | --- | --- |
| **Finding body** | The assessment, as the argument beside the material it rests on. It carries neither the verdict nor the identifier: the row it expands inside just showed both. | [finding-detail.tsx](../frontend/src/features/review/finding-detail.tsx) |
| ├ **Judged** | The model's paragraph at the reading size — the only text set that large on the page — under a line naming who produced it, then Hinges on and Recommended response. | [finding-detail.tsx](../frontend/src/features/review/finding-detail.tsx) |
| ├ **Measured** | The machine's column: the code involved, the readings on a rule, and the excerpts inline. You cannot argue with a judgement whose evidence is one click away, which is what folding this behind a disclosure used to ask. | [finding-detail.tsx](../frontend/src/features/review/finding-detail.tsx) |
| ├ **Disclosure** | Policies and Provenance, each with a closed state that says what is inside it. | [finding-detail.tsx](../frontend/src/features/review/finding-detail.tsx) |
| └ **Decision bar** | Accept / Park / Waive for this candidate, the standing decision, and whether it was taken against a verdict that has since moved. | [decision-bar.tsx](../frontend/src/features/review/decision-bar.tsx) |

### The other surfaces

| Name | What it is | Where |
| --- | --- | --- |
| **Atlas surface** | The shape this review was looking at, drawn from the atlas it was pinned to. Anchors on every element a finding was made about, opens on the **Judged** lens, and answers "where is this" — never "what is in the repository now". A card with a verdict opens its finding. | [atlas-surface.tsx](../frontend/src/features/review/atlas-surface.tsx) |
| ├ **Atlas explorer** | The map itself and the panel beside it: three lenses, filters, pan / zoom / fit / full screen, a minimap, and the atlas queries a reader can run from a selected element. Knows nothing about reviews. | [explorer.tsx](../frontend/src/features/atlas/explorer.tsx) |
| **Delta surface** | What moved since the previous review: one list keyed on the candidate's name, filtered by change state. Its unique content is `addressed` — a candidate that is gone, and so has no docket row to be met in. A row opens its finding. | [surfaces.tsx](../frontend/src/features/review/surfaces.tsx) |
| **Report surface** | The rendered Markdown report, led by what the review comes to. | [report-surface.tsx](../frontend/src/features/review/report-surface.tsx) |
| **Ask surface** | Questions put to the review, in separate threads. | [surfaces.tsx](../frontend/src/features/review/surfaces.tsx) |

### Judgement context — the drawer

Opened from an open row, at every width. Four tabs, all scoped to the candidate in front of
you; at review scope the Provenance tab becomes the audit of every candidate at once.

| Name | What it is | Where |
| --- | --- | --- |
| **Context rail** | The drawer as a whole: Case · Policies · Structure · Provenance. | [context-rail.tsx](../frontend/src/features/review/context-rail.tsx) |
| ├ **Structure** | What else touches this candidate's code, searched in the atlas and seeded from its participants. | [context-rail.tsx](../frontend/src/features/review/context-rail.tsx) |
| └ **Review provenance** | Every candidate's retrieval at once, when no candidate is selected. | [context-rail.tsx](../frontend/src/features/review/context-rail.tsx) |

## The other pages

| Name | Route | Where |
| --- | --- | --- |
| **Landing page** | `/` | [landing-page.tsx](../frontend/src/features/landing/landing-page.tsx) |
| **Start page** | `/start` — two steps: which repository, and how much of it to read. The case is stated at the point of running, not confirmed as a step. | [start-page.tsx](../frontend/src/features/start/start-page.tsx) |
| **Run page** | `/runs/:runId` — a review being made, with its progress timeline | [run-page.tsx](../frontend/src/features/start/run-page.tsx) |
| **Reviews page** | `/reviews` — one block per lineage (repository, branch, case), revisions inside it in sequence, a run in flight at the top of its own | [reviews-page.tsx](../frontend/src/features/reviews/reviews-page.tsx) |
| **Repositories page** | `/repositories` | [repositories-page.tsx](../frontend/src/features/repositories/repositories-page.tsx) |
| **Cases page** | `/cases` | [cases-page.tsx](../frontend/src/features/cases/cases-page.tsx) |
| **Policies page** | `/policies` | [policies-page.tsx](../frontend/src/features/policies/policies-page.tsx) |
| **Models page** | `/settings` | [settings-page.tsx](../frontend/src/features/settings/settings-page.tsx) |
