# The design system

What ArchCompass looks like, and why it looks like that.

Three documents describe the interface and they do not overlap. [The charter](charter.md)
says what the product is for and which rules settle an argument about it.
[Frontend regions](frontend-regions.md) is the vocabulary — what each area on screen is
called, so a sentence like "the queue footer overlaps the last row" means one thing.

This one is the contract between the two: the tokens, the type roles and the structural
devices that the components are built from. If a component invents a colour, a face or a
radius that is not here, that is the bug — not a local decision.

## What was wrong with the first system

Worth writing down, because the first system was not careless. It was disciplined, it was
consistent, and it was anonymous.

**The three jobs were invisible.** The charter's second commitment says the machine
assembles, the model judges and the person decides, and that ArchCompass keeps those three
jobs *visibly* apart. They were apart in the domain — `Finding` and `StandingDecision` are
separate records for exactly this reason — and identical on screen. `VerdictBadge` and
`DispositionBadge` were the same component reading a different lookup table. The single
most distinctive idea in the product had no visual expression at all.

**The type had no contrast.** Schibsted Grotesk set the headings and Instrument Sans set
the body. Two grotesks, a few years apart in design, near-identical in colour and width.
A pairing with no contrast is not neutral — it reads as *unconsidered*, and it left the
interface indistinguishable from any other tool with a sidebar.

**The accent was spent on chrome.** `--accent` appeared in 29 of 40 components and 74 times
in all: tab underlines, link text, primary buttons, focus rings, case tags, the recommended
response border, the timeline dot. All of it furniture. Meanwhile the three hues that carry
the product's only real signal — material, held, cleared — were competing with indigo for a
reader's colour attention on every screen. `ui/verdict-hues.test.ts` already existed to stop
the verdict palette leaking outwards; nothing stopped the accent leaking inwards.

**Everything was a card on a card.** 106 uses of `rounded-*`, 13 panel shadows, and a
workbench that nested a panel inside a panel inside a panel. The radius and the shadow were
doing the work that a rule and a margin should do, and each nesting level cost real
horizontal space in a layout that has three columns to fit.

## The thesis: three voices

**Every element on screen belongs to exactly one of the three jobs, and says which by its
typeface.**

| Voice | Who is speaking | Face | What it sets |
| --- | --- | --- | --- |
| **Measured** | Deterministic analysis | Mono | Names, paths, counts, ids, provenance, evidence locations, measurements |
| **Judged** | The model | Serif | Verdict reasoning, hinges, policy bearings, recommended responses, review answers |
| **Decided** | The person | Sans | Controls, labels, navigation, empty states, the record of what a person chose |

This is not decoration keyed to content; it is the product's structure made legible. A
reader who has learned three faces can tell whose voice a paragraph is in without reading
it, and that is precisely the distinction the charter says must never blur.

It also constrains us usefully. When a new element does not obviously belong to one of the
three, that is a design question worth stopping on: something is being presented as fact
that is an opinion, or as a conclusion that is actually a control.

### Why the model's voice is a serif

This is the deliberate risk in the system, so it gets its own paragraph.

Developer tools do not set body copy in a serif. The reason to do it here is that the
model's output is not a status, a log line or a result — it is *an argument the reader is
meant to weigh and disagree with*. The mission statement asks for "architectural judgement
they can trust, argue with, and re-check". Prose you argue with is set in the register of an
opinion: a report, a judgement, a review. Setting it in the same sans as the buttons around
it quietly asserts that it is a system output on the same footing as a count, which is the
one thing the charter says it is not.

The serif also does the separation work for free. There is no way to mistake a sentence the
model wrote for a sentence the analyser produced, because they are not in the same face.

## Type

Three faces, all self-hosted as woff2 in `frontend/src/assets/fonts/`, latin subset, loaded
`font-display: swap` with a real fallback stack.

| Token | Face | Cut | Fallback |
| --- | --- | --- | --- |
| `--font-display` | **Archivo** | Variable, 400–700 | `ui-sans-serif, system-ui, sans-serif` |
| `--font-read` | **Newsreader** | Variable, 200–500, optical size 6–72 | `Georgia, "Times New Roman", serif` |
| `--font-code` | **IBM Plex Mono** | 400 and 600 static | `ui-monospace, "SF Mono", Menlo, monospace` |

