# The design system

What ArchCompass looks like, and why it looks like that.

Five documents describe the interface and they do not overlap. [The charter](charter.md)
says what the product is for and which rules settle an argument about it.
[The experience](experience.md) says what a person is trying to do and whether the screen in
front of them is helping. [Frontend regions](frontend-regions.md) is the vocabulary — what
each area on screen is called, so a sentence like "the docket row clips its own claim" means
one thing. [The landing page](landing-page.md) is the one surface with an argument to make
rather than work to do.

This one is the contract underneath all four: the identity, the tokens, the type roles and the
structural devices that the components are built from. If a component invents a colour, a face
or a radius that is not here, that is the bug — not a local decision.

## Status of this revision

This is v2 and it has landed. The identity, the ramps, the four signal hues, the two tiers and
the laws below are what the code does; what is left open is listed at the end, and every item
there is a measurement rather than a decision.

| Landed | Pending |
| --- | --- |
| Three voices, attribution lines, the `Prose` packing | Every corpus sweep in `ch` and in characters a line — see *Where this is still open* |
| The face: `--font-ui` and `--font-display` are IBM Plex Sans | A browser re-reading of the nine `ch` rectangles |
| The ground and ink ramps; the two tiers; four signal hues | Light `--held` sits 15.7° off its nominal hue |
| Radius, rim, lift, motion, the counts line | `--mark` is unused outside `ui/` — no path in `features/` wears it yet |
| The enforcement culture — a rule is a test | |

**The one number every measure in the product turns on has moved.** A `ch` is the advance of the
used font's zero: Onest's was `0.665em` and narrowed to `0.6618em` as its variable instance got
heavier, and IBM Plex Sans's is `0.600em` at all four static cuts. Every `ch` in the code was
re-derived with the face — `26.75rem` became `24.15rem`, `38.5rem` became `34.8rem` — and
`ui/font.test-metrics.ts` holds the advance once, read off `plex-sans-{400,500,600,700}.woff2`.
That file was `ui/onest.test-metrics.ts` and pinned Onest's advance as a constant, which is why
nothing failed when the face changed; the rename is part of the repair.

## The identity: a record, not a dashboard

The charter settled this and the interface never said it out loud. *Evidence before opinion.
Nothing is asserted without saying where it came from. Reviews are immutable records that can
be compared, not reports that get regenerated and lost.*

That is a case file. Not a dashboard, not an IDE, not an inbox — a document built to be
trusted and audited, where every claim carries its citation and the reader's question is
always *how do you know*. A case file has a look, and three properties fall out of it that
settle most arguments about a specific pixel.

**Paper and ink.** A record is neutral. Every ground in the product — the page, a panel, a
strip, an inset, a table, an empty state — is a grey with a whisper of warmth and no nameable
hue. There is no such thing as a coloured panel.

**The stamp is the only colour.** Colour arrives as a mark: an edge, a glyph, a word, an
underline, a badge. It is saturated *because* it is small. The moment a hue fills a region it
has stopped signalling and started decorating, and a reader who sees colour everywhere stops
reading it as meaning anything.

**Every claim shows its source.** Provenance is not a footer. The route back to a file, a
corpus, a prompt is a first-class element with its own colour and its own face, present
wherever a claim is.

## What was wrong with the second system

Worth writing down, because the second system was not careless either. It was disciplined, it
was measured, it had tests, and it was unreadable in a specific way that none of its tests
could see.

**Every ink passed, and the block still read as one grey.** The Provenance fold measures
6.12:1 for a label and 7.49:1 for the value beside it — both comfortably AA. Against *each
other* they measure **1.22:1**, thirteen levels apart, so the key and the content were one
colour separated by a pixel of size and a change of case. `ui/tokens.test.ts` measures each
ink against each ground and was right to pass. It cannot see two passing inks landing on top
of one another, and that turned out to be the defect.

**The ramp steps were below the threshold of sight.** `--surface` to `--surface-2` is five
levels — 0.015 in OKLCH lightness — so an opened fold, a panel header and a table strip were
all the same white. `--rule` and `--rule-strong` are five levels apart too, which meant the
system had two boundary tokens that measure the same and no way for a component to say
*firmer*.

**A chip and its container were the same declaration.** `Tag` paints `bg-surface-2`; the fold
it sits in also paints `bg-surface-2`. The four "Measured as" boxes were outlines around
nothing, held apart from their ground by a 1.25:1 hairline.

**The dimmest tier was the most-used tier.** 295 uses of `text-ink-3` against 196 of
`text-ink` and 136 of `text-ink-2`, and nine of its commonest recipes put the meta tier on
`text-sm` body copy. The tier reserved for labels was doing the work of body text.

**One channel carried four jobs.** Hierarchy, boundary, container and grouping were all spent
on grey value, in steps of thirteen levels. That is the whole diagnosis: not a token that
fails, but one axis asked to do everything, and asked to do it in increments nobody can see.

**And the identity was anonymous.** One geometric sans at three weights, no hue but a red
kept on so tight a budget it appeared four times, and a charter about evidence and
accountability that the screen expressed in no way a stranger could name.

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
it. `ui/design-system.test.ts` — *"has no second face to reach for"* — fails the build on
`font-read` and `font-serif` anywhere at all, and there is no `--font-read` token to reach
for either.

