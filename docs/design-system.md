# The design system

What ArchCompass looks like, and why it looks like that.

Five documents describe the interface and they do not overlap. [The charter](charter.md)
says what the product is for and which rules settle an argument about it.
[The experience](experience.md) says what a person is trying to do and whether the screen in
front of them is helping. [Frontend regions](frontend-regions.md) is the vocabulary — what
each area on screen is called, so a sentence like "the docket row clips its own claim" means
one thing. [The landing page](landing-page.md) is the one surface with an argument to make
rather than work to do.

This one is the contract underneath all four: the tokens, the type roles and the structural
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

**Every element on screen belongs to exactly one of the three jobs, and says which.**

| Voice | Who is speaking | How it is set |
| --- | --- | --- |
| **Measured** | Deterministic analysis | Mono. Names, paths, counts, ids, provenance, evidence locations, measurements |
| **Judged** | The model | The reading size — 16px, the largest body text in the product — under a line naming the model that produced it |
| **Decided** | The person | Sans at control size. Buttons, labels, the record of what a person chose |

This is not decoration keyed to content; it is the product's structure made legible. A reader
who has read one finding knows the shape of the next: an `Attribution` line saying *whose*,
then the block.

It also constrains us usefully. When a new element does not obviously belong to one of the
three, that is a design question worth stopping on: something is being presented as fact that
is an opinion, or as a conclusion that is actually a control.

### The model's voice was a serif, and is not

The first version of this document made a serif the whole thesis: set the model's prose in
Newsreader, and there is no way to mistake a sentence the model wrote for a sentence the
analyser produced, because they are not in the same face.

It did not survive. A second face is a second face everywhere — it turned up in headings, in
empty states, in a policy title — and every one of those was a place where nobody was
speaking. What was left was a 187 KB payload buying an idea the interface had stopped
honouring, and a rule that could only be enforced by taste.

So the separation moved to things that cannot leak: **placement**, **the reading size**, and
**an attribution line**. The model's paragraph is the only text on the page set at 16px, it
sits alone in a band across the top of a finding, and the words `JUDGED · <model>` sit above
it. `ui/design-system.test.ts` — *"has no second face to reach for"* — now fails the build on
`font-read` and `font-serif` anywhere at all, and there is no `--font-read` token to reach
for either.

## Type

Two faces, both self-hosted as woff2 in `frontend/src/assets/fonts/`, latin subset, loaded
`font-display: swap` with a real fallback stack.

| Token | Face | Cut | Fallback |
| --- | --- | --- | --- |
| `--font-display` | **Onest** | Variable, 400–700 | `ui-sans-serif, system-ui, sans-serif` |
| `--font-ui` | **Onest** | the same face | `ui-sans-serif, system-ui, sans-serif` |
| `--font-code` | **IBM Plex Mono** | 400 and 600 static | `ui-monospace, "SF Mono", Menlo, monospace` |

`--font-display` and `--font-ui` resolve to the same family on purpose. They are kept apart as
names because they answer different questions — *what sets a number somebody reads at a
glance* and *what sets the interface* — and one of them may want to move later without
dragging the other with it.

Onest is a geometric-humanist sans with a tall x-height and unusually even colour, which is
most of what this interface asks of a face: it holds up at 10px uppercase letterspaced and at
16px in a paragraph without either looking borrowed from the other. IBM Plex Mono is picked
over the system stack because "whatever mono the reader has" is not a design decision.

No italic cut ships. The one place italics are wanted is a code comment, and there the
browser's synthetic slant is doing something honest — leaning a line that is already grey.

### The scale

| px | Face | Where |
| --- | --- | --- |
| 10 | Sans, 700, `0.13em` | Attribution voices, block labels, group headings — always uppercase |
| 11 | Mono | Provenance, meta lines, identities, namespaces |
| 12–12.5 | Sans / mono | Footnotes, counts, the docket's meta line |
| 13 | Sans | Controls, a docket row's claim, secondary body |
| 14 | Mono, 500 | A docket row's identifier; sans at 14 sets a notice |
| 15 | Sans, 600 | A panel's heading, and a section heading under a page title |
| 15–17 | Mono | The review head — the repository, branch and commit that identify a review |
| 16 | Sans, 400, `1.65` | **The model's reasoning.** Its own size, used nowhere else |
| 17 | Sans, 600, `-0.02em` | An app page's `h1`. It was 28px, which spent the largest type on the page on the word the reader is least in doubt about — they pressed the nav link that says it. The landing display is a different job and keeps its own row below |
| 34–62 | Sans, 600, `-0.035em` | Landing display only, `clamp()`ed |