Archivo is a workhorse grotesk with engineered proportions and a wide weight range; it holds
up at 10px uppercase and letterspaced, which is most of what the interface asks of it.
Newsreader has a low-contrast, slightly bookish quality that reads well at 15–17px on a
screen. IBM Plex Mono is picked over the previous system stack because "whatever mono the
reader has" is not a design decision, and because Plex's letter shapes sit comfortably
beside both of the others.

No italic cut ships for any of the three. Nothing in the sans register needs one, and
Newsreader's italic is 144 KB for the handful of places a serif emphasis would appear. The
whole payload is 187 KB against the 90 KB the two grotesks cost — the price of the thesis,
and the reason the italics were the first thing cut.

### The scale

Nine steps, each with a job. Anything not on the scale is a mistake.

| px | Face | Where |
| --- | --- | --- |
| 10 | Sans, 700, `0.13em` | Gutter voice, block labels — always uppercase |
| 11 | Mono, 500, `0.13em` | Eyebrows, meta lines, provenance — uppercase where it is a label |
| 12 | Mono, 500 | Queue row identifiers, chips, tab labels |
| 13 | Sans, 600 | Controls, secondary body |
| 15 | Sans, 400 | Body copy, empty states, decision copy |
| 17 | Serif, 300 | The model's reasoning — its own size, used nowhere else |
| 19 | Mono, 500 | The finding's identifier in the detail header |
| 27 | Sans, 600, `-0.025em` | The review title |
| 34–62 | Sans, 600, `-0.035em` | Landing display only, `clamp()`ed |

Line height: mono 1.35–1.5, sans 1.5–1.6, serif 1.68. Measure: the model's prose caps at
`60ch`, everything else at `66ch`. Headings take `text-wrap: balance`; digits that line up
in a column take `tabular-nums`.

## Colour

**Chroma is spent on verdicts. Everything else is graphite.**

The accent is not a hue any more — it is ink. A selected tab is an ink underline, a primary
button is an ink fill, the focus ring is ink. This is the charter's "a colour never carries
meaning alone" pushed one step: where a colour would carry nothing at all, it is not used.

### Tokens

Light is the ground truth; dark is the same six lifted, not naively inverted.

The names are the ones that were already there. Only the values moved — every component
and every region name already speaks in `canvas`/`surface`/`rule`, and renaming a hundred
usages would have been churn with nobody on the other side of it.

| Token | Light | Dark | What it is |
| --- | --- | --- | --- |
| `--canvas` | `#EBEBE6` | `#0C0E10` | The page. A cool bone, off the warm cream the first system used |
| `--surface` | `#FCFCFA` | `#16181B` | Any surface content sits on |
| `--surface-2` | `#F4F4F0` | `#1B1E21` | Recessed strips: tab bars, panel headers, the queue rail |
| `--sunken` | `#E2E2DC` | `#101214` | Wells, inset fields and a selected row |
| `--ink` | `#15171A` | `#E9EAE6` | Text, and every primary action |
| `--ink-2` | `#4B5057` | `#A7ADB4` | Body copy |
| `--ink-3` | `#7D838A` | `#757C83` | Labels, meta, anything demoted |
| `--rule` | `rgb(21 23 26 / 14%)` | `rgb(233 234 230 / 14%)` | Hairlines. The primary structural device |
| `--rule-strong` | `rgb(21 23 26 / 30%)` | `rgb(233 234 230 / 30%)` | Borders on controls, and a voice change in the gutter |
| `--material` | `#AF3A22` | `#E9906F` | Act on it |
| `--held` | `#8E6209` | `#D9AE5B` | Waiting on a person |
| `--cleared` | `#16674A` | `#63BE94` | Assessed and settled |
| `--mark` | `#3E4B5D` | `#93A4BA` | The one non-verdict chroma. See below |

Each verdict also has a `-soft` wash for tinted blocks. Nothing else gets a wash.

### The budget of one: `--mark`

There is exactly one chroma that is not a verdict, and it is reserved for **navigating to
the thing a claim came from** — a source location, a policy, a cited finding. Nothing else
may use it: not a button, not a tab, not a heading.