**This survives v2 unchanged, and it is the reason the face change is safe.** Swapping the
sans does not reopen the serif question: the argument against a third face is that it leaks,
and one sans plus one mono is the same architecture it always was. What changes is which sans,
not how many.

## Type

Two faces, self-hosted as woff2 in `frontend/src/assets/fonts/`, latin subset, loaded
`font-display: swap` with a real fallback stack.

| Token | Face | Cut | Fallback |
| --- | --- | --- | --- |
| `--font-display` | **IBM Plex Sans** | 400, 500, 600, 700 | `ui-sans-serif, system-ui, sans-serif` |
| `--font-ui` | **IBM Plex Sans** | the same face | `ui-sans-serif, system-ui, sans-serif` |
| `--font-code` | **IBM Plex Mono** | 400, 500, 600 | `ui-monospace, "SF Mono", Menlo, monospace` |

`--font-display` and `--font-ui` resolve to the same family on purpose. They are kept apart as
names because they answer different questions — *what sets a number somebody reads at a
glance* and *what sets the interface* — and one of them may want to move later without
dragging the other with it.

### Why the sans moved

Onest is a capable geometric-humanist with a tall x-height and unusually even colour, and it
was chosen for good reasons: it holds up at 10px uppercase letterspaced and at 16px in a
paragraph without either looking borrowed from the other. What it does not have is a point of
view, and the entire product was set in it. That is most of why a stranger could not name what
this interface is.

**IBM Plex Sans is the change that argues for itself: the mono is already IBM Plex Mono.** The
two are one superfamily — same skeleton, same rhythm, same design brief — so the pairing stops
being two unrelated choices that happen to sit together and becomes one family used in two
registers. Plex was commissioned to be an institution's own type, which is the register a
record wants; it has real character in the `a`, the flat-sided bowls and the mechanical `g`,
and it is not on the short list of faces that read as a default.

The cost is honest and small: `--font-ui` moves, the woff2 subsets are rebuilt, and every
figure in *Measure* below is re-derived. Nothing new needs enforcing, because the rule that
already exists — one sans, one mono, no third face — is unchanged.

### The scale

| px | Face | Where |
| --- | --- | --- |
| 11, 700, `0.08em` | Sans | Attribution voices, block labels, group headings, table heads — always uppercase |
| 12.5, 500 | Mono | Evidence: provenance, identities, paths, namespaces, fingerprints |
| 13 | Sans | Footnotes, counts, the docket's meta line |
| 14 | Sans | Controls, a docket row's claim, secondary body |
| 15, 600 | Sans | A panel's heading, and a section heading under a page title |
| 15–17 | Mono | The review head — the repository, branch and commit that identify a review |
| 16, 400, `1.65` | Sans | **The model's reasoning.** Its own size, used nowhere else |
| 20, 600, `-0.02em` | Sans | An app page's `h1` |
| 30–42, 600, `-0.03em` | Sans | Landing display only, `clamp()`ed |

Three sizes move, and each was a legibility defect rather than a preference.

**Labels: 10px → 11px, tracking `0.13em` → `0.08em`.** 10px bold uppercase is under the
practical floor for a tier that carries every `Label`, every attribution and every group
heading in the product, and the unusually wide tracking was compensating for the size in the
wrong direction — letterspacing buys apparent width, not legibility, and past about `0.1em` it
starts costing word shape. 11px at `0.08em` reads larger and looks tighter.

**Evidence: 11px → 12.5px, and it gains weight 500.** This tier sets 64-character hashes and
absolute paths, so the product's longest strings were at its smallest size, in the face whose
stems are thinnest at that size. A mono at 11px measured against a ground at 6:1 is not the
same reading experience as a sans at 11px against the same 6:1; contrast is computed on the
colour pair and says nothing about stroke.

**A page title: 17px → 20px.** 17 was chosen to avoid spending the largest type on the page on
the word a reader is least in doubt about, which is a sound argument against 28px and an
over-correction at 17. A record's head should read as a head.

### Measure

**Every `ch` figure this section used to carry has been deleted rather than converted.** They
were properties of `onest.woff2` — the advance of its zero at two weights, read off `hmtx` and
`HVAR` — and a face change makes every one of them wrong. Carrying them forward would be
exactly the failure this section spent six passes learning to name: a number in prose is a copy
of a measurement, and a copy has no way to notice that the thing it copied moved.

The same rule sorted the code's own figures when the face landed, into two piles that are worth
telling apart. **A `ch` is arithmetic** — count × size × advance — so every one of them was
recomputed, and the tests that hold them went red until they were. **A character on a full line
is a corpus measurement**, needing the built bundle, a headless browser and a workspace database
that is not checked in; those are still Onest's, they are marked as Onest's everywhere they
appear, and they are the open item at the end of this document. Nothing was converted by
ratio.

What survives is the method, which is face-independent, and the rule about where a figure is
allowed to live, which is the genuinely transferable lesson.