Measure: the model's prose caps at `62ch`, and everything else between `60ch` and `64ch`. Digits that line up in
a column take `tabular-nums`. A qualified name is one token to the line breaker, so anything
that can hold one takes `wrap-anywhere` — this is the single most common overflow bug in the
product and `features/review/overflow.test.tsx` exists for it.

## Colour

**There is one hue, and everything wearing it means the same thing: look here.**

The accent is `#971b1a`, a dark red. The mark wears it, the primary action wears it, a link to
the source a claim came from wears it, a material finding wears it, and a review that is
running wears it — and `--material` is
declared as `var(--accent)` rather than as its own hex, so the alarm and the brand can never
drift into two reds that nearly match. Everything else on screen is grey: `ui/tokens.test.ts`
fails the build if any token outside the accent and the code palette has one RGB channel
differing from another by so much as a step. The bone the first system used was a second
temperature — it sat at the same warmth as the old `held` amber and cost that amber some of
its distance from the ground.

Two accent values, because a fill and a letterform want opposite things on a dark ground.
`--accent-fill` is the deep red in **both** themes — a mark that lightens in dark is a second
logo, and white on `#971b1a` clears 8.4:1 either way — while `--accent` itself lifts to
`#f27166` in dark, where the deep red drops to 2.3:1 and stops being text at all.

This is the second accent this system has had, and the first one reached 29 of 40 components.
So it comes back on a budget: `ui/design-system.test.ts` names the four files allowed to say
`-accent` (`ui/brand.tsx`, `ui/button.tsx`, `ui/tabs.tsx`, `ui/badge.tsx`), and the material
verdict is painted from a tone in `lib/format` and guarded by `verdict-hues.test.ts`. A
focus ring is deliberately *not* on that list: it answers "where is the keyboard", which is a
question about the reader rather than about the content, and a red ring makes every tab press
read as a validation failure.

One rule orders the ramp in both themes: **light means elevation.** In light that reads as
white on grey. In dark it reads as a film of white laid over the void — the same rule running
the only direction it can once the ground is already at the bottom, which is why `--sunken` is
the *brightest* of the four greys in dark. Nothing is darker than the page; a hole is not a
thing you can dig at the bottom.

| Token | Light | Dark | For |
| --- | --- | --- | --- |
| `--canvas` | `#f5f5f5` | `#000000` | The page |
| `--surface` | `#ffffff` | `#0d0d0d` | A panel, a docket row that is open |
| `--surface-2` | `#fafafa` | `#141414` | A strip inside a panel — the measured half of a finding |
| `--sunken` | `#ebebeb` | `#1f1f1f` | A quiet inset: a hover, a code block |
| `--overlay` | `rgb(0 0 0 / 45%)` | `rgb(0 0 0 / 72%)` | Behind a drawer |
| `--chrome` | `rgb(255 255 255 / 72%)` | `rgb(0 0 0 / 62%)` | The one deliberately see-through surface, blurred `22px` |
| `--control` | `#ffffff` | `rgb(255 255 255 / 7%)` | The fill of something you operate |
| `--control-2` | `#ebebeb` | `rgb(255 255 255 / 13%)` | Its hover |
| `--rim` | `transparent` | `rgb(255 255 255 / 8%)` | The light along a surface's top edge |
| `--rule` | `rgb(0 0 0 / 10%)` | `rgb(255 255 255 / 11%)` | Hairlines — the primary structural device |
| `--rule-strong` | `rgb(0 0 0 / 15%)` | `rgb(255 255 255 / 17%)` | A border on something you could pick up |
| `--ink` | `#0a0a0a` | `#fafafa` | Body |
| `--ink-2` | `#525252` | `#a1a1a1` | Secondary |
| `--ink-3` | `#5f5f5f` | `#8f8f8f` | Meta — measured against all four grounds, not eyeballed |
| `--accent` | `#971b1a` | `#f27166` | The one hue: a letterform, an icon, an indicator |
| `--accent-fill` | `#971b1a` | `#971b1a` | A solid fill — the mark, the primary action. Does not move between themes |
| `--accent-on-fill` | `#ffffff` | `#fafafa` | What sits on that fill |
| `--material` | `var(--accent)` | `var(--accent)` | Act on it |
| `--held` | `#0a0a0a` | `#fafafa` | Waiting on a person — full ink, present, not an alarm |
| `--cleared` | `var(--ink-3)` | `var(--ink-3)` | Settled, and settled things recede |