It earns the exception from "say where it came from". Provenance links are a first-class
category in this product, they appear on nearly every surface, and they need to be
distinguishable from body text at a glance. It is desaturated far enough (`#3E4B5D`) to read
as ink with a bias rather than as an accent, and it never appears next to a verdict.

### What replaced the accent on policy strength

`lib/format.ts` gave `required` the accent tone, on the argument that a required policy is
"the thing to look at" and painting it verdict-red would turn the policy library into a list
of alarms. That argument was right and its answer is now unavailable.

**Policy strength is carried by weight and rule, not by colour.** All three keep their glyph
and their word — `▲ Required`, `◆ Preferred`, `○ Guidance` — which is what the step between
them was always made of. A required policy's block takes a `--rule-strong` border; preferred
and guidance take a hairline. Emphasis without alarm, and no hue at all.

## Structure

**Rules, not cards.** A hairline separating two things is the default. A border around a
thing is for when it is genuinely a separate object you could pick up. A shadow is for
something that actually floats — a drawer, a popover — and nowhere else. `shadow-panel` is
retired.

**Radius is near-zero and means "interactive".** Structural containers — panels, sheets,
rails, the app frame — are square. Controls are `2px`. Only status dots stay round.

The five-step scale collapses to two values behind its existing names: `xs`, `sm` and `md`
all resolve to `2px`, and `lg` and `xl` to `0`. The names survive so a component still reads
as "small control" or "panel" rather than as a number, and so 106 usages did not have to be
rewritten to say the same thing.

**The workbench is one sheet.** The queue rail and the detail column are two columns of the
same surface divided by a rule, not two floating cards with a gap between them. This
recovers roughly 40px of horizontal space per nesting level that the first system spent on
padding and radius.

## The two new devices

### The attribution gutter

The signature element, and the reason the system exists.

A single hairline runs the full height of the finding detail. Every block registers against
it, and the gutter to its left says whose voice produced the block beside it.

```
 108px          │  content
────────────────┼──────────────────────────────────────
       MEASURED ▪  leaky abstraction · unchanged
     detection  │  audiobook.synthesis.providers.qwen
                │
    What was    │  ┌────────┬────────┬────────┐
     counted    │  │   5    │   0    │ 1 of 3 │
                │  └────────┴────────┴────────┘
                │
         JUDGED ▪  ▲ MATERIAL
 gemini-3.6-... │  Five modules outside synthesis.providers name
     2026-08-20 │  this implementation directly. The port exists…
                │
        DECIDED ▪  [ Accept the work ] [ Park ] [ Waive ]
     nobody yet │
```

Rules:

- The gutter is `108px`, right-aligned against the spine, and never holds content — only
  attribution.
- A **voice change** draws a `--rule-strong` line across both columns and puts a 6px filled
  square on the spine. A block within the same voice gets a label in `--ink-3` and no rule.
- The gutter carries *who*, not just *what*: the detector and its version, the model
  identity and the date it judged, or "nobody yet" where no decision has been recorded.
- Because the gutter carries provenance, there is no separate provenance footer. Having both
  was printing the same attribution twice.
- Below `lg` the gutter collapses to a full-width label strip above each block; the sequence
  survives, the two-column registration does not.

### The queue spine

The same three jobs, compressed to ten pixels, at the left edge of every queue row.

Three stacked 3×7px segments — machine, model, person:

- **Machine** is always filled. There is always evidence; that is what raised the candidate.
- **Model** fills once there is a verdict, and takes the verdict's hue.
- **Person** fills once there is a standing decision.

So `▮▮▯` is judged and waiting on you, `▮▮▮` is settled, and the difference between the
Attention and Settled filters is visible without reading a word. The words stay on the row
regardless — the spine is a scanning aid, never the sole carrier, per "a colour never
carries meaning alone".

This replaces the `opacity-60` treatment a decided row used to get, which said "less
important" rather than "further along".

## The status ribbon

Counts are orientation, read once, on the way to the work — the charter is explicit that a
number nobody acts on is decoration. So they are set like readings on an instrument rather
than in cards that ask to be looked at: values in mono on a rule, hairline ticks between
them, uppercase labels beneath.