**The method.** Serve the built bundle and wait on `document.fonts.check` for every weight
involved, because `font-display: swap` otherwise answers with a fallback whose metrics are
several per cent out. Take the corpus from a read-only copy of `.archcompass/workspace.sqlite3`
as the union of `core_finding_cache.finding_json -> reasoning` and
`core_review_snapshots.review_json -> findings[].reasoning`. Render all of them through the
real `ModelProse`, with quoted names drawn as the mono chips they ship as, because a chip is
wider than the sans it displaces. Then cluster a `Range` per character on the vertical centre
of each rect, at a 0.6px tolerance, one cluster to a line.

**And say what a character on a line is**, because the method decides neither half of it and
each half moves every figure. *Which* characters: the block's **rendered** text, so a quoted
name counts as the characters inside its chip and not as the backticks the model wrote around
it. *Where the wrap's space goes*: a soft wrap happens at a space, that space is drawn on no
line, and every figure here counts it as belonging to **the line it ended** — so a line runs
from its own first visible character up to the next line's first, and the last line of a block
takes the rest. The reason is that those spans then partition the block, so the counts sum to
its own rendered length and can be checked against something other than a second run of the
same script. Counting the visible run instead — first ink to last — gives a reading about one
character lower throughout, and neither reading is wrong; leaving the choice unwritten is.

**A `ch` is only honest where one font size *and one weight* are set.** It is the advance of
the used font's zero, so it follows both, and a variable face's zero narrows as the instance
gets heavier. One `max-w-[46ch]` shared by a 24px title, an 18px heading, a 15px one, a 14px
`####` label and a 14px paragraph — every one of those but the paragraph semibold — is **five**
different widths on four sizes. A measure shared across sizes is stated in `rem`.

**Which figures belong in a test, and which belong in the argument.** Seven rounds of wrong
numbers on one surface is not seven careless passes; it is a shape. The line is drawn by what
the number is *made of*:

* **Derivable from something in the repository — it goes in a test, and the prose names the
  test.** Every `ch` resolution is `value × size × advance` over a class list a component
  emits, so `ui/markdown.test.tsx` and `features/review/finding-detail.test.tsx` recompute all
  of them and this document quotes them without owning them.
* **A measurement of a corpus or of a layout engine — it stays in prose, with its method, its
  population and its definitions beside it.** A return-sweep average needs a headless browser,
  the shipped face and a workspace database that is not checked in. Hiding it in a script
  nobody runs would make it less checkable, not more.
* **A historical counterfactual — it goes.** "The 73 came from measuring the string" described
  a method nobody wrote down, so nobody could check it, and it turned out to be wrong in the
  direction as well as the digit. A wrong number about a past mistake teaches a future one.

The font model lives in one place — `ui/font.test-metrics.ts`, renamed with the face — holding
the advance per weight with the `fontTools` recipe above it, Tailwind's nine weight utilities,
and a resolver that turns a class list into an advance or **throws**. It throws rather than
falling back to 400, because under a variable face a silent fallback was half a per cent: small
enough that nobody re-derives it, large enough to make every figure in a comment wrong. Under
four static cuts it guards something worse — a weight with no entry is a weight `styles.css`
does not download, so its `ch` resolves against whatever the fallback stack hands over.

**The file is named for the job and not for the face, and that is the lesson of this pass.** It
was `ui/onest.test-metrics.ts` and it held `{ 400: 0.665, 600: 0.6618 }` as a constant, so when
`onest.woff2` was deleted from the tree nothing failed: every test recomputed faithfully from a
number that had stopped describing anything. The sentence that used to stand here — "those tests
will fail the moment the face changes, which is correct and is the reason they are tests" — was
wrong, and it was wrong in the one way this section keeps learning about. A test that pins a
measurement is only a guard against the *code* moving under it; nothing in vitest reads a woff2.
The advance is now `0.600em` at every cut, verified against the `hmtx` of all four shipped files,
and the four entries are four readings that agree rather than one reading generalised.

### The rules that outlive the face

Every renderer that draws a block declares a measure, and `ui/markdown.test.tsx` asserts it
over `EMITS` rather than over a count — a count of "at least eight" passed while a `####`
label ran the panel's full width over paragraphs stopping at a third of it. `RENDERERS` is a
`Record` over `EMITS`, so a tag on that list cannot be forgotten; `tsc` names it. The fixture
is written from the grammar rather than from a plausible document, and the assertion is that
no element in the rendered tree carries an empty class list.

**Two declared measures agreeing is not two edges agreeing.** A measure is a cap, and what a
block draws at is the smaller of that cap and the box it is in — so a test that resolves two
declared numbers is blind to two boxes of different widths, which is what a two-column grid
makes. The repair is containment rather than a second number: the lede is placed in the
argument's own grid column, so no cap it declares can take it wider.

A paragraph the model wrote is cut at its own sentence boundaries, up to six blocks, each
separated from the last by 8px — under a third of the line, which is enough to find and too
little to claim paragraph structure the model did not write. Past six blocks the sentences are
packed into blocks of even rendered length, and the block a reader arrives at is held to its
share, so an argument never opens on its tallest paragraph. A property about `pack` has to be
checked over every string `pack` is handed, which is why `ui/prose.test-corpus.ts` holds all
nine strings that reach the cap rather than the two that happen to catch one mutation.