**Two of the three verdicts gave up their hue, and this cost something real.** The scale was
red, amber and green; it is now one hue and two weights. What that buys is that red is never
ambiguous — nothing else on screen is coloured, so the eye goes to the one thing asking to be
acted on. What it costs is that a docket column no longer separates *held* from *cleared* at
the edge of vision, and the mark, the word and the left edge have to carry that on their own.
That trade was made deliberately, not discovered.

The accent and each verdict also have a `-soft` wash for a panel whose entire subject is that
state — 8% in light, 13% in dark for the accent; a neutral 3–8% for the two that are grey.
Nothing else gets a wash.

A permanently dark strip has its own four tokens — `--band`, `--band-ink`, `--band-ink-2`,
`--band-rule` — because the topbar and the landing page's field band do not invert with the
theme and therefore cannot borrow `ink`/`surface` from the page. It has a fifth,
`--accent-on-band` (`#f27166`), for the same reason: the deep red is 2.35:1 on `#0a0a0a`.
Nothing paints it directly — `.on-band` is what hands it to `--material` and to `--accent`.

### `--mark` is the accent's fourth job

Navigating to the thing a claim came from — a file, a policy, a cited finding — is one of the
four places the accent is spent, and `--mark` is the name it is spent under. It resolves to
`var(--accent)`.

The name survives for the reason it always did: it keeps the decision in one place instead of
being re-made beside every path reference, and it means changing where the accent points is
one edit rather than a search. The guard in `ui/design-system.test.ts` protects the name: five
files may say `-mark`, and three of them do.

### A running review is the accent's fifth job

The topbar's run indicator — a breathing 6px dot beside "1 review running" — is the accent,
and it is the newest entry in the budget. It is worth stating why it is not a verdict, because
the cheap version of this change was to give it `tone="material"`: same red, no `-accent`
string, no test anywhere would have failed. `material`, `held` and `cleared` are a severity
scale, and a review that is running has judged nothing yet, so grading it is a claim the
result may contradict a minute later. The same rail already spends `material` on a recorded
provider failure a few centimetres away; two identical dots in one bar, one meaning "your
reasoning provider returned 401" and one meaning "work is in progress", is the hue being spent
on something else in the one shape a line-by-line guard cannot see.

So it is spent as what it is. The accent means *look here*, and a review in flight is the one
thing in the rail worth crossing the room for. `StatusDot` takes a `running` value in its own
prop type — deliberately **not** a sixth `Tone`, so it cannot reach `Badge` or `ui/meta.tsx` —
and paints `bg-accent`. `ui/badge.tsx` is on the `-accent` allowlist for that one line.

The dot needs `.on-band` to be legible at all, and this is the general rule for the topbar
rather than a detail of this dot. `--accent` inverts with the *page*; the band does not invert.
On a light page an unlifted accent dot is `#971b1a` on `#0a0a0a` — **2.35:1**, a smudge, while
the identical dot measures 6.91:1 in dark. `.on-band` remaps `--accent` to `--accent-on-band`
(`#f27166`, **6.91:1** in both themes, slightly brighter than the `#8f8f8f` dot it replaced at
6.12:1). `--accent-fill` is no rescue here: it is the deep red in both themes by design, so it
fails on the band in *both* rather than in one. And the lift belongs on the band, not in the
component: the same `StatusDot` renders on a page surface in the phone drawer, where `#f27166`
measures 2.63:1.

### The one exception: a source excerpt

Code is coloured, and it is the only thing on screen that is. The exception is narrow enough
to state in a sentence: **three cool hues, inside a monospace block, never anywhere else.**