"Decided by the team" is counted beside "judged", because how far through a review you are
is answered by the team's half and not by the model's.

## What is forbidden, and what enforces it

Every rule above was also a rule in the first system, written in a comment, and the accent
still reached 29 of 40 components one reasonable-looking commit at a time. So the ones that
can be checked are checked, in `ui/design-system.test.ts` beside the `ui/verdict-hues.test.ts`
that already guarded the other half.

| Rule | Why a comment was not enough |
| --- | --- |
| No `-accent` utility anywhere | The tokens are deleted, so a leftover `text-accent` compiles to nothing and vanishes in review rather than failing |
| `font-read` only on the model's voice | The serif is the whole thesis; spending it on a heading costs the one thing a reader can rely on |
| `--mark` only on something that navigates to a source, a policy or a cited finding | The moment it paints a button it is an accent again, and the argument for having it disappears |
| A shadow only on something that floats | A panel has a rule; `shadow-float` and `shadow-hero` belong to the drawer and the landing hero |
| No verdict hue outside a verdict | Existing rule in `verdict-hues.test.ts`, existing allowlist |

The `--accent*` tokens are deleted rather than deprecated. A token that still resolves is a
token somebody will use.

Syntax highlighting is under the same budget. `highlight.js` defines around forty classes
and the first system coloured six of them; an excerpt is measured material sitting a few
centimetres from a verdict, and a six-colour rainbow beside a three-colour severity scale is
two palettes arguing. It is now three values: a keyword carries its weight, a literal takes
`--mark` because it is usually the string a reader is scanning the excerpt for, and a
comment recedes.

## Region by region

Keyed to the names in [frontend-regions.md](frontend-regions.md).

| Region | What changes |
| --- | --- |
| **Sidebar** | Square, `--sheet-2`, rule instead of border. Active item is ink, not accent |
| **Topbar** | Model chips become mono; theme toggle unchanged |
| **Review head** | Title to 27px Archivo; meta line to mono; status keeps its verdict-scale hue |
| **Status ribbon** | Rebuilt as the instrument scale above; gains the decided count |
| **Surface tabs** | Ink underline, `--sheet-2` strip, 12px |
| **Attention queue** | Gains the spine; loses the opacity treatment; rows separated by rules, not cards |
| **Finding detail** | Rebuilt on the attribution gutter; provenance footer absorbed into it |
| **Context rail** | Now a drawer at every width, not only below `lg`. The gutter took the left margin and the finding is one reading column, so there is no inline margin left to put the case and the policies in at any size |
| **Decision bar** | Becomes the DECIDED block of the gutter. Its own border and its "· human" label went with it: the gutter already says DECIDED and already says by whom |
| **Clarification round** | Keeps its held tint — it is only ever shown while the review is held |
| **Delta / Evidence / Retrieval / Report / Ask** | Tokens and type only; no structural change |
| **Landing page** | Type scale and palette; the mock workbench inside it tracks the real one |
| **All workspace pages** | Tokens and type; accent chrome swept to ink |

## Test impact

- `ui/verdict-hues.test.ts` — extended with the three new rules. The allowlist stays.
- `features/review/overflow.test.tsx` — asserts on structural classes (`min-h-0`,
  `overflow-x-clip`, `line-clamp-2`). The queue and finding rework must preserve them; they
  guard real bugs that shipped.
- Everything else asserts on text and roles, and is unaffected by a presentational pass.

## What this does not change

No API shape, no domain record, no persisted field, no copy that a test asserts on. The
whole system is presentational — which is possible only because the three jobs were already
kept apart in the model. That is the second commitment paying for itself.

## Where this is still open

- **The gutter below `lg`.** Collapsing to a label strip keeps the sequence and loses the
  registration. Whether that is enough on a phone is not yet answered by anything but taste.
- **Newsreader at 17px on Windows.** Tested on macOS only. If the low contrast fails against
  a different rasteriser, the weight goes to 400 before the face does.
- **The Atlas surface.** It is the one region with no attribution, because exploring a
  structure is not one of the three jobs. It may need a fourth register, or it may need to
  stop being a surface.