Digits that line up in a column take `tabular-nums`. A qualified name is one token to the line
breaker, so anything that can hold one takes `wrap-anywhere` — this is the single most common
overflow bug in the product and `features/review/overflow.test.tsx` exists for it.

## Colour

**Colour signals; neutrals ground.** Four hues carry meaning and nothing else does. Every
surface in the product is neutral, in every state, and the moment a hue fills a region larger
than a badge it has stopped signalling.

That is one sentence longer than the rule it replaces — *there is one hue, and everything
wearing it means the same thing* — and the extra clause is the whole change. The old rule
bought unambiguity by spending the entire budget on one red, and paid for it twice: two of
three verdicts went grey and stopped separating down a column, and provenance had to borrow
the alarm colour to say "this goes somewhere". Four hues on a strict surface-area budget buys
the same unambiguity, because none of them is decoration.

### Grounds

Neutral, warm by 0.005 OKLCH chroma — below the point a reader can name the hue, above the
point a grey reads as dead rather than chosen. One rule orders the ramp in both themes:
**light means elevation.** In light that reads as white on grey; in dark it reads as a film of
white laid over the void, the same rule running the only direction it can once the ground is
already at the bottom. Nothing is darker than the page; a hole is not a thing you can dig at
the bottom.

| Token | Light | Dark | For |
| --- | --- | --- | --- |
| `--canvas` | `#f1eeeb` | `#0b0a08` | The page |
| `--surface` | `#fffffc` | `#181614` | A panel, a docket row that is open |
| `--surface-2` | `#f8f5f2` | `#22201e` | A strip inside a panel — a header, a footer |
| `--sunken` | `#e7e5e2` | `#2d2b29` | A quiet inset: a hover, a code block, an opened fold |
| `--overlay` | `rgb(0 0 0 / 45%)` | `rgb(0 0 0 / 72%)` | Behind a drawer |
| `--chrome` | `rgb(255 255 255 / 72%)` | `rgb(0 0 0 / 62%)` | The one deliberately see-through surface, blurred `22px` |
| `--control` | `#fffffc` | `rgb(255 255 255 / 7%)` | The fill of something you operate |
| `--control-2` | `#e7e5e2` | `rgb(255 255 255 / 13%)` | Its hover |
| `--rim` | `transparent` | `rgb(255 255 255 / 7%)` | The light along a surface's top edge |
| `--ink` | `#181614` | `#f9f6f3` | What is said |
| `--ink-2` | `#494745` | `#b5b2af` | The reading tier |
| `--ink-3` | `#656360` | `#969390` | Labels and meta — never a sentence |

`--sunken` is the bottom of the ramp in light and the **top** of it in dark, which is the same
rule read the only way it can be once the page is already at the bottom — and it has one
consequence worth naming, because two of the things in that row nest. A code block inside an
opened fold cannot step again: there is no neutral token above `--sunken` in dark. **The inner
one takes a boundary instead of a fill** — `--rule-strong`, no ground of its own — which is what
`features/review/lookup-result.tsx` and the policy cards in the Provenance fold both do. A fill
repeated on a fill is 1.00:1, and an outline around nothing is the defect this revision was
called to fix, not a way of fixing it.

**Every step in that ramp is at least 0.020 in OKLCH lightness** — 0.021 to 0.028 in light,
0.043 to 0.057 in dark — against the 0.015 the v1 light ramp stepped in. That is the whole of the grey-on-grey repair: a division a reader is not asked to
notice is still a division they can see, and five levels is neither. The ink tiers are
**0.100 apart** where v1 put them 0.046 apart, so a label and the value beside it are two
colours rather than one colour with two names.

Every ink clears 4.5:1 on all four grounds in both themes. The lowest cell in the matrix is
**4.62:1**, `--ink-3` on `--sunken` in dark.

### Boundaries

| Token | Light | Dark | On `--surface` | For |
| --- | --- | --- | --- | --- |
| `--rule` | `rgb(0 0 0 / 11%)` | `rgb(255 255 255 / 12%)` | 1.28 / 1.42 | Separating things that are already apart |
| `--rule-strong` | `rgb(0 0 0 / 22%)` | `rgb(255 255 255 / 26%)` | 1.69 / 2.35 | A boundary that groups — a chip, a table head |
| `--rule-control` | `rgb(0 0 0 / 42%)` | `rgb(255 255 255 / 40%)` | 3.03 / 3.81 | The edge that says *this is a control* |

`--rule-strong` moves from 15% to 22% because at 15% it measured 1.41:1 against `--rule`'s 1.28:1 — two boundary tokens five levels apart, which is one boundary token with a typo. The
rule that decides which to reach for: **a boundary carrying structure clears 1.6:1; one
carrying an affordance clears 3:1.** Below 1.6:1 a rule is decoration and the fix is to delete
it and use space, not to lighten it further.

### The four signals

| Meaning | Token | Light | Dark |
| --- | --- | --- | --- |
| Act on it | `--material` | `#961114` | `#f86b60` |
| Waiting on you | `--held` | `#835000` | `#f8bb1a` |
| Settled | `--cleared` | `#006b39` | `#67d89c` |
| Where this came from | `--mark` | `#0053a0` | `#4ca8ff` |

