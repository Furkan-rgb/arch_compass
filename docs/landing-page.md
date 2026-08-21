# The landing page

What `/` shows, why it shows that and not something else, and the things that will break
quietly if somebody changes them without knowing.

[The charter](charter.md) says what ArchCompass is for and what it refuses to be — every
argument on this page is downstream of it. [The design system](design-system.md) owns the
token layer, the type roles, the three voices, the marks, the radius ladder, the two
elevation devices and the enforcement table; nothing here re-explains any of that, and where
this page uses one it names the section. [Frontend regions](frontend-regions.md) lists the
Landing page as one route and stops there, which is why this document exists.

The landing page is the only surface in the product with no data behind it. Every other
screen is handed a `Review`, a `Finding`, a `Policy`; this one is written out by hand. That
makes it the easiest page in the repository to make a false claim on, and most of what
follows is about not doing that.

## The thesis

**The hero shows the artefact, not the application.**

The deterministic half of this product is the half nobody believes. "We parse your
repository, we never import it and never run it" is a sentence, and every tool says a
sentence like it. So the hero draws the thing that sentence describes — modules, nodes,
edges, built before a model is asked anything — and pins one finding to one node of it. The
copy claims; the figure is the receipt.

A screenshot of the workbench would have been the obvious alternative and it is the wrong
one twice over. It shows the product's chrome rather than its argument, and it is a picture
of a screen a first-time reader has no way to read. The atlas needs no key: a reader who
has never seen ArchCompass can see that something was mapped, that one thing on the map was
singled out, and that what was said about it names a policy somebody wrote.

Two lines hold the rest of the page in place:

- **`Weighed, not enforced`** — the eyebrow. It is the charter's "not a linter" said in
  three words, at the top, before the headline.
- **`Three verdicts, no score`** — the tail of the picker. There is no magnitude anywhere on
  this page because there is no magnitude anywhere in the domain: `FindingOutput.material`
  is a bool and `Verdict` has three values. See *Honesty* below.

The chrome is deliberately not the app's chrome. `AppShell` is a topbar because the
workbench is a tool somebody works inside; a marketing page is read top to bottom and wants
a horizontal nav and a footer. What the two share is what should be shared: the wordmark,
the tokens, the type and the buttons.

## The three directions, and why B

Three hero directions were drawn at 1440 and again at 390 before one was built. All three
used the same headline, the same lede, the same two calls to action and the same specimen
finding, so what was being chosen was the picture and nothing else.

| | The picture | Why it was worth drawing | Why it was not built |
| --- | --- | --- | --- |
| **A · Field** | The aurora from the `intent` band moved up into the hero, dark, with the specimen card overhanging the boundary into the lit page | The strongest image the system already owns, and it is the product's own metaphor — the field was always there, the light only lets you read it. Costs no new asset; same canvas maths as `field.tsx` | The page would open dark and turn light, and the band below would lose the one atmospheric moment on the page. Spending the image twice makes it worth less in both places |
| **B · Atlas** | The deterministic map in hairline ink: modules enclosing nodes, edges between named elements, three nodes carrying a verdict, one callout pinned to the candidate | It *shows* the deterministic half instead of claiming it, and it earns the "parsed, never imported and never run" line standing beside it | **Built.** The cost is real: a node graph is the most-used visual in developer tooling, and it implies a graph view the product does not ship |
| **C · Corpus** | All 54 bundled policy titles as the ground, in mono, held back to a whisper; one lit, with a hairline carrying it down into the verdict it produced | It draws the thesis rather than stating it — write it once, and one of them bears on this candidate | The quietest of the three at a glance, and it leans on type alone to be impressive |

A rejected direction with its reason attached is what stops it being re-proposed every
quarter, so all three artboards and their notes are the record. Two things about the losers
are worth knowing, because they are still on the page:

- **A did not die.** `features/landing/field.tsx` still draws the ribbon field, in the
  `intent` band, which is where it was already. Rejecting A was rejecting *moving* it.
