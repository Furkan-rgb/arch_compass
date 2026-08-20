# What each region on screen is called

A shared vocabulary for talking about the interface. These are the *large* regions — the
ones worth pointing at in a sentence like "the queue footer overlaps the last row".
Anything smaller (a badge, a tag, a button) is named by what it is and is not listed here.

Names are the component names in the code, so a name here is also a file to open. What each
region is *for* is [the charter](charter.md); what it looks like and why is
[the design system](design-system.md).

## Everywhere — the shell

| Name | What it is | Where |
| --- | --- | --- |
| **Sidebar** | The 232px left rail: wordmark, Review and Workspace nav, workspace card. Becomes a drawer below `lg`. | [shell.tsx](../frontend/src/app/shell.tsx) |
| **Topbar** | The sticky bar above the page: menu button on small screens, model chips, theme toggle. | [shell.tsx](../frontend/src/app/shell.tsx) |
| **Page area** | Everything right of the sidebar and below the topbar. Each route fills it. | [shell.tsx](../frontend/src/app/shell.tsx) |

## The review page — `/reviews/:id`

Top to bottom, then the workbench's two columns.

| Name | What it is | Where |
| --- | --- | --- |
| **Review head** | Title, repository path, branch, commit, status, and the Answer / Cancel / Run buttons. | [review-page.tsx:47](../frontend/src/features/review/review-page.tsx#L47) |
| **Status ribbon** | The counts, set as readings on a scale: need you, decided by the team, judged, policies retrieved, new or changed. | [review-page.tsx:111](../frontend/src/features/review/review-page.tsx#L111) |
| **Surface tabs** | Workbench · Delta · Atlas · Evidence · Retrieval · Report · Ask. | [review-page.tsx:285](../frontend/src/features/review/review-page.tsx#L285) |
| **Workbench** | The first tab's body: the queue rail beside the detail column. | [review-page.tsx:293](../frontend/src/features/review/review-page.tsx#L293) |

### The queue rail — the workbench's left column

Sticky, `19rem` wide, put away by "Hide the queue".

| Name | What it is | Where |
| --- | --- | --- |
| **Queue rail** | The sticky left column as a whole: the attention queue above, the revision rail below. | [review-page.tsx:303](../frontend/src/features/review/review-page.tsx#L303) |
| **Attention queue** | The panel a reviewer works down. The product's centre of gravity. | [attention-queue.tsx](../frontend/src/features/review/attention-queue.tsx) |
| ├ **Queue header** | "Attention queue", its subtitle, and the Attention / Settled / All filter switch. | [attention-queue.tsx:131](../frontend/src/features/review/attention-queue.tsx#L131) |
| ├ **Queue spine** | The three segments at a row's left edge — machine, model, person — saying how far through the three jobs the candidate is. | [spine.tsx](../frontend/src/ui/spine.tsx) |
| ├ **Queue list** | The scrolling list of candidate rows, with the clarification card pinned on top when the review is waiting. Fades at an edge it can still scroll past. | [attention-queue.tsx:107](../frontend/src/features/review/attention-queue.tsx#L107) |
| └ **Queue footer** | The "Hide the queue" strip under the list. | [review-page.tsx:307](../frontend/src/features/review/review-page.tsx#L307) |
| **Revision rail** | The lineage of reviews for this branch and case, plus any run in flight. | [revision-rail.tsx](../frontend/src/features/review/revision-rail.tsx) |

### The detail column — the workbench's right column

Holds exactly one of these, depending on what the queue has selected.

| Name | What it is | Where |
| --- | --- | --- |
| **Finding detail** | The card for one candidate. | [finding-detail.tsx](../frontend/src/features/review/finding-detail.tsx) |
| ├ **Attribution gutter** | The `6.75rem` column down the left of the finding. Says whose voice produced the block beside it — measured, judged, decided — and who in particular. Stacks into a label above each block below `lg`. | [gutter.tsx](../frontend/src/ui/gutter.tsx) |
| ├ **Finding header** | The MEASURED block: pattern, delta state, and the candidate's identifier in mono with its summary beneath. | [finding-detail.tsx:72](../frontend/src/features/review/finding-detail.tsx#L72) |
| ├ **Context rail** | Case, policies and provenance behind "Judgement context". A drawer at every width — the gutter owns the left margin and there is no right one. | [context-rail.tsx](../frontend/src/features/review/context-rail.tsx) |
| ├ **Decision bar** | Accept / waive / park for this candidate, and the standing decision. | [decision-bar.tsx](../frontend/src/features/review/decision-bar.tsx) |
| └ **Technical detail** | The collapsed disclosure at the bottom: ids, detection rationale, measurements. | [finding-detail.tsx:308](../frontend/src/features/review/finding-detail.tsx#L308) |
| **Clarification round** | Replaces the finding detail when the review is waiting on answers. Each question offers the answers the model proposed, plus writing your own and skipping. | [clarification.tsx](../frontend/src/features/review/clarification.tsx) |

### The other surfaces

One per tab, each filling the whole width, all in
[surfaces.tsx](../frontend/src/features/review/surfaces.tsx).

| Name | What it is | Where |
| --- | --- | --- |
| **Delta surface** | What moved since the previous review: one list keyed on the candidate's name, filtered by change state. A row opens its finding in the workbench. | [surfaces.tsx:127](../frontend/src/features/review/surfaces.tsx#L127) |
| **Atlas surface** | The repository's structure, explored rather than drawn. | [surfaces.tsx](../frontend/src/features/review/surfaces.tsx) |
| **Evidence surface** | Every pinned excerpt, grouped under the candidate it was pinned for. | [surfaces.tsx:398](../frontend/src/features/review/surfaces.tsx#L398) |
| **Retrieval surface** | Which policies were retrieved for each candidate, and by what. | [surfaces.tsx](../frontend/src/features/review/surfaces.tsx) |
| **Report surface** | The rendered Markdown report. | [surfaces.tsx](../frontend/src/features/review/surfaces.tsx) |
| **Ask surface** | Questions put to the finished review. | [surfaces.tsx](../frontend/src/features/review/surfaces.tsx) |

## The other pages

| Name | Route | Where |
| --- | --- | --- |
| **Landing page** | `/` | [landing-page.tsx](../frontend/src/features/landing/landing-page.tsx) |
| **Start page** | `/start` — repository picker, scope picker, the run button | [start-page.tsx](../frontend/src/features/start/start-page.tsx) |
| **Run page** | `/runs/:runId` — a review being made, with its progress timeline | [run-page.tsx](../frontend/src/features/start/run-page.tsx) |
| **Reviews page** | `/reviews` | [reviews-page.tsx](../frontend/src/features/reviews/reviews-page.tsx) |
| **Repositories page** | `/repositories` | [repositories-page.tsx](../frontend/src/features/repositories/repositories-page.tsx) |
| **Cases page** | `/cases` | [cases-page.tsx](../frontend/src/features/cases/cases-page.tsx) |
| **Policies page** | `/policies` | [policies-page.tsx](../frontend/src/features/policies/policies-page.tsx) |
| **Models page** | `/settings` | [settings-page.tsx](../frontend/src/features/settings/settings-page.tsx) |
