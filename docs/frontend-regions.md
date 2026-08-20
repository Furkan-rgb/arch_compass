# What each region on screen is called

A shared vocabulary for talking about the interface. These are the *large* regions — the
ones worth pointing at in a sentence like "the queue footer overlaps the last row".
Anything smaller (a badge, a tag, a button) is named by what it is and is not listed here.

Names are the component names in the code, so a name here is also a file to open. What each
region is *for* is [the charter](charter.md); what it looks like and why is
[the design system](design-system.md); how a person works it, and why the surfaces are the
ones they are, is [the experience](experience.md).

## Everywhere — the shell

| Name | What it is | Where |
| --- | --- | --- |
| **Sidebar** | The 232px left rail: wordmark, Review and Workspace nav, workspace card. Becomes a drawer below `lg`. | [shell.tsx](../frontend/src/app/shell.tsx) |
| **Topbar** | The sticky bar above the page: menu button on small screens, model chips, theme toggle. | [shell.tsx](../frontend/src/app/shell.tsx) |
| **Page area** | Everything right of the sidebar and below the topbar. Each route fills it. | [shell.tsx](../frontend/src/app/shell.tsx) |

## The review page — `/reviews/:id`

The queue is the page's left column at every mode, not a tab on it. Everything else fills
the column beside it.

| Name | What it is | Where |
| --- | --- | --- |
| **Review head** | One line: which review this is, and the repository, branch and commit it read, with the status and the Answer / Cancel / Run buttons. | [review-page.tsx:56](../frontend/src/features/review/review-page.tsx#L56) |
| **Queue rail** | The sticky left column: the attention queue above, the revision rail below. Present in every mode. | [review-page.tsx:279](../frontend/src/features/review/review-page.tsx#L279) |
| **Detail column** | Everything to its right: the mode tabs and whatever they select. | [review-page.tsx:302](../frontend/src/features/review/review-page.tsx#L302) |
| **Mode tabs** | Workbench · Delta · Report · Ask. What the detail column is showing — not views of the review. | [review-page.tsx:303](../frontend/src/features/review/review-page.tsx#L303) |

### The queue rail

| Name | What it is | Where |
| --- | --- | --- |
| **Attention queue** | The panel a reviewer works down. The product's centre of gravity. Moves from the keyboard: `↑` `↓` `j` `k` walk the rows and open what they land on. | [attention-queue.tsx](../frontend/src/features/review/attention-queue.tsx) |
| ├ **Queue header** | "Attention queue", its subtitle, and the Attention / Settled / All filter switch. | [attention-queue.tsx:236](../frontend/src/features/review/attention-queue.tsx#L236) |
| ├ **Queue spine** | The three segments at a row's left edge — machine, model, person — saying how far through the three jobs the candidate is. | [spine.tsx](../frontend/src/ui/spine.tsx) |
| ├ **Queue groups** | "Moved since review N" above "Carried forward", when there is a previous review and both have rows. | [attention-queue.tsx:186](../frontend/src/features/review/attention-queue.tsx#L186) |
| ├ **Queue list** | The scrolling list of candidate rows, with the clarification card pinned on top when the review is waiting. Fades at an edge it can still scroll past. | [attention-queue.tsx:275](../frontend/src/features/review/attention-queue.tsx#L275) |
| └ **Worked through** | What the list becomes when nothing needs a person: what was decided, and the two things done next. | [attention-queue.tsx:426](../frontend/src/features/review/attention-queue.tsx#L426) |
| **Revision rail** | The lineage of reviews for this branch and case, plus any run in flight. | [revision-rail.tsx](../frontend/src/features/review/revision-rail.tsx) |

### The detail column

Holds exactly one of these.

| Name | What it is | Where |
| --- | --- | --- |
| **Finding detail** | The assessment of one candidate. The Workbench mode's default. | [finding-detail.tsx](../frontend/src/features/review/finding-detail.tsx) |
| ├ **Attribution gutter** | The `6.75rem` column down the left of the finding. Says whose voice produced the block beside it — measured, judged, decided — and who in particular. Stacks into a label above each block below `lg`. | [gutter.tsx](../frontend/src/ui/gutter.tsx) |
| ├ **Finding header** | The MEASURED block: pattern, delta state, and the candidate's identifier in mono with its summary beneath. | [finding-detail.tsx:82](../frontend/src/features/review/finding-detail.tsx#L82) |
| ├ **Decision bar** | Accept / park / waive for this candidate, the standing decision, and whether it was taken against a verdict that has since moved. | [decision-bar.tsx](../frontend/src/features/review/decision-bar.tsx) |
| ├ **Technical detail** | The collapsed disclosure: ids, detection rationale, measurements. | [finding-detail.tsx:322](../frontend/src/features/review/finding-detail.tsx#L322) |
| └ **Next needing you** | The strip at the foot, naming the next candidate that still wants a person. | [finding-detail.tsx:362](../frontend/src/features/review/finding-detail.tsx#L362) |
| **Clarification round** | Replaces the finding detail when the review is waiting on answers. Each question offers the answers the model proposed, plus writing your own and skipping. | [clarification.tsx](../frontend/src/features/review/clarification.tsx) |
| **Delta surface** | What moved since the previous review: one list keyed on the candidate's name, filtered by change state. A row opens its finding. | [surfaces.tsx:137](../frontend/src/features/review/surfaces.tsx#L137) |
| **Report surface** | The rendered Markdown report. | [surfaces.tsx](../frontend/src/features/review/surfaces.tsx) |
| **Ask surface** | Questions put to the finished review. | [surfaces.tsx](../frontend/src/features/review/surfaces.tsx) |

### Judgement context — the drawer

Opened from the finding, at every width. Four tabs, all scoped to the candidate in front of
you; at review scope the Provenance tab becomes the audit of every candidate at once.

| Name | What it is | Where |
| --- | --- | --- |
| **Context rail** | The drawer as a whole: Case · Policies · Structure · Provenance. | [context-rail.tsx](../frontend/src/features/review/context-rail.tsx) |
| ├ **Structure** | What else touches this candidate's code, searched in the atlas and seeded from its participants. | [context-rail.tsx:283](../frontend/src/features/review/context-rail.tsx#L283) |
| └ **Review provenance** | Every candidate's retrieval at once, when no candidate is selected. | [context-rail.tsx:193](../frontend/src/features/review/context-rail.tsx#L193) |

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