- **C's argument did not die either.** It survives as the callout's head: the strength, the
  policy title and the policy id sit above the verdict, so the finding is read after the
  thing it rests on rather than before it. The first drawing of B (`Atlas.dc.html`) had no
  policy head — the id was a fragment in the footer — and the shipped version took C's
  ordering. Compare `Atlas.dc.html` with `AtlasRed.dc.html` to see the move.

**What holds B's cost down.** The graph reads as an artefact rather than as a feature
because it is not interactive, not zoomable and not navigable: `AtlasMap` is
`pointer-events-none` and `aria-hidden`, the only thing that changes is which node is lit,
and the change is driven from the picker rather than from the map. Nothing on it invites a
click, so nothing promises a graph view. If that ever stops being true — a hover state, a
tooltip, a node that opens something — direction B's tradeoff has been re-taken without
anybody noticing.

## The anatomy of the hero

Five pieces, and the point is that the first four are **one statement**, not four components
that happen to sit near each other.

| Piece | Where | What it is |
| --- | --- | --- |
| **The copy column** | `landing-page.tsx`, `Hero` | Eyebrow, headline, lede, one primary action, one text link, the trust line |
| **The map** | `atlas.tsx`, `AtlasMap` | 4 modules, 15 nodes, 25 edges, drawn in a 900×700 viewBox. Three nodes carry a verdict; everything else is hairline |
| **The callout** | `specimen.tsx`, `SpecimenCallout` | The policy that bore, then the finding it produced, then the two retrieval counts. The one lift on the page |
| **The leader** | `atlas.tsx`, `Node.leader` | A dashed hairline from the lit node to the callout's corner |
| **The picker** | `specimen.tsx`, `SpecimenPicker` | Material · Held · Cleared, as the map's legend *and* as the control that moves between the three specimens |

### One statement, and what makes it one

`BEARINGS` in `bearings.ts` carries a `node` field. It is the only field on that record with
no counterpart on the wire, and it exists so the map and the callout read from the same
index: `useSpecimen()` returns one `index`, `AtlasMap` lights `bearing.node`, and
`SpecimenCallout` shows the specimen at the same position. Render them from separate state
and the hero is back to claiming the deterministic half rather than showing it — which is
why `landing.test.tsx` asserts that clicking *Held* in the picker both lights `orders` on
the map and puts `orders.Repository` in the callout.

### The picker is the legend

These were two things once: a legend under the copy naming the three verdicts, and a tab
strip across the bottom of the card. They said the same three words a hand's width apart.
One control that does both is not a saving, it is the honest shape — "what does the red node
mean" and "show me the red one" are the same question asked twice.

It also stands exactly where the invented metrics ribbon used to stand, under a
`border-t border-rule-strong`. That was not an accident of layout; see *What was removed*.

## The invariants

Each of these is load-bearing and none of them announces itself. Changing one without
knowing costs an afternoon of wondering why the figure is subtly wrong.

### The map's lower-right quadrant is empty on purpose

`NODES` puts the graph on an arc across the top and down the left. Nothing sits below and
right of roughly (350, 330) in the viewBox — that region is where the callout lands. A map
drawn without room for it would have a finding covering half its own evidence.

Adding a node there is the single easiest way to wreck this figure, and it will look
perfectly reasonable in the SVG on its own.

### The aspect ratio and the viewBox are the same coordinate space

The callout is HTML and lives outside the SVG. It pins to a node inside it because both are
addressed in the same fractions:

```
ATLAS_VIEWBOX = { width: 900, height: 700 }   atlas.tsx
ANCHOR        = { x: 320,   y: 330 }          atlas.tsx

left: (320 / 900) * 100 = 35.56%              landing-page.tsx
top:  (330 / 700) * 100 = 47.14%
```

The box holding both carries `xl:aspect-[900/700]`, so a percentage of the box and a
fraction of the viewBox are the same place. **If the viewBox changes, the aspect ratio has
to change with it**, in `landing-page.tsx` and on `AtlasMap`'s own `aspect-[900/700]`, or
the callout drifts off the end of its own leader. The percentages are computed from the
constants rather than written out precisely so that only one of the two can be forgotten.

`ANCHOR` is where the callout's top-left corner sits and therefore where every leader ends.
The callout stays put and the line re-aims when the specimen changes; the other way round —
a callout that jumps to whichever node is active — moves the one block of text on the figure
somebody is trying to read.