The reason it earns one is that an excerpt asks a question the rest of the interface does
not. Everywhere else, a reader arrives already knowing what they are looking at — a badge, a
path, a count. Inside forty lines of Python they are looking for something else entirely:
which of these tokens is a name somebody in this repository chose, and which is the
language's own furniture. Weight cannot answer that. Half of Python is a keyword, and a page
of bold is a page of nothing.

Four roles, from roughly thirty token classes the highlighter emits:

| Token | Role | Light | Dark |
| --- | --- | --- | --- |
| `--code-keyword` | the language's own words — `def`, `class`, `return` | `#7e22ce` | `#d8b4fe` |
| `--code-name` | what somebody named — a function, a class, a tag | `#1d4ed8` | `#93c5fd` |
| `--code-lit` | what is written out — a string, a number | `#0e7490` | `#67e8f9` |
| `--code-comment` | prose inside code; the only neutral, and italic | `#5f5f5f` | `#8a8a8a` |

Everything the highlighter emits outside those four inherits the block's ink. Colouring all
thirty classes produces an excerpt harder to read than the editor it came from.

The accent rule is not suspended, because it was never a rule about abstinence — it is a rule
about *hue*. Red means look here. So the code palette lives on the cool half of the wheel,
where the accent never goes, and the closest any of the six values comes to it is the 85
degrees between violet and `--accent` in light, 81 in dark. A keyword cannot be misread as a
material badge, because no badge is ever violet. `tokens.test.ts` asserts that distance rather
than trusting six hex codes to hold it.

The argument used to be made against a green `cleared` 42 degrees from cyan, which was the
tightest pair in the set. Held and cleared gave up their hues, so the set is wider now — and
the bar stays at 35 degrees, because it was never sized to the comfortable case.

The highlighter is a tokeniser only. It emits `hljs-…` class names and `styles.css` gives
them colour, so no highlight.js stylesheet is imported and a keyword follows the workspace
theme. It never guesses a language: an excerpt is coloured from the extension of the file it
was read out of, a fence from its own label, and anything else is left plain. Code shown in
the wrong colours is worse than code shown in none, because the colours are a claim about
what the tokens mean.

### Marks: what a thing is allowed to wear

Marks are **Lucide**, resolved from a fixed vocabulary in `ui/mark.tsx`. They have been three
things: literal characters (`▲ ◆ ●`), which broke because neither Onest nor IBM Plex Mono
ships the Geometric Shapes block, so every one fell through to whatever the operating system
had; then hand-cut SVG, which fixed the sizing and left the real problem; and now a library.

The rule that survives all three is the one `ui/design-system.test.ts` enforces: **a mark is
drawn, never typed.** The build fails on any source line carrying one of those characters,
comment lines excepted.

What this file keeps, and a library cannot supply, is *which* icon a thing is allowed to
wear. Three registers, and the separation is load-bearing:

| Register | Wears | Worn by |
| --- | --- | --- |
| **A sign** | caution triangle, pause, tick — plus a run's spinner, cross and stop | What is **graded**: the model's three verdicts, and a review's own state |
| **A step on a scale** | filled dot, outline, dashed outline | A position that is not a grade — chiefly how binding a policy is |
| **A person's move** | flag, clock, slash | What somebody decided |
| **A difference** | plus, minus, swap, equals | How a candidate moved between two reviews — the Delta surface |

The registers exist because of two things the product must never say:

- **A required policy is not an alarm.** `required` / `preferred` / `guidance` is emphasis —
  the policy to read first, not a problem — so it carries no chroma *and* no caution sign.
  Solid, outline, dashed is a scale and nothing more.
- **Accepting a finding is a commitment to act on it,** not a report that it went away, so a
  disposition may not wear the tick either. A decision may share a verdict's *tone*, because
  it answers one — never its mark. This is where the charter's separation between the model's
  verdict and the person's decision becomes visible.
- **A delta is a comparison, not a grade.** "Raised last time, gone now" is not the same claim
  as "assessed and found unproblematic", so `addressed` is a minus beside a plus rather than
  the tick it carried for months. Diff notation reads as a diff, at a glance, and says nothing
  about whether the candidate was any good — which is also why **none of the four carries a
  hue**. A changed candidate can come back material, held or cleared, so tinting the *movement*
  would be the surface guessing at the outcome. See below.