`--material` is red at OKLCH hue 27, which is the brand's hue, and `--accent` resolves to it
rather than the other way round — the alarm and the mark are one colour and cannot drift into
two reds that nearly match. `--accent-edge` is the same alias one tier down, and it exists for
`StatusDot`'s "a run is in flight" dot: a dot is a graphic, so all five of that component's
hue-bearing tones are painted from the `-edge` half, and the one that is deliberately *not* a
verdict needed a name at that tier to come with them. `--held` is amber at 84, `--cleared` green
at 158, `--mark` blue at 250.

**Those four are the dark values, and light does not reproduce them.** Measured off the shipped
hexes, dark sits on the nominal hues exactly — 27.0, 84.0, 158.0, 249.8 — while light reads 27.1,
**68.3**, 154.0 and 254.1. The drift that matters is `--held`: an amber that has to clear 4.5:1
on a near-white ground has to go brown to do it, and 68.3 is where it landed. `tokens.test.ts`
allows 20° around each nominal hue for that reason, and asserts separately that twice that window
stays under the 57° between `material` and `held`, which is the tightest pair — so widening the
tolerance cannot quietly become a way of no longer telling an amber from a red.

**Re-picking it was the open item, and the measurement closes it: 68.3 stays.** sRGB does not
hold a hue-84 amber at a lightness dark enough to clear 4.5:1 on this ground — the in-gamut
maximum at L 0.51 is chroma 0.104, so the nominal 0.150 was never reachable and clipping is what
produced 68.3. Held to 84 the best available is `#826002`, and it is worse on both counts that
matter: the worst dichromat pair among the three verdicts is ΔE 4.3 either way — 84 buys 3.1 on
`material`/`held` and gives 1.6 back on `held`/`cleared`, moving which pair is worst without
raising the floor — while `#826002` drops the contrast floor from 5.37:1 to 4.61:1. So light
`--held` is a bronze by choice, `--held-edge` is 10.2° off for the same ceiling, and the two
themes are genuinely different colours rather than one colour at two lightnesses.

**`--mark` leaves the severity scale, and that is the point of adding it.** Where a claim came
from is not a grade. Under v1 a file path wore the same red as a material verdict, so the
interface said *act on this* about a citation; the fold that holds nothing but provenance is
the clearest case, and it is why a reader looking at it could not tell which of the three
voices they were in.

### Two tiers, and they are not interchangeable

WCAG asks different things of a word and of a graphic: 4.5:1 of body text, 3:1 of a
user-interface component or a meaningful graphic. Splitting the tiers on that line is what lets
the edge tier be genuinely saturated while the word stays readable, and it is the tier the eye
catches first when scanning a column.

| Text tier / graphic tier | Light | Dark | May paint |
| --- | --- | --- | --- |
| `--material` / `--material-edge` | `#961114` / `#d72e2d` | `#f86b60` / `#e8403b` | text / edges, glyphs, bars, dots |
| `--held` / `--held-edge` | `#835000` / `#b27600` | `#f8bb1a` / `#e6a400` | text / edges, glyphs, bars, dots |
| `--cleared` / `--cleared-edge` | `#006b39` / `#009754` | `#67d89c` / `#00c479` | text / edges, glyphs, bars, dots |
| `--mark` / `--mark-edge` | `#0053a0` / `#007ae3` | `#4ca8ff` / `#0087f8` | text / edges, glyphs, bars, dots |

Every text tier clears 4.5:1 on all four grounds and on its own wash; the lowest is **4.87:1**,
`--material` over `--material-wash` in dark. Every edge tier clears 3:1 on all four grounds;
the lowest is **3.01:1**, `--cleared-edge` on `--sunken` in light. Setting a word in the edge
tier is a contrast failure. Painting a 3px edge in the text tier wastes the signal.

### The wash is a badge fill and nothing else

| Token | Light | Dark |
| --- | --- | --- |
| `--material-wash` | `#ffebe7` | `#42231f` |
| `--held-wash` | `#faf0dc` | `#382a0d` |
| `--cleared-wash` | `#e2f7ea` | `#153423` |
| `--mark-wash` | `#e4f3ff` | `#192e44` |

This is the only chromatic fill *on the signal scale*, and it is capped at the size of a pill —
roughly 120×24px. A provenance panel, a code block, a table header, an empty state, a fold body,
a selected row: neutral, always. The v1 `-soft` washes are renamed rather than merely retuned,
because the old name invited use as a panel tone and was taken up on exactly that reading.

**The exception, stated rather than left to be discovered: `--accent-fill`.** The primary action
and the brand tile are red boxes 32–44px tall, which is over the cap, and they stay. A signal
says something about a *finding* and its surface area is budgeted so that it keeps meaning
something; a primary button says something about what a person can do next, there is at most one
on a screen, and it carries `--accent-on-fill` at 8.8:1 rather than tinting anything behind it.
Two files paint it — `ui/button.tsx` and `ui/brand.tsx` — and what holds it there is the signal
budget in `ui/design-system.test.ts` rather than the wash rule, which is why the L1 guard's own
pattern names only the four signals and their washes.

### Colour is never the only carrier

Every verdict states itself four ways: a **glyph**, a **word**, a **left edge** and a **hue**.
Render the interface in greyscale and nothing may become ambiguous.