### The three leaders are authored, not computed

`Node.leader` is a hand-written path per verdict node:

```
gateway  M330 195V330    straight down
invoice  M665 145V330    straight down
orders   M110 340H320    straight across
```

A generated elbow has to pick a direction it cannot know is free, and the three nodes sit in
three different relations to the anchor: two above it and one beside it. Three short paths
drawn on purpose beat one rule that is wrong a third of the time. A fourth specimen needs a
fourth path, written by hand, or it gets no leader at all.

The leader is dashed. Solid, it was the same mark the edges are drawn with and it
disappeared into the very edges it runs beside; a dash reads as annotation rather than as
something the atlas contains.

### The callout is one height because all three specimens are laid out

`SpecimenCallout` renders every bearing into one grid cell (`col-start-1 row-start-1`) and
hides the inactive two with `invisible` — `visibility: hidden`, which keeps the box and its
height. The grid track is therefore as tall as the tallest specimen and nothing moves when
the cycle advances.

This replaced a `min-h-[684px]` measured off one browser at one text size, with three pixels
of headroom. At a 20px root size the *held* specimen wrapped one extra line, grew to 701px
and shoved the rest of the page down every six seconds. A layout that has to be re-measured
whenever the copy or the font changes will be wrong again.

`landing.test.tsx` cannot measure anything in jsdom, so it asserts the mechanism instead:
all three policy ids are in the document at once, and exactly one specimen is exposed as a
group. Render only the active one and that test fails.

`invisible` is not enough on its own for tooling that walks the DOM rather than the render
tree, so the hidden two also carry `aria-hidden`. That is what lets every query in the test
file be scoped by `getByRole("group", { name: /^(Material|Held|Cleared)$/ })`.

### `xl` is where the figure stops being pinned

Above `xl` (1280px, the Tailwind default — this project does not override the breakpoints)
the figure is taken out of the flow and bleeds off the right edge:

```
xl:absolute xl:left-[50%] xl:right-[-6%] xl:top-4 xl:max-w-[56rem]
```

Because nothing tall is left in the section to measure it, the section carries
`xl:min-h-[55rem]` — 880px, which is what the figure needs. That minimum exists *only* for
the absolute case and never applies below `xl`, where the copy and the figure stack.

Three things switch at that same breakpoint and they switch together:

- the map goes `xl:absolute xl:inset-0 xl:aspect-auto` and lets the container hold the ratio;
- the callout goes `xl:absolute` and its inline `left`/`top` start meaning something. Below
  `xl` the element is static, so those two declarations are inert rather than conditional —
  which is why they are written unconditionally;
- the leader appears. `Node.leader` renders with `hidden xl:inline`, because below `xl` the
  callout sits underneath the map and there is nothing for a line to point at.

Moving any one of those to a different breakpoint without the others produces a leader that
points at nothing, or a callout stacked on top of the map.

### Exactly three nodes are lit, and the tone comes from a table

Three nodes carry a verdict because three findings are on show. Every other node is ink. A
map where everything is lit is a map that has said nothing.

`atlas.tsx` paints from `TONE`, keyed by the verdict, in the same way the badges do: nothing
in that file decides that a shape should be red, it paints the tone a finding already has.
The verdict tokens are reached through `var(--material)` / `var(--held)` / `var(--cleared)`
rather than through Tailwind classes, which means `verdict-hues.test.ts` does not see them —
the guard is the table, not the test. Write a hex at a node and nothing will fail.

Two more details that are meaning rather than style: the lit node's ring goes to 0.75 opacity
and the other two verdict nodes' rings sit at 0.3, and the edges touching the active node
come forward to `--ink-3` at 1.25 while every other edge stays `--rule-strong` at 1. The
edges into and out of the candidate are the ones the finding is about.

## Honesty: everything on this page maps to a real record

**A hero that invents a field is a promise the product cannot keep.** Somebody reads the
figure, starts a review, and the shape they were shown does not exist. That is a worse
outcome than a duller hero, so the rule is absolute and `bearings.ts` documents it field by
field:

| Field | What it stands for |
| --- | --- |
| `policy` | A `Policy`. All three quoted are real bundled ones, **verbatim** from `src/archcompass/policies/general/*.md` |
| `origin` | `PolicyOrigin` — bundled corpus, or this workspace's own directory |
| `retrieved` vs `also` | `RetrievalProvenance.selected_policy_ids.length` against `Finding.policies.length`. Retrieval pulls several; only some bear |
| `reasoning` | A `PolicyBearing.reasoning` — the model's account of how *this* policy bore on *this* candidate. Not the policy's text |
| `verdict` | A three-value `Verdict`. There is no score, because `FindingOutput.material` is a bool |
| `hinge` | What the judgement is waiting on. Only the *held* specimen carries one, which is what *held* means |
| `node` | The one field with no counterpart on the wire. See *One statement* above |

Three consequences worth stating separately, because each is a thing somebody will want to
add back:

- **`6 retrieved · 2 bore on the judgement` is the most honest number on the page** and both
  halves have to stay. Printing only the first overstates how much of the corpus was
  weighed. `landing.test.tsx` asserts the exact string.
- **The policy has to be one that ships.** `landing.test.tsx` names
  `delay-premature-abstraction` and its title. Inventing a plausible policy id would pass
  every visual review and be a lie.
- **`PolicyBearingResponse` carries `policy_id`, `policy_title` and `reasoning` and nothing
  else**, so a real finding surface could not quote a policy body even if it wanted to. The
  hero must not either — the callout shows the policy's *title* and *id*, never its
  description. Direction A and direction C both showed the description, and both were
  rejected for other reasons; do not import that detail from the artboards.

The `FindingSection` further down the page is under the same rule. Its counts
(`Implementations 1`, `External callers 5`, `Provider terms in domain 3`), its excerpt, its
attribution lines (`sole_implementation`, `detector v1.4.0`, `8f31c2a`, `google:gemini-3.6`,
`judge:v1`) are shaped like the records they stand for, and its three decision controls are
painted with `buttonClass("primary" | "secondary", "sm")` from `ui/button.tsx` rather than
by hand — a hand-rolled copy of a control is a copy that stops matching the day the primary
action changes colour, which is exactly what happened when the palette shipped.

## What was deliberately removed, and must not come back

### The metrics ribbon

The hero used to carry five readings under the lede: `Examined 12 · Material 4 · Held 3 ·
Cleared 5 · Decided 0`. Every one of those numbers was invented, and they described a review
the reader had not run.

The page's own *refusals* section says, in the charter's words, that a number nobody acts on
is decoration. On a landing page nobody can act on any of them. It went, and the specimen
picker stands in its slot — a control that does something, in the place a fake dashboard
used to be.

### The second primary button

There was `Review a repository` beside `Read a real finding`, the second pointing at
`/reviews` — which is empty on a first visit. One page has one primary action. The second
offer is now a text link to `#finding`, which is a shorter walk than starting a review and
lands on something that is actually there. `landing.test.tsx` asserts both hrefs, so putting
a second button back breaks a test rather than a taste argument.

`FinalCta` at the foot of the page does carry two buttons — primary to `/start`, secondary
to `/policies`. That is the bottom of the page, where the reader has finished reading and a
second door is a service rather than a competitor.

### The header call to action, below `sm`

`ButtonLink to="/start"` in `LandingNav` is `hidden sm:inline-flex`. On a phone it wrapped
onto two lines and squeezed the wordmark against the menu button, and it was the third copy
of the same call to action at that width — the hero states it a screen-length below, and the
drawer the menu opens ends with it.

### The corpus count as chrome

The old hero card had a header strip reading `Your policy corpus · 54 policies`. The atlas
hero has no such strip. `CORPUS_SIZE = 54` is still exported from `bearings.ts` and is
currently unused — it is a real number (the bundled `general` corpus really does ship 54
policies) kept for whatever wants it next. Do not put it back as a header ornament; a count
that nobody acts on is the ribbon again in a smaller font.

## Responsive behaviour