### One coloured thing per row, in one place

The Delta surface is where this rule was worked out, and it generalises. Every row there now
carries exactly one coloured element — the badge saying where the candidate stands, in the
verdict's own hue — and everything else on the row is ink. The movement glyph is a weight
ramp: `addressed` and `changed` at full ink because both want re-reading, `new` at `ink-2`
because it is also sitting in the docket, `unchanged` at `ink-3`.

Getting there fixed a real bug rather than a cosmetic one. `addressed` used to tint its glyph
`text-cleared`, defensible at the time because that row is the one state with no verdict badge
to carry colour — there is no finding, the candidate is gone. The better answer was to **give
it a badge** (`No longer detected`, cleared tone, in the slot every other row fills with its
verdict) instead of tinting a glyph. The state the experience doc calls the only one that
exists nowhere else in the product had been the dimmest row on the page.

That took `features/review/surfaces.tsx` off the `verdict-hues.test.ts` allowlist: it names no
hue at all any more, because `<Badge tone="cleared">` lets `ui/badge.tsx` do the painting. An
allowlist entry that has stopped being load-bearing is worse than no entry — it silently
licenses the next hue somebody adds to that file — so entries are expected to come off it.

Two sizing facts, both learnt the hard way. Lucide draws at stroke 2 on a 24 box, tuned for
20–24px; **`Mark` overrides to 2.25**, because almost nothing here renders that large and a 2
arrives thin and grey once scaled down. And **nothing below 12px** — the marks used to be
9–13px, which is a size at which no line icon survives and the reason they were hand-cut
filled shapes in the first place. A verdict on a docket row is 15px, dense counts are 13px, a
badge's is 1.25em.

### The verdict as an edge

A docket row states its verdict three times: a sign, a word, and a **3px left edge** in the
verdict hue (`TONE_EDGE` in `ui/meta.tsx`, the only other place besides `TONE_TEXT` that
names the hues). The edge exists because the question asked of a whole column at once — where
does the red start — is not one a mark inside a row can answer. At any size that fits beside a
name, a glyph has to be looked *at*; an edge is read without being looked at, costs no
horizontal space, and is a rule rather than a card, which is the structure this system already
uses everywhere else.

A settled row's edge goes transparent rather than absent, so nothing shifts sideways when you
decide something. The list of edges is then exactly the list of what still wants you.

### "You are here" is an underline, never a container

The candidate trajectory used to ring the revision you were reading. That stopped working the
day the verdict marks became circles: a ring around a circle is two concentric circles and
says nothing. It is now the device the system already had — **an underline and weight** — with
the rest of the lineage receding to 45%.

The general rule, worth applying before reaching for a box: mark the present by taking
emphasis off everything else, not by adding chrome to it. A container around a mark competes
with the mark; contrast does not. The lineage rail is the exception that proves it — it rings
a plain dot, and a ring around a dot is a halo rather than a nested shape.

### A toggle that is on is raised, not inverted

A pressed filter used to be `bg-ink text-canvas` — the loudest fill the system can draw. One
of them is a strong signal. The atlas has eleven in three rows, and the default state of the
relationship filters is *all of them on*, so the surface opened as a wall of solid black
slabs in dark and solid white ones in light, none of which anybody had chosen.

A toggle that is on now wears the `secondary` button's recipe: the control film, a hairline,
a rim along the top edge, full-strength ink. A toggle that is off is plain text with no
border at all. The state is carried by **an edge appearing**, not by a fill inverting, and
that is deliberate — in light the control film *is* the panel colour, both are white, so a
filled-versus-unfilled distinction is invisible there however it is written. An edge is
legible on both grounds. One gesture, not one colour.

The same recipe is in two places on purpose: `ui/button.tsx`'s `ToggleButton`, and
`components/ui/toggle.tsx` for the vendored Radix switch. Two toggles that look different are
two toggles a reader has to learn separately.

### shadcn components are vendored and repainted