This is not belt-and-braces, it is the load-bearing part. Simulated with Viénot, Brettel &
Mollon, the three verdicts separate under deuteranopia at **ΔE 4.3–6.0 in light** and 10.8–14.7
in dark. The light figure is weak, and it is weak for a reason that is physics rather than
tuning: four hues that must each clear 4.5:1 on a near-white ground are confined to a narrow
band of lightness, and red and green converge there under the commonest dichromacy. No
arrangement does materially better without the hues ceasing to look like themselves — a search
that maximised dichromat separation alone produced a maroon, a burnt orange and a navy.

So the palette is chosen for semantic legibility and the redundancy carries the rest. A
greyscale check in `ui/verdict-hues.test.ts` is what enforces it, because the property is
*"does anything become ambiguous"*, and that is a question about the component, not the token.

### The one exception: a source excerpt

Code is coloured, and it is the only thing on screen that is. Three hues, inside a monospace
block, never anywhere else.

The reason it earns one is that an excerpt asks a question the rest of the interface does not.
Everywhere else a reader arrives already knowing what they are looking at — a badge, a path, a
count. Inside forty lines of Python they are looking for something else entirely: which of
these tokens is a name somebody in this repository chose, and which is the language's own
furniture. Weight cannot answer that, because half of Python is a keyword.

**The v1 rule for keeping code off the signal cannot survive four hues, and this is measured
rather than asserted.** That rule was *a `--code-*` hue stays 35° from the accent*, which was
easy when the accent was the only hue on the wheel. Against the four signals, two of the three
code roles now collide, and these are read off the tokens as declared rather than off the nominal
hues: `--code-name` sits at 264 and is **10.3°** from `--mark` in light, **14.0°** in dark;
`--code-lit` sits at 172 and is **18.2°** from `--cleared` in light, **15.0°** in dark. The
collision is under 20° under every reading. There is one gap on the wheel wide enough to hold
three separated hues — the 133–137° between `--mark` and `--material` — and putting
the whole syntax palette in the violets to satisfy an angle would make Python look like
nothing anyone writes it in.

The replacement rule is **context isolation rather than hue separation**: a signal token may
never be painted inside a `<pre>`, and a `--code-*` token may never be painted outside one. Two
disjoint contexts, so a hue can be reused across them without ambiguity — the same reason a
road sign and a chart may both use green. It is a stricter test than the angle it replaces,
because it is a statement about where a token appears rather than about what value it holds,
and `tokens.test.ts` can check both halves.

The rest of the code rules stand unchanged: every `--code-*` clears 4.5:1 on `--sunken`, which
is the only ground a highlighted span is painted on; the four roles stay apart from each other
and from `--ink` by OKLab distance, because contrast against the ground is a different question
from telling five things in a block apart; and every one is declared three times — light, the
`prefers-color-scheme` fallback and the `data-theme` attribute — because a value edited in two
of the three is wrong for exactly half the readers.

### The band

A permanently dark strip has its own tokens — `--band`, `--band-ink`, `--band-ink-2`,
`--band-rule` — because the topbar and the landing page's field band do not invert with the
theme and therefore cannot borrow `ink`/`surface` from the page. Each signal has a
`-on-band` value for the same reason: `--material` at `#961114` measures **2.05:1** on the band.

**Not inverting is not the same as being one value.** `--band` was `#0a0a0a` against v1's
`#000000` void. v2's canvas is `#0b0a08`, and `#0a0a0a` is **1.00:1** against it — so held at one
hex the band either vanishes in dark or, lifted to `#181614` to survive there, reads a step paler
than near-black in light. Neither is a decision; both are the ramp moving underneath a value that
was pinned to the wrong thing. So it is declared per theme, and what is held constant is *dark*,
not a hex: `#0a0a0a` in light at 17.13:1 over the page, `#181614` in dark at 1.10:1 over the void
— the same step every panel is separated from its ground by. The ink is not split with it,
because the whole `-on-band` set clears on both grounds; the worst text tier measures 6.85:1 on
the light band and 6.24:1 on the dark one. `--band-hover`, the fill a rail control takes under a pointer,
is here too — it was hand-written as `bg-white/8` and was the one fill in the product with no
token to argue it. Nothing paints any of these directly; `.on-band` is what hands them over, and
it has to redeclare `--accent` and `--accent-edge` as well as the twelve signal tokens, because a
custom property resolves where it is *declared* and `--accent: var(--material)` resolves on
`:root`.

### One coloured thing per row, in one place

A docket row gets an edge and a badge. Not an edge, a badge, a coloured count and a coloured
title. Saturation only works when it is rare, and the budget is what makes the four hues read
as meaning rather than as theme.

## Structure

### Separate with space, then a rule, then a fill, then a border

In that order, and stop at the first one that works.

This is the ordering v1 had backwards in practice, and the Provenance fold is where it showed:
nine hairlines at 1.28:1 holding apart nine rows of a definition list. A rule that low does not
separate anything — it adds eight grey bands to a block already made of grey. Space separates
for free, at any contrast, in both themes, and costs nothing but height.

A **rule** separates things that are already apart. A **border** belongs to something you could
pick up. That distinction does most of the structural work, and it is why the finding's two
halves are one grid divided by `border-rule` rather than two panels with a gap.