| Width | What the hero does |
| --- | --- |
| `< sm` (640) | Copy full width. Map at `aspect-[900/700]`, full width, **module labels at 18 user units and only the active node labelled** — fifteen labels at half scale are fifteen illegible labels, and the callout beneath names the candidate in text anyway. The header CTA is gone; the section nav is behind the menu button. The `intent` band's field drops to 34% opacity so it never competes with the three paragraphs over it |
| `sm` (640) | Node labels appear at 13 units, module labels drop to 12. The header CTA returns. The finding section's three readings go from stacked rows to one row |
| `md` (768) | The section nav appears inline and the menu button goes. The finding section's attribution gutter becomes a real left column instead of a label strip above each block |
| `lg` (1024) | The six steps of *How it works* go to one row of six |
| `xl` (1280) | The figure leaves the flow, pins to the right, and the callout attaches to the map with its leader. Below this the figure is one stacked column: caption, map, callout underneath |

The picker wraps rather than scrolls, and each of its buttons is `min-h-11` — the 44px touch
floor, unconditionally, because these are the page's second-most-tapped control after the
primary button. The `See how a finding is made` link carries the same floor for the same
reason.

## Accessibility decisions taken on purpose

- **`AtlasMap` is `aria-hidden`.** The callout names the candidate in text, so announcing
  fifteen node labels would say it twice and say it worse. This is why the test that checks
  which node is lit reads the DOM rather than the roles.
- **The callout is one `role="group"`** labelled *A policy and the finding it produced*,
  because it is one: the policy above and the finding below change together, and a reader
  arriving by keyboard should be told that before the pieces arrive one at a time. Each
  specimen inside is a group named by its verdict.
- **The cycle stops when anybody is reading it.** `holdProps` — `onMouseEnter`,
  `onMouseLeave`, `onFocusCapture`, `onBlurCapture` — is spread onto the whole hero section,
  so hovering *or* tabbing into any part of the figure pauses it.
- **Reduced motion stops the cycle entirely**, not just the transition. `useSpecimen` checks
  `prefers-reduced-motion` and never starts the interval; the first specimen simply stays.
  The picker still works, so nothing becomes unreachable.
- **The interval is 11 seconds** (`CYCLE_MS`). It was 6.2, which is under a third of the
  time it takes to read the ninety-odd words a specimen carries — so a reader who never
  touched the figure never finished a single one, which is a carousel that exists to be
  watched rather than read.
- **Scroll reveals finish immediately where they cannot animate.** `useReveal` reveals at
  once under `prefers-reduced-motion` and where `IntersectionObserver` is undefined, which
  is the same path jsdom takes — so no test waits for an animation and no reader is left
  with an invisible page.
- **A skip link, and `main` is `tabIndex={-1}`**, so the skip actually moves focus rather
  than only the scroll position.
- The picker's buttons are `aria-pressed` toggles rather than tabs. They do not switch
  panels; they choose which of three co-resident specimens is visible.

## Where this is still open

- **The atlas is a specimen, and nothing says so on the page.** Every field in it is shaped
  like a real record and none of it is from the reader's repository. The callout's provenance
  line (`payments/gateway.py:12–26 · google:gemini-3.6`) reads exactly as it would on a real
  finding. Nobody has yet decided whether that needs a word saying "example" — the argument
  against is that a label on the figure is a label on the product's own confidence.
- **`--material` on the map at very small sizes.** A verdict node is an 8-unit dot inside a
  15-unit ring. At phone width, drawn at roughly a third of the design size, the ring is the
  first thing to disappear on a low-density display. The lit label and the callout carry it,
  but the *unlit* verdict nodes have nothing else.
- **Three specimens is a number, not a rule.** A fourth needs a fourth authored leader, a
  fourth free node position, a wider picker, and it makes the callout's fixed height the
  height of whichever specimen wraps worst. Nothing enforces the count.
- **The comment block at the head of `frontend/src/styles.css` predates the palette that
  file now declares.** It says the model's voice is a serif and that there is no accent hue —
  both were true of the previous system and neither is true a hundred lines below it in the
  same file. Read the token declarations and
  [the design system](design-system.md#colour), not that header, and fix the header when
  somebody is next in there.