`components.json` and the `@/*` alias were already here; `src/components/ui/` is the first
thing to use them. What the registry is for is the *behaviour* — roving focus, arrow-key
traversal, a listbox that is real markup, a pressed state announced as a toggle — and that is
all that is kept. Every colour is rewritten onto this system's tokens before the component
ships, because the registry paints with `bg-muted`, `text-foreground` and `border-input`, none
of which are defined in this project. A vendored file that kept them would be a second,
silent theme, and `design-system.test.ts` scans all of `src/` — including `components/ui/` —
so a registry file that arrived with `focus:bg-accent` and `shadow-md` fails the build rather
than quietly establishing one.

`lib/utils.ts` re-exports `cn` under the path the registry imports it from, so the next
`shadcn add` compiles without a hand-edited import line.

Two are in: `ToggleGroup` (the atlas lens, the relationship filters, the framing controls) and
`Select` (the highlight menu). The `ToggleGroup` variant is about the *set*, not the switch —
`segment` is one-of-many and gets a sunken track, `chips` is many-of-many and gets none,
because a bar drawn around switches that can all be on at once claims a choice between them
that does not exist.

## Structure

### Hairlines, not cards on cards

A rule separates; a border belongs to something you could pick up. That distinction does most
of the structural work, and it is why the finding's two halves are one grid divided by
`border-rule` rather than two panels with a gap.

### Radius means what it is, not what it does

The first system made radius near-zero and square-cornered every structural container, on the
argument that square means "structure, not a control". That reads as a rule you have to be
told. The five steps are five real values again, and the step says how large the thing is:

| Token | px | For |
| --- | --- | --- |
| `--radius-xs` | 4 | A tick, a dot, a tag |
| `--radius-sm` | 6 | A control you can operate |
| `--radius-md` | 10 | A block inside a panel |
| `--radius-lg` | 14 | A panel |
| `--radius-xl` | 20 | A surface a panel sits on |

`rounded-full` is for a thing whose shape is the point: a status dot, a spinner, a badge pill,
a timeline node, a trajectory node.

### Two elevation devices, and the difference is the whole rule

A **rim** is the edge of a surface: one inset hairline of light along the top, no blur, no
offset. It lifts nothing and costs nothing, so any surface may have one — it is how a panel
says where it begins on a ground too dark for a hairline to carry alone. In light `--rim` is
`transparent` on purpose: there is nothing to catch, and the surface is already the brightest
thing on screen.

A **lift** is for something that genuinely left the page. Three things do: the drawer, the
command palette and the landing page's specimen card. `ui/design-system.test.ts` holds that
line with an allowlist, and a second test forbids hand-rolled inset shadows so that a second,
slightly-different rim cannot get into the system.

The recipes are theme-split, because a black blur on a black ground draws nothing:

```
light  --shadow-float: inset 0 1px 0 var(--rim), 0 1px 2px rgb(0 0 0 / 5%), 0 12px 32px rgb(0 0 0 / 9%)
dark   --shadow-float: inset 0 1px 0 var(--rim), inset 0 0 0 1px rgb(255 255 255 / 6%),
                       0 24px 60px -20px rgb(0 0 0 / 85%)
```

`--shadow-hero` is the same shape with a longer, softer throw.

## Motion

Seven animations, one easing curve, and a hard stop for anyone who has asked for less.

| Token | Duration | Where |
| --- | --- | --- |
| `--animate-expand` | `0.24s ease-out` | A docket row opening, a waiver's reason field |
| `--animate-slide-left` | `0.28s` | A drawer arriving |
| `--animate-slide-up` | `0.30s` | A sheet |
| `--animate-fade` | `0.32s ease-out` | A panel that replaced another |
| `--animate-rise` | `0.42s` | The landing page's first paint |
| `--animate-shimmer` | `1.5s`, infinite | A loading placeholder |
| `--animate-breathe` | `2.4s`, infinite | A run in flight |

Everything that is not a loop uses `cubic-bezier(0.22, 0.7, 0.3, 1)`. Under
`prefers-reduced-motion` every duration collapses to `0.001ms` — the state still changes, the
travel does not.

There was briefly an eighth — `slide-right`, the mirror of `slide-left` — for a clarification
round that swapped one question for the next and needed the swap to say which way it had
gone. The round is a stack now and nothing swaps, so the token went with the thing it was
for. Motion that exists to make a transition survivable is worth asking whether the
transition should happen at all.

## The counts under the review head