### Radius means what it is, not what it does

The step says how large the thing is, not how operable:

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

### Never mix a tone from an alpha of a ramp token

`bg-sunken/60` composites to `#efefef` over the light canvas — six levels, an unnamed grey, and
a tone that does nothing — while the identical declaration in dark composites nineteen levels
and reads correctly. A tone that only works in one theme is not a tone. If a value is wanted
that is not on the ramp, name it here.

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
round that swapped one question for the next and needed the swap to say which way it had gone.
The round is a stack now and nothing swaps, so the token went with the thing it was for. Motion
that exists to make a transition survivable is worth asking whether the transition should
happen at all.

## The counts under the review head

*Not a dashboard. Counts are orientation, read once, on the way to the work.* One wrapping
line: **how many need a decision**, in plain ink, then the verdict spread with its glyph, its
number and its word.

The leading count is deliberately plain ink even where most of what it counts is material — a
hue on a mixed total would be a verdict painted on something that is not one.

A zero recedes on a laptop and disappears below `sm`, because "0 material" is worth a glance
where there is room for the whole scale and a line of the viewport spent saying nothing
happened where there is not.

## What is forbidden, and what enforces it

Every rule below is a test in `frontend/src/ui/design-system.test.ts`, `ui/tokens.test.ts` or
`ui/verdict-hues.test.ts`. Each was a rule in a comment first, and each shipped broken anyway.

| Rule | Why it is a test |
| --- | --- |
| Four signal hues, and the set is closed | `material`, `held`, `cleared`, `mark`. `tokens.test.ts` fails any other token carrying chroma above 0.006 outside the code palette. The v1 rule banned chroma outright; this one names the four that are allowed and still catches everything else |
| No chromatic fill taller than a badge | The wash tokens are the only chromatic backgrounds and they are reachable from `ui/badge.tsx` alone. A panel, a fold body or a table head reaching for one is the defect this replaced |
| The two tiers do not swap | An `-edge` token in a text position fails the 4.5:1 floor; a text token on a 3px edge is a wasted signal. `tokens.test.ts` measures both floors against all four grounds in both themes |
| `--accent` is `--material`, never a second hex | The alias runs that way round now: the brand's red *is* the alarm rather than a colour the alarm borrows, and `--material: var(--accent)` would be a cycle. `tokens.test.ts` asserts the direction the stylesheet declares. A second red a hex away from the first is two reds that nearly match — a material badge and the button beside it |
| Every ramp step is ≥0.020 OKLCH lightness, every ink pair ≥0.09 | The grey-on-grey defect was two passing inks landing on each other and four surfaces measuring the same white. Contrast against a ground could not see either |
| No verdict hue outside a verdict | `verdict-hues.test.ts`, with an allowlist that a second test checks still names real files |
| `-mark` only where something goes somewhere | The name is the decision; without the guard it becomes a synonym for a blue |
| Nothing becomes ambiguous in greyscale | Every verdict carries a glyph, a word and an edge as well as a hue. This is what carries a deuteranope, not the palette, and it is asserted over the rendered component |
| No signal token inside a `<pre>`; no `--code-*` outside one | Replaces the v1 rule that a code hue stays 35° from the accent, which four signals make unsatisfiable — measured against the shipped tokens, `--code-name` is 10.3° from `--mark` in light and 14.0° in dark, `--code-lit` 18.2° from `--cleared` in light and 15.0° in dark |
| Every `--code-*` clears 4.5:1 on `--sunken` | Code at its size is body text, not large text, and `--sunken` is the only ground a highlighted span is painted on |
| The four code roles stay apart | A coloured role within 0.20 OKLab of `--ink`, a name within 0.15 of a literal, a name within 0.09 of a keyword, or three hues spanning under 110° |
| Every `--code-*` is declared three times | Light, the `prefers-color-scheme` fallback and the `data-theme` attribute. A value edited in two of the three is wrong for exactly half the readers and invisible to whoever wrote it |
| A parameter is painted as a name | `tests/browser/test_code_colour.py` reads the *resolved* colour of an `hljs-params` span in a real excerpt, in both themes. jsdom applies no stylesheet, so nothing in vitest can tell whether a selector list reaches a token on screen |
| No second face — no `font-read`, no `font-serif` | The model's voice is placement, attribution and the reading size. A face leaks; those do not |
| Mono means the machine is quoting itself | Identifiers, paths, hashes, retrievers, measurements — not headings, not empty states, not English sentences. "Nothing came back above the threshold" set in 11px monospace reads as an identifier that has gone wrong |
| A mark is drawn, never typed | A pasted `▲` falls back to the system font and breaks the set. Three blocks — arrows, ticks and crosses, geometric shapes. Comment lines are skipped: a doc comment naming the marks it draws is a description, not the thing |
| Lift only what leaves the page | Three files. Structure is separated by a rule and a rim |
| One rim, from the token | Two rims a percent apart read as a rendering bug rather than as a decision |
| No tone mixed from an alpha of a ramp token | It composites to a real step in one theme and to nothing in the other |
| No `line-clamp` on a `display: flex` box | They collide silently — the clamp is ignored and the row grows |

## Where this is still open

- **Every corpus sweep is still Onest's.** The arithmetic moved with the face and the
  measurements did not, because they need what a vitest run does not have: the built bundle
  served over HTTP, a headless Chromium waiting on `document.fonts.check`, and a read-only copy
  of `.archcompass/workspace.sqlite3`. What is outstanding, all marked as Onest's where they
  appear: the 75.7 characters a full line of a judgement carries at the argument's measure and
  the 59 a footnote carries at its own (`features/review/finding-detail.tsx`); the 60.58 a policy
  note carries (`finding-detail.tsx`, the policy-card comment); the **541.7px** widest
  unbreakable qualified name in `ui/prose.test-corpus.ts`, which is the *floor* the argument's
  measure is chosen against; and the nine `ch` rectangles in `ui/font.test-metrics.test.ts`,
  whose relation to the arithmetic — snap down to 1/64px — is a property of Chromium and
  carries over, while the nine readings do not.
  **The floor is the one to do first.** `58ch` was 617.12px under Onest and cleared the 541.7px
  floor by 75px; under Plex Sans it is 556.80px and clears it by 15px, and both ends of that
  subtraction have moved, since the token is now set in the new face too.
  `features/review/finding-detail.test.tsx` asserts the inequality and it passes — on one
  face's measure against another face's floor.
- **Deuteranopia in light is weak.** ΔE 4.3–6.0 between the three verdicts, against 10.8–14.7
  in dark. The redundancy rule is the answer and it is enforced, but a reader with a red-green
  deficiency is getting less from the light theme's hue channel than from the dark theme's.
  Worth revisiting if the ink floor ever moves — the constraint is 4.5:1 on a near-white
  ground, and it is what confines the four hues to a narrow band.
- **`--cleared` has the least headroom in the set.** 5.28:1 on `--sunken` in light is the
  tightest text cell among the signals, and green is the hue that loses most when a ground
  darkens. Pin it with a test rather than a comment.
- **The code palette collides with two signals, and the isolation rule is what holds it.** Two
  of three roles sit within 20° of a signal hue in both themes. Context isolation is now
  enforced — `tokens.test.ts`, *"keeps the code palette inside a code block, and the signals
  outside one"*, in four assertions plus a check that `@theme` maps no `--color-code-*` so no
  `text-code-name` utility can exist. What it cannot see is the markup `highlight.js` emits,
  which is trusted to carry only `hljs-` classes, and whether a selector reaches a token on
  screen, which is `tests/browser/test_code_colour.py`'s.
- ~~**Light `--held` is 15.7° off its nominal hue.**~~ **Settled — 68.3 stays.** `#835000`
  measures 68.3 where the set is named at 84, and the cause is an sRGB ceiling rather than a
  slip: the in-gamut maximum at hue 84 and L 0.51 is chroma 0.104, so the nominal 0.150 was
  never reachable and clipping produced both the hue and the chroma. Re-picking was the
  proposed fix and the measurement rejects it. The best hue-84 value is `#826002`, which leaves
  the worst dichromat pair among the three verdicts at ΔE 4.3 — identical to today, buying 3.1
  on `material`/`held` and giving 1.6 back on `held`/`cleared`, so it moves which pair is worst
  without raising the floor — and drops the contrast floor from 5.37:1 to 4.61:1. A bronze that
  reads at 5.37:1 beats a gold that reads at 4.61:1 and separates no better. The palette table
  and the signals section now state the measured hue rather than the nominal one.
- **`--mark` is unimplemented outside `ui/`.** `PathRef` and the Markdown anchor wear it, and
  the L4 half that says provenance gets its own colour is real there. Everywhere in `features/`
  a file path, a namespace, a run id, a corpus id or a retriever name is still `text-ink-3` in
  mono, and two call sites argue explicitly *against* the mark on the reading that ordinary
  navigation is not provenance. That question — is a link to another page in this product
  "where this came from" — is not settled by the sentence above, and until it is the fourth hue
  is doing a quarter of the job it was added for.
- **`--rule-control` is 2.98:1 on `--canvas` in light**, two hundredths under the 3:1 the
  boundary rule names for an affordance. The table quotes it on `--surface`, where it is 3.03,
  and two things sit on the canvas rather than on a panel: the docket's progress strip and the
  `Key` caps in its shortcut hint. Nothing on the ramp is closer, so lifting it means minting a
  boundary token the system does not have.
- **The dark ramp's greys are close.** `#181614`, `#22201e` and `#2d2b29` step 0.043 and 0.045
  apart in OKLCH lightness. That is an evening-out rather than a widening: v1 stepped 0.159,
  0.032 and 0.048, so the page-to-panel gap was doing almost all the work and the two panel
  tones were the pair that gave way on a cheap display. v2 spends the range more evenly, and
  the rim still carries more of the separation than a colour ramp should have to delegate.
- **Numerals are set per call site rather than once.** The interface asks for tabular
  everywhere a count sits in a column, which is a `tabular-nums` utility on every one of them
  rather than a font feature set on the token. That was already true under Onest and the face
  change does not fix it — but it does mean every one of those columns wants re-checking, since
  which figures a face gives by default is a property of the face. If a column jitters, the fix
  is `font-variant-numeric` on `--font-ui`, not another utility.