*Not a dashboard. Counts are orientation, read once, on the way to the work.* The five-cell
status ribbon is gone. What is left is one wrapping line: **how many things still want you**,
in plain ink, then the verdict spread with its glyph, its number and its word.

The leading count is deliberately plain ink even where most of what it counts is material — a
hue on a mixed total would be a verdict painted on something that is not one. A zero recedes
on a laptop and disappears below `sm`, because "0 material" is worth a glance where there is
room for the whole scale and a line of the viewport spent saying nothing happened where there
is not.

## What is forbidden, and what enforces it

Every rule below is a test in `frontend/src/ui/design-system.test.ts`, `ui/tokens.test.ts` or
`ui/verdict-hues.test.ts`. Each was a rule in a comment first, and each shipped broken anyway.

| Rule | Why it is a test |
| --- | --- |
| `-accent` in four files only | The first accent reached 29 of 40 components, every one a local decision that looked reasonable. The budget is the rule; the allowlist is the enforcement. `ui/badge.tsx` is the newest entry and buys one line — the running dot; a badge or a wash reaching for it there is the first accent growing back |
| `--material` is `var(--accent)`, never a hex | A second red a hex away from the first is two reds that nearly match — a material badge and the button beside it. `tokens.test.ts` asserts the alias |
| `--held` and `--cleared` carry no chroma | They are weight now. `tokens.test.ts` fails either one at an OKLCH chroma above 0.01 |
| No second face — no `font-read`, no `font-serif` | The model's voice is placement, attribution and the reading size. A face leaks; those do not |
| No chroma outside the accent or the code palette | Any other token whose RGB channels differ fails `tokens.test.ts`. A bone is a temperature and a temperature is a colour |
| Code colour stays off the accent | The exemption above is from *being grey*, not from the hue rule. `tokens.test.ts` fails a `--code-*` hue within 35° of the accent in either theme — the cool half of the wheel is where the syntax palette lives |
| No verdict hue outside a verdict | `verdict-hues.test.ts`, with a ten-file allowlist that a second test checks still names real files |
| `-mark` only where something goes somewhere | Five files, allowlisted. The name is the decision; without the guard it becomes a synonym for ink |
| A mark is drawn, never typed | A pasted `▲` falls back to the system font and breaks the set. Three blocks — arrows, ticks and crosses, geometric shapes — because covering only the third let the Delta surface keep `✓` and `→` underneath the guard for months. Comment lines are skipped: a doc comment naming the marks it draws is a description, not the thing. An *ASCII* character used as an icon (`~`, `+`, `=`) is the same defect and is not catchable — that half is review |
| Lift only what leaves the page | Three files. Structure is separated by a rule and a rim |
| One rim, from the token | Two rims a percent apart read as a rendering bug rather than as a decision |
| No `line-clamp` on a `display: flex` box | They collide silently — the clamp is ignored and the row grows |

## Where this is still open

- **Onest's numerals.** They are proportional by default and the interface asks for tabular
  everywhere a count sits in a column, which is a utility on every one of them rather than a
  font feature set once. If a column of digits is ever seen to jitter, the fix is
  `font-variant-numeric` on the token, not another `tabular-nums`.
- ~~**`--ink-3` is the same value in both themes.**~~ **Settled.** It was `#737373` in both, on
  the argument that sitting near the middle made it read correctly on either ground. Measured,
  it cleared 4.5:1 on two of its eight ground-and-theme pairs — 4.35 on the canvas in light,
  3.48 on a sunken block in dark — and it carries the docket's meta line, every `Label` and
  every empty state, so the tier that explains the interface was its least readable text. It is
  now `#5f5f5f` and `#8f8f8f`, both clearing 5:1 on all four grounds of their own theme.
  `--cleared` was a hardcoded copy of the old value and drifted when the tier moved, which is
  why it is now `var(--ink-3)` — the same relationship `--material` has to `--accent`, for the
  same reason. `ui/tokens.test.ts` measures the whole ramp against every ground rather than
  trusting a value to stay legible after a ground moves under it.
- **The dark ramp's four greys are close.** `#0d0d0d`, `#141414` and `#1f1f1f` are three and
  eleven steps apart, which holds on a good display and is the first thing to give way on a
  cheap one. The rim is what carries the separation there, and it is doing more work than a
  colour ramp should have to delegate.
