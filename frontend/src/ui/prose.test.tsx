import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import {
  Citations,
  INLINE_CODE,
  INLINE_CODE_BARE,
  ModelProse,
  Prose,
  plainProse,
  sentences,
  type Citation,
} from "./prose";
import {
  OVER_CAP,
  PHONE_COLUMN_PX,
  UNDER_CAP_WALL,
  WIDEST_UNBREAKABLE_TOKEN_PX,
} from "./prose.test-corpus";
import { spacingPx } from "./tailwind.test-spacing";

/**
 * The scanner in `ui/prose.tsx`, which is a parser and will therefore be wrong in an edge
 * case if nobody checks.
 *
 * The acceptance test is the second block: a name the model quotes has to arrive on screen
 * byte-identical, because a wrong name looks exactly like a right one and is a worse failure
 * than the backtick this whole file exists to remove. The strings there are taken from real
 * recorded model output.
 */

/**
 * A class list that lets the line breaker split a run of characters that has no break in it.
 *
 * Stated as the set of utilities that grant the permission rather than as the one this file
 * happens to use, because what the block needs is the *permission*: `wrap-anywhere` and
 * `wrap-break-word` are `overflow-wrap: anywhere` and `break-word`, `break-words` is the older
 * spelling of the second, and `break-all` is `word-break`. All four let a name too wide for its
 * column fold instead of pushing the column open, which is the property under test.
 *
 * `wrap-anywhere` is the one chosen, and the difference is real even though this set does not
 * insist on it: `anywhere` is counted in the element's min-content width and `break-word` is
 * not, so only `anywhere` also stops a grid or flex track being sized to fit the whole name.
 * The Judged band puts this block in a `minmax(0,1fr)` track, which makes that difference moot
 * there and would not make it moot everywhere `ModelProse` is drawn.
 */
const BREAKS_INSIDE_A_TOKEN =
  /(?:^|\s)(?:wrap-anywhere|wrap-break-word|break-words|break-all)(?:\s|$)/;

/** The rendered prose as one string, with the chips marked so a test can see where they were. */
function rendered(node: React.ReactNode): string {
  const { container } = render(<div data-testid="prose">{node}</div>);
  const host = container.querySelector("[data-testid='prose']") as HTMLElement;
  return [...host.childNodes]
    .map((child) =>
      child.nodeType === Node.ELEMENT_NODE && (child as Element).tagName === "CODE"
        ? `«${child.textContent}»`
        : child.textContent,
    )
    .join("");
}

describe("Prose", () => {
  it("draws a quoted name as code and leaves the sentence around it alone", () => {
    expect(rendered(<Prose>{"The abstraction `NarrationPreparationProvider` is held."}</Prose>)).toBe(
      "The abstraction «NarrationPreparationProvider» is held.",
    );
  });

  it("puts the span in a code element and nothing else in one", () => {
    render(<Prose>{"Held: `ports.Clock` and nothing else."}</Prose>);
    const code = screen.getByText("ports.Clock");
    expect(code.tagName).toBe("CODE");
    expect(code.className).toContain("font-mono");
  });

  it("returns the string untouched when there is no backtick in it", () => {
    const plain = "Two adapters reach the same store, and neither owns it.";
    expect(rendered(<Prose>{plain}</Prose>)).toBe(plain);
  });

  it("renders an empty string as nothing", () => {
    expect(rendered(<Prose>{""}</Prose>)).toBe("");
  });

  /**
   * The corruption this approach exists to avoid, in the exact shapes the recorded corpus
   * contains.
   *
   * Two passes left the counts here alone because the terms were never defined, so they are
   * defined now and then counted. A **bare snake_case token** is a whitespace-separated run
   * lying outside every code span that carries an underscore between two alphanumerics — an
   * identifier the model wrote without asking for one, which is the case a Markdown pipeline
   * sets in bold. A **bracketed run** is a `[…]` outside every code span, which is CommonMark
   * shortcut link syntax. "Outside a code span" is decided by the delimiter-run rule
   * `ui/prose.tsx` itself pairs with, not by a regex, because a stray backtick changes the
   * answer.
   *
   * Counted that way over all 375 recorded strings: **two** bare runs holding `__init__`, **one**
   * holding `__file__` — the sequence inside a longer run, `src.audiobook.preparation/__init__.py)`
   * and `Path(__file__).resolve().parents[1]`, since it is the `__…__` and not the run that a
   * Markdown pipeline sets in bold — **152** bare snake_case tokens **in 118 strings**, and
   * **49** bracketed runs in 37 strings.
   *
   * The two distinct counts need one more word each, because a distinct count is a count of
   * *things held equal* and the definition above does not say what that is. Under it — the run
   * with its punctuation attached, which is what the line breaker sees — the 152 are **81**
   * distinct and the 49 are **13**. Strip each run down to its own first and last character that
   * is a letter, a digit or an underscore — the whole of the rule, so `run_benchmark).` loses
   * both ends while `run_benchmark.py` and `run_benchmark.CATEGORIES` keep their interior dots
   * and stay distinct — and the same 152 fall to **54**, because six of the 81 — `run_benchmark`,
   * `run_benchmark,`, `run_benchmark).`, `(run_benchmark,`, `(run_benchmark` and
   * `run_benchmark)` — become one. 54 is the figure this comment carried while stating the
   * attached definition in the same sentence, which is the drift in miniature: not a wrong
   * measurement, a right one under a rule nobody wrote down. Both are kept, each with its rule.
   *
   * The numbers this replaces were 113 and 52, and no reading of either term produces them: the
   * nearest a bracket count comes is 51, which is every `[…]` in the corpus including the two
   * that sit *inside* a code span and are therefore never at risk.
   *
   * None of this is recomputed by a test, and it cannot be: the counts are over the 375 recorded
   * strings, and `ui/prose.test-corpus.ts` explains at length why only the nine the block cap
   * touches are checked in. Re-derive them by copying `.archcompass/workspace.sqlite3`, opening
   * the copy read-only, and splitting each string with a port of `scan` from `ui/prose.tsx`.
   *
   * **Which `reasoning`**, because there are two and a recursive walk finds both. It is the
   * finding's own top-level field — `core_finding_cache.finding_json -> reasoning`, 231 distinct,
   * and `core_review_snapshots.review_json -> findings[].reasoning`, 148, sharing four, so 375.
   * The other is `policies[].reasoning`, one per policy a finding bears on, which is 292 more in
   * the cache and 227 in the snapshots and takes the union to 889. Those are drawn on a different
   * surface and are not what `ModelProse` sets. Every count in this comment and every sweep
   * figure in `ui/prose.tsx` is over the 375, and a pass that walks the JSON for the key rather
   * than for the field will disagree with all of them by a factor of two.
   *
   * A full Markdown pipeline turns the first of those into a bold "init" — CommonMark's
   * intraword rule does not save it, because the leading `__` is preceded by a space and so is
   * left-flanking.
   */
  it("passes Markdown's own syntax through byte-identical", () => {
    const cases = [
      "The __init__ of the adapter reads the environment directly.",
      "It resolves __file__ at import time, which pins the layout.",
      "run_benchmark and scattered_concept both reach stripe_gateway.",
      "The handler takes *args and forwards them unchanged.",
      "Bears on [1] and [2] under [avoid-duplicated-knowledge].",
      "A **bold** claim, an _emphasis_, a [link](http://example.test) and a # heading.",
      "a_b_c stays a_b_c, and so does a*b*c.",
    ];
    for (const source of cases) {
      expect(rendered(<Prose>{source}</Prose>), source).toBe(source);
    }
  });

  it("keeps Markdown's syntax intact inside a span too", () => {
    expect(rendered(<Prose>{"The registry `__init__` runs first."}</Prose>)).toBe(
      "The registry «__init__» runs first.",
    );
    expect(rendered(<Prose>{"Signature `*args, **kwargs` is preserved."}</Prose>)).toBe(
      "Signature «*args, **kwargs» is preserved.",
    );
  });

  /** A span is not a token: this one is a whole declaration, and it is from the real corpus. */
  it("keeps punctuation, spaces and quotes inside a span", () => {
    expect(
      rendered(<Prose>{"The module holds `_PROVIDERS: dict[str, ProviderFactory] = {}` at import."}</Prose>),
    ).toBe("The module holds «_PROVIDERS: dict[str, ProviderFactory] = {}» at import.");
    expect(rendered(<Prose>{'It writes `"text": "Python with SQLite."` verbatim.'}</Prose>)).toBe(
      'It writes «"text": "Python with SQLite."» verbatim.',
    );
  });

  it("leaves an unmatched backtick literal and keeps reading past it", () => {
    expect(rendered(<Prose>{"A stray ` and nothing to close it."}</Prose>)).toBe(
      "A stray ` and nothing to close it.",
    );
    expect(rendered(<Prose>{"Trailing backtick at the end `"}</Prose>)).toBe(
      "Trailing backtick at the end `",
    );
    expect(rendered(<Prose>{"`"}</Prose>)).toBe("`");
    // Resumed *after* the unmatched run, not inside it, so the span that follows still reads.
    expect(rendered(<Prose>{"An unclosed `` run, then `Clock` reads fine."}</Prose>)).toBe(
      "An unclosed `` run, then «Clock» reads fine.",
    );
  });

  it("closes a span only on a run of exactly the same length", () => {
    // The naive `` `([^`]+)` `` regex reads the opening pair as an empty span and mangles
    // the rest; the run rule is what makes this come out whole.
    expect(rendered(<Prose>{"Reads ``a`b`` twice."}</Prose>)).toBe("Reads «a`b» twice.");
    expect(rendered(<Prose>{"Reads ```a``b``` twice."}</Prose>)).toBe("Reads «a``b» twice.");
  });

  it("strips one space from each end of a padded span, and only then", () => {
    // CommonMark's rule, and the only way to quote a lone backtick.
    expect(rendered(<Prose>{"The delimiter is `` ` `` itself."}</Prose>)).toBe(
      "The delimiter is «`» itself.",
    );
    // Not all spaces removed, and a span that is only spaces is left as it is.
    expect(rendered(<Prose>{"Padded ``  a  `` here."}</Prose>)).toBe("Padded « a » here.");
    expect(rendered(<Prose>{"Blank ` ` span."}</Prose>)).toBe("Blank « » span.");
  });

  it("treats a bare double backtick with no closer as literal", () => {
    expect(rendered(<Prose>{"An empty `` span."}</Prose>)).toBe("An empty `` span.");
  });

  it("does not let a span cross a newline", () => {
    // Deliberately unlike CommonMark: two of the call sites set `whitespace-pre-line`, where
    // the newline is a visible break, and a stray backtick must not eat the next line.
    expect(rendered(<Prose>{"A stray ` here\nand a `Clock` on the next line."}</Prose>)).toBe(
      "A stray ` here\nand a «Clock» on the next line.",
    );
  });

  it("handles a sentence made only of a span, and two spans in a row", () => {
    expect(rendered(<Prose>{"`Clock`"}</Prose>)).toBe("«Clock»");
    expect(rendered(<Prose>{"`a.B` and `c.D` differ."}</Prose>)).toBe("«a.B» and «c.D» differ.");
  });

  it("drops the box on a scanning surface and keeps the face", () => {
    render(<Prose bare>{"Two adapters reach `stripe_gateway` directly."}</Prose>);
    const code = screen.getByText("stripe_gateway");
    expect(code.className).toBe(INLINE_CODE_BARE);
    expect(code.className).toContain("font-mono");
    expect(code.className).not.toContain("border");
    expect(code.className).not.toContain("bg-sunken");
    expect(code.className).not.toContain("px-1");
  });

  it("renders the span as text, never as markup", () => {
    render(<Prose>{"It builds `<img onerror=x>` from the path."}</Prose>);
    const code = screen.getByText("<img onerror=x>");
    expect(code.querySelector("img")).toBeNull();
    expect(code.textContent).toBe("<img onerror=x>");
  });

  /**
   * A quoted name is one box, and a line break may not cut it in half.
   *
   * `INLINE_CODE` says `inline-block` is load-bearing and nothing could see it. An *inline* box
   * fragments at a line break and the browser draws the border, the fill and the padding round
   * each fragment, so an identifier one character too wide for the line left a second chip on
   * the next line holding one letter — a small grey box that reads as a rendering fault rather
   * than as a name. Change the one word to `inline` and every test in the product stayed green,
   * because `Prose` puts whatever string it is given on the element and no test read it.
   *
   * Three assertions, and the second two are why the first is survivable. An unsplittable box
   * that is wider than its column pushes the column open, so the chip is capped at the column's
   * width and told it may break inside itself — where the box around the fragments is what says
   * they are one name. The two widest names in the corpus are backticked in every string they
   * appear in and draw wider than the argument's own measure, so this is the case that is
   * actually reached rather than the one that could be.
   *
   * Asserted on the constant *and* on what reached the DOM, because they are two failures: a
   * class list that stopped being the one this file exports would pass a test that only read the
   * export.
   */
  it("draws a quoted name as one box a line break cannot split", () => {
    render(<Prose>{"Held on `archcompass.ports.capabilities.RevisionCalculator` alone."}</Prose>);
    const chip = screen.getByText("archcompass.ports.capabilities.RevisionCalculator");
    expect(chip.className, "the chip is drawn from something other than INLINE_CODE").toBe(
      INLINE_CODE,
    );

    expect(
      INLINE_CODE,
      "an inline chip fragments at a line break and draws its border round each half",
    ).toMatch(/(?:^|\s)inline-(?:block|flex|grid)(?:\s|$)/);
    expect(
      INLINE_CODE,
      "`inline` is the fragmenting display this class exists to refuse",
    ).not.toMatch(/(?:^|\s)inline(?:\s|$)/);
    // What makes an unsplittable box safe in a 324px column: it may not be wider than the
    // column, and it folds inside itself instead.
    expect(INLINE_CODE, "a chip wider than its column would push the column open").toMatch(
      /(?:^|\s)max-w-full(?:\s|$)/,
    );
    expect(INLINE_CODE, "a capped chip that cannot fold clips the name instead").toMatch(
      BREAKS_INSIDE_A_TOKEN,
    );
  });
});

/**
 * The block `ModelProse` draws, which is the surface the original complaint was about — "like a
 * title but full wall of text" — and which had two class names holding the whole of the fix.
 *
 * `features/review/finding-detail.test.tsx` asserts the measure and the leading, because those
 * are what that band is for. What is asserted here is the two things that are true of this
 * component wherever it is drawn: a block may break inside a name too wide for its column, and
 * two blocks are separated by a gap. Both were unguarded, and both are one word to delete.
 */
describe("ModelProse", () => {
  /** The blocks the component drew, which is what a reader arrives at. */
  function blocks(source: string) {
    const { container } = render(<ModelProse>{source}</ModelProse>);
    const root = container.firstElementChild as HTMLElement;
    return { root, paragraphs: Array.from(root.querySelectorAll("p")) };
  }

  /**
   * A name wider than the column folds inside itself rather than pushing the column open.
   *
   * `wrap-anywhere` on the block was unguarded in this suite *and* invisible to
   * `tests/browser/test_mobile.py`, which does measure horizontal overflow at 390px on every
   * state of the workbench — invisible because the deterministic review it drives has never
   * produced a name long enough to reach it. A guarantee held by what one fixture happens to say
   * is the failure this whole file exists to stop, so the premise is asserted here rather than
   * hoped for: the corpus really does contain a run of characters wider than the column, so the
   * permission really is reached. That file now supplies the name instead of waiting for one —
   * "a name wider than the column folds instead of widening the phone" — which is the half that
   * knows nothing between this paragraph and the document takes the permission away again.
   *
   * Measured in a browser rather than argued: at a 324px column the shipped component overflows
   * on 0 of the 375 recorded strings and its widest line box is exactly 324.00px; with the
   * anywhere-break deleted, 48 of the 375 overflow, the worst by 218px, and the widest line box
   * drawn is 541.70px — `WIDEST_UNBREAKABLE_TOKEN_PX` reached from the other end. On a phone
   * that is not a paragraph that looks wrong, it is a page that scrolls sideways.
   *
   * `prose.test-corpus.ts` carries both figures and how to take them again.
   */
  it("lets a name too wide for the column break inside itself", () => {
    // The premise, asserted before it is used: without it this test is about nothing.
    expect(
      WIDEST_UNBREAKABLE_TOKEN_PX,
      "no recorded token is wider than the narrowest column, so nothing needs to fold",
    ).toBeGreaterThan(PHONE_COLUMN_PX);

    const { paragraphs } = blocks(
      "The candidate is (src.audiobook.preparation.providers.base.NarrationPreparationProvider) " +
        "and it has one implementation. The evidence pins two references.",
    );
    expect(paragraphs.length).toBeGreaterThan(1);
    for (const paragraph of paragraphs) {
      expect(
        paragraph.className,
        `"${paragraph.className}" cannot break inside a name, so a ` +
          `${WIDEST_UNBREAKABLE_TOKEN_PX}px token pushes a ${PHONE_COLUMN_PX}px column open and the ` +
          "page scrolls sideways",
      ).toMatch(BREAKS_INSIDE_A_TOKEN);
    }
  });

  /**
   * The gap between two blocks, which is the fix itself and was the one thing nothing held.
   *
   * Deleting `mt-2` leaves the DOM split into a paragraph per sentence and draws it as one
   * unbroken wall — so every test that counts paragraphs, joins their text or checks that no
   * character was lost goes on passing, and the surface silently returns to the complaint it was
   * built for. That makes it the most important assertion in this file.
   *
   * Stated against the line box rather than as `mt-2`, because the argument for the value is a
   * ratio: 8px is under a third of the 26.4px line this block sets, which is enough for the eye
   * to find the next start on a second reading and too little to claim paragraph structure the
   * model did not write. A gap at a whole line box is what a `<p>` gets by default and is the
   * claim the cut is careful not to make; a gap at a sixth of one is not visible at all. The
   * bounds are read off the block's own declared type, so changing the size or the leading moves
   * them with it.
   */
  it("puts a real gap between the blocks it cuts, and one no wider than a breath", () => {
    const { root, paragraphs } = blocks(
      "One claim about the abstraction. A second claim about it. And a third to close on.",
    );
    expect(paragraphs, "nothing was cut, so there is no gap to be wrong").toHaveLength(3);

    const size = /(?:^|\s)text-\[([\d.]+)px\](?:\s|$)/.exec(root.className);
    const leading = /(?:^|\s)leading-\[([\d.]+)\](?:\s|$)/.exec(root.className);
    expect(size && leading, `cannot read the type off "${root.className}"`).toBeTruthy();
    const lineBox = Number(size![1]) * Number(leading![1]);

    expect(
      spacingPx(paragraphs[0].className, "mt") ?? 0,
      "the first block is pushed down by a gap above nothing",
    ).toBe(0);

    for (const paragraph of paragraphs.slice(1)) {
      const gap = spacingPx(paragraph.className, "mt");
      expect(
        gap,
        `"${paragraph.className}" puts no gap above a block the cut created, so the blocks are ` +
          "drawn as the wall the cut exists to break",
      ).not.toBeNull();
      const share = gap! / lineBox;
      expect(
        share,
        `${gap}px against a ${lineBox}px line is ${share.toFixed(2)} of a line box — too little ` +
          "for an eye to find the next start",
      ).toBeGreaterThanOrEqual(0.25);
      expect(
        share,
        `${gap}px against a ${lineBox}px line is ${share.toFixed(2)} of a line box, which reads ` +
          "as paragraph structure the model did not write",
      ).toBeLessThanOrEqual(0.6);
    }
  });
});

describe("plainProse", () => {
  it("takes the delimiters off and leaves the words", () => {
    expect(plainProse("The abstraction `NarrationPreparationProvider` is held.")).toBe(
      "The abstraction NarrationPreparationProvider is held.",
    );
  });

  it("returns a string with no backtick in it untouched", () => {
    const plain = "Two adapters reach the same store, and neither owns it.";
    expect(plainProse(plain)).toBe(plain);
    expect(plainProse("")).toBe("");
  });

  it("drops an unmatched backtick, which Prose keeps", () => {
    // A reader can see a stray backtick for the typo it is; a listener only hears the word
    // "backtick" where a name should be.
    expect(plainProse("A stray ` and nothing to close it.")).toBe(
      "A stray  and nothing to close it.",
    );
  });

  it("agrees with Prose about where every span was", () => {
    const sources = [
      "The abstraction `NarrationPreparationProvider` is held.",
      "The delimiter is `` ` `` itself.",
      "Reads ``a`b`` twice.",
      "The module holds `_PROVIDERS: dict[str, ProviderFactory] = {}` at import.",
      "The __init__ of the adapter reads the environment directly.",
    ];
    for (const source of sources) {
      // The chip markers come out of the rendered tree; stripping them has to leave exactly
      // what the string function produced, minus any backtick it dropped as unmatched.
      expect(rendered(<Prose>{source}</Prose>).replace(/[«»]/g, ""), source).toBe(
        plainProse(source),
      );
    }
  });

  it("leaves Markdown's own syntax alone outside a span", () => {
    expect(plainProse("The __init__ of `ports.Clock` runs first.")).toBe(
      "The __init__ of ports.Clock runs first.",
    );
    expect(plainProse("Bears on [1] and *args.")).toBe("Bears on [1] and *args.");
  });
});

describe("sentences", () => {
  /**
   * The acceptance test for this one is that nothing is lost. Every part is a raw slice, so
   * joining the parts back with a single space has to give the recorded string exactly — that
   * is what lets a reading surface put a gap between two claims without editing either.
   */
  it("cuts a paragraph into its sentences and loses nothing", () => {
    const source =
      "The detected structure defines the constant _PROVIDERS in two separate modules. " +
      "This represents duplicated capability knowledge across unrelated modules. " +
      "Because the constant must be kept consistent by hand, it costs more than it earns.";
    const parts = sentences(source);
    expect(parts).toHaveLength(3);
    expect(parts.join(" ")).toBe(source);
  });

  it("returns a string with no boundary in it as one part", () => {
    const single = "The abstraction NarrationPreparationProvider has one implementation.";
    expect(sentences(single)).toEqual([single]);
    expect(sentences("No terminator at all")).toEqual(["No terminator at all"]);
    expect(sentences("")).toEqual([""]);
  });

  /** The reason no abbreviation list is needed: a qualified name has no space after its dots. */
  it("never cuts a qualified name, a path, a decimal or a version", () => {
    const cases = [
      "It is declared in src.audiobook.preparation.providers.registry and nowhere else.",
      "The excerpt is in src/audiobook/benchmarking/corpus.py at the module top.",
      "The threshold is 0.35 and the score was 0.34, so nothing came back.",
      "The retriever is dense-scoped/2.1 and it selected six policies.",
    ];
    for (const source of cases) expect(sentences(source), source).toEqual([source]);
  });

  /**
   * The failure this guard exists for. A cut inside a code span leaves an unmatched delimiter
   * on each side of it, so two literal backticks reach the screen — the one bug `Prose` is
   * written to prevent, reintroduced by the thing that splits the string before it.
   */
  it("skips a backticked name whole, so a stop inside one is never a boundary", () => {
    const source = "It writes `\"text\": \"Python with SQLite. Fast.\"` verbatim to the file.";
    expect(sentences(source)).toEqual([source]);
    const two = "The module holds `a.B` first. Then `c.D` follows it.";
    expect(sentences(two)).toEqual(["The module holds `a.B` first.", "Then `c.D` follows it."]);
  });

  it("lets a sentence open with a quoted name", () => {
    const source = "Policy 3 is the one that bears. `SynthesisProvider` is its only subject.";
    expect(sentences(source)).toEqual([
      "Policy 3 is the one that bears.",
      "`SynthesisProvider` is its only subject.",
    ]);
  });

  it("cuts on a question mark and after a closing quotation mark", () => {
    const source =
      "Does it earn its place? The policy says an abstraction \"must earn its place.\" " +
      "The evidence shows one implementation.";
    const parts = sentences(source);
    expect(parts).toHaveLength(3);
    expect(parts[0]).toBe("Does it earn its place?");
    expect(parts.join(" ")).toBe(source);
  });

  it("does not cut where the next word is lower case, or where there is no space", () => {
    expect(sentences("Bears on policy 3. see also policy 6 for the exception.")).toHaveLength(1);
    expect(sentences("Bears on [1].Then nothing follows the stop.")).toHaveLength(1);
  });

  /** An identifier still arrives byte-identical after the cut, which is the whole contract. */
  it("hands each part to Prose unchanged", () => {
    const source = "The adapter reads __init__ directly. The handler takes *args and forwards.";
    const parts = sentences(source);
    expect(parts).toEqual([
      "The adapter reads __init__ directly.",
      "The handler takes *args and forwards.",
    ]);
    for (const part of parts) expect(rendered(<Prose>{part}</Prose>), part).toBe(part);
  });

  /**
   * Two of the 375 recorded strings carry a newline, and a newline at a boundary falls at a
   * boundary: the block gap takes its place, which is the same break said in the layout.
   */
  it("takes a newline at a boundary as the boundary", () => {
    const source = "First claim.\nSecond claim about it.";
    expect(sentences(source).join(" ")).toBe("First claim. Second claim about it.");
    expect(sentences(source)).toEqual(["First claim.", "Second claim about it."]);
  });

  /**
   * The tail, which is where one block per sentence stops being a rhythm.
   *
   * The longest recorded judgement is nineteen sentences. Cut one to a block it drew as
   * nineteen short paragraphs eight pixels apart — a numbered list of assertions, over a
   * stream of consciousness that argues with itself twice and reverses its own opening claim.
   * So the cut is capped and the sentences over the cap are packed. The median is three and the
   * p90 is five — nearest-rank over the part counts of all 375, which is where the "four" this
   * used to say came from: that is the p75. What the sentence is for survives the correction,
   * because the claim is about the cap and not about the p90: 366 of the 375, 97.6%, never reach
   * this and are cut exactly as before, which is the half that has to be asserted alongside it.
   */
  it("packs the sentences past the cap rather than drawing a list", () => {
    const three = "One claim. A second claim. And a third to close on.";
    expect(sentences(three)).toHaveLength(3);

    const many = Array.from({ length: 19 }, (_, at) => `Claim number ${at + 1} about it.`).join(" ");
    const parts = sentences(many);
    expect(parts.length).toBeLessThanOrEqual(6);
    expect(parts.length).toBeGreaterThan(1);
    // Packed, not dropped: every sentence is still there, in order, and the join is the
    // string the model wrote.
    expect(parts.join(" ")).toBe(many);
  });


  /**
   * Evenly, in the quantity a reader can see — and never opening on the tallest block, which
   * is a property of `pack` rather than a fact about this month's corpus.
   *
   * Three assertions, and they are three different claims. The opening block carries no more
   * than its share *or* is a single sentence, which is the ceiling and the one escape the
   * ceiling has — a block cannot be made shorter than one sentence, so an opening sentence
   * already over the share is left as it is. The opening block is never the tallest, which the
   * ceiling makes impossible where it applies and which has to be checked separately where the
   * escape is taken. And the tallest is held near its share, which is what stops the wall
   * reappearing further down the argument. None of the three implies another, and a run of six
   * equal blocks would satisfy all three.
   *
   * **Run over every recorded string the cap can reach, and that is the repair rather than a
   * preference.** This carried two of them, hand-picked because they are the two that open on
   * their tallest block when the ceiling is deleted — so it caught that one mutation exactly
   * and was blind to any mutation that spares those two. It really is blind: relax the ceiling
   * from `length > share` to `length > share * 1.1` in `pack` and the two go on packing the way
   * they always did, while the 1,838-character `ReviewExecutionStore` judgement opens on a
   * block over its share that is more than one sentence — the ceiling neither met nor escaped,
   * on a string the fixture did not hold. That is the mutation this now fails on.
   *
   * `ui/prose.test-corpus.ts` is all nine, with the extraction written out so the next reader
   * can redo it. Nine strings and the same three assertions is a few hundred microseconds; the
   * fixture this replaces was two strings and one paragraph of prose explaining why those two.
   *
   * 1.75 is loose against the 1.61 the worst of the nine reaches, because it is a bound on
   * lopsidedness and not a target: a cut may only land on a sentence boundary, so a block can
   * never be exactly its share and pinning this tighter would pin today's corpus.
   */
  it("packs by length, and never opens on its tallest block", () => {
    // The population, asserted before it is used. A corpus that quietly lost a string would
    // otherwise make this a property about eight, which is the failure this test is a repair
    // for said one string smaller.
    expect(OVER_CAP, "the recorded strings past the cap").toHaveLength(9);

    for (const { subject, chars, sentences: found, source } of OVER_CAP) {
      // The fixture is a transcript, and a transcript is checked against its own record before
      // anything is concluded from it: a string that lost a character on the way in would make
      // every assertion below a claim about a judgement no model wrote.
      expect(source.length, subject).toBe(chars);
      expect(sentences(source, Number.MAX_SAFE_INTEGER), subject).toHaveLength(found);
      expect(found, `${subject}: not past the cap, so it does not belong here`).toBeGreaterThan(6);

      const parts = sentences(source);
      // Nothing is edited on the way: every part is a raw slice, and the whitespace at each cut
      // is the single space the join puts back. None of the nine holds a newline — the two
      // recorded strings that do are both under the cap.
      expect(parts.join(" "), subject).toBe(source);
      // Exactly the cap, never under it: the packing fills every block it is allowed.
      expect(parts, subject).toHaveLength(6);

      const lengths = parts.map((part) => part.length);
      const share = source.length / parts.length;
      // The escape, asked of the block itself rather than assumed: run the cut again with no
      // cap and see whether the opening block is one sentence.
      const openingIsOneSentence = sentences(parts[0], Number.MAX_SAFE_INTEGER).length === 1;
      expect(
        lengths[0] <= share || openingIsOneSentence,
        `${subject}: the opening block is ${lengths[0]} characters against a ${share.toFixed(1)} ` +
          `share and is ${sentences(parts[0], Number.MAX_SAFE_INTEGER).length} sentences, so the ` +
          "ceiling was neither met nor escaped",
      ).toBe(true);
      expect(lengths[0], `${subject}: the argument opens on its tallest block`).toBeLessThan(
        Math.max(...lengths),
      );
      expect(
        Math.max(...lengths),
        `${subject}: a block behind the opening one is a wall`,
      ).toBeLessThanOrEqual(share * 1.75);
    }
  });

  /**
   * That the objective is squared deviation, which is the one thing above does not hold.
   *
   * `pack` argues at length for least squares over least absolute deviation, and nothing made
   * that argument checkable: swapping `off * off` for `Math.abs(off)` left every test in the
   * frontend passing while one recorded judgement repacked to put a 90-character block into
   * the middle of a 967-character argument. The three assertions above all survive it — a
   * ceiling, a not-tallest-first and a 1.75 bound are satisfied by both objectives, because
   * they bound the extremes and the difference between these two is in the middle.
   *
   * A bound on the smallest block cannot separate them either, and that is worth recording
   * rather than rediscovering: least squares *itself* draws a block at 0.52 of its share on
   * the recorded corpus, so any threshold loose enough to admit the real packing also admits
   * the mutant's.
   *
   * So this asserts optimality instead, and locally rather than globally: move any one cut to
   * the neighbouring sentence boundary and the squared cost must not improve. The shipped
   * answer comes from a dynamic program that is globally optimal, so it is certainly optimal
   * against a one-cut perturbation; an answer from a different objective is not, and the
   * perturbation finds it. Checking it this way rather than by recomputing the optimum keeps
   * the test from carrying a second copy of the algorithm — the failure this whole file is a
   * defence against.
   */
  it("packs to the least squared deviation, not merely to a tolerable spread", () => {
    for (const { subject, source } of OVER_CAP) {
      const all = sentences(source, Number.MAX_SAFE_INTEGER);
      const parts = sentences(source);

      // Which sentences each block took, recovered by counting rather than by re-cutting: a
      // block is a run of whole sentences, so its own sentence count is how many it consumed.
      const groups = parts.map((part) => sentences(part, Number.MAX_SAFE_INTEGER).length);
      expect(
        groups.reduce((total, count) => total + count, 0),
        `${subject}: the blocks do not account for every sentence`,
      ).toBe(all.length);

      // A block spanning sentences `first..through` is what the reader is given: the sentences
      // and the single spaces the cuts became. None of the nine holds a newline, asserted
      // above, so a cut is always exactly one space.
      const spanOf = (first: number, through: number) =>
        all.slice(first, through).reduce((total, one) => total + one.length, 0) + (through - first - 1);

      const share = source.length / parts.length;
      const costOf = (sizes: readonly number[]) => {
        let at = 0;
        return sizes.reduce((total, size) => {
          const off = spanOf(at, (at += size)) - share;
          return total + off * off;
        }, 0);
      };

      const shipped = costOf(groups);
      for (let cut = 0; cut < groups.length - 1; cut += 1) {
        for (const moved of [-1, 1]) {
          const perturbed = [...groups];
          perturbed[cut] += moved;
          perturbed[cut + 1] -= moved;
          if (perturbed[cut] < 1 || perturbed[cut + 1] < 1) continue;
          // The ceiling is part of the problem, not part of the objective, so a perturbation
          // that breaks it is not an arrangement `pack` was allowed to choose and proves
          // nothing about which objective it used.
          const opensOver = spanOf(0, perturbed[0]) > share;
          if (opensOver && perturbed[0] > 1) continue;
          expect(
            costOf(perturbed),
            `${subject}: moving the cut after block ${cut + 1} by ${moved} sentence lowers the ` +
              "squared deviation, so this packing is not the least-squares one",
          ).toBeGreaterThanOrEqual(shipped);
        }
      }
    }
  });

  /**
   * The one case the ceiling gives way to, and the reason it is not a hole in the rule.
   *
   * A block cannot be shorter than one sentence. When the opening sentence is already over its
   * share there is nothing to take out of the first block, so the ceiling is dropped and the
   * block is that sentence and nothing added to it — the shortest opening the string admits.
   * Three of the nine recorded strings past the cap reach this, at 1.02, 1.05 and 1.14 shares,
   * and on none of them does the first block become the tallest. That sentence was a claim
   * about the corpus made in a comment, and the corpus is imported now, so it is counted below
   * instead. The written fixture stays because it reaches the escape by a much wider margin —
   * 1.86 shares — and because it fixes *which* block the escape must produce, which the
   * recorded three do not pin as sharply.
   */
  it("gives the opening ceiling up only to a sentence that cannot be made shorter", () => {
    const long = (at: number) =>
      `Claim ${at} ${"about the abstraction and the policy it bears on ".repeat(4)}here.`;
    const short = (at: number) => `Then ${at} follows.`;
    const source = [
      ...Array.from({ length: 3 }, (_, at) => long(at + 1)),
      ...Array.from({ length: 10 }, (_, at) => short(at + 1)),
    ].join(" ");

    const parts = sentences(source);
    expect(parts.join(" ")).toBe(source);
    expect(parts).toHaveLength(6);
    // The opening sentence alone is over the share, so no ceiling can be met and no sentence is
    // packed in behind it.
    expect(parts[0]).toBe(long(1));
    expect(parts[0].length).toBeGreaterThan(source.length / parts.length);

    // And the same escape, counted over the recorded strings rather than described. Three of
    // the nine open over their share, each by a single sentence that cannot be made shorter.
    const escapes = OVER_CAP.map(({ subject, source: recorded }) => {
      const blocks = sentences(recorded);
      const share = recorded.length / blocks.length;
      return { subject, blocks, shares: blocks[0].length / share };
    }).filter((entry) => entry.shares > 1);
    expect(
      escapes.map((entry) => `${entry.subject} at ${entry.shares.toFixed(2)}`),
      "the recorded strings that open over their share",
    ).toEqual([
      "AtlasFreshnessChecker at 1.14",
      "PolicyStore at 1.02",
      "EdgeResolver at 1.05",
    ]);
    for (const entry of escapes) {
      expect(
        sentences(entry.blocks[0], Number.MAX_SAFE_INTEGER),
        `${entry.subject}: over its share and more than one sentence, so the ceiling was ` +
          "dropped where it could still have been met",
      ).toHaveLength(1);
    }
  });

  /**
   * A packed boundary keeps the model's own whitespace, which is what makes the cap safe on
   * the two judgements that break a paragraph themselves: the cut drops the whitespace at a
   * boundary because the block gap replaces it, and a boundary that is *not* cut has no gap
   * to replace it with. The run stays inside the part, and `whitespace-pre-line` draws it.
   */
  it("keeps the whitespace at a boundary it did not cut", () => {
    const source = "First.\nSecond.\nThird.\nFourth.";
    expect(sentences(source, 2)).toEqual(["First.\nSecond.", "Third.\nFourth."]);
  });

  /**
   * The condition on the guarantee above, written down as a test because a guarantee stated
   * without its condition is the false comment this surface has already shipped six of.
   *
   * "The argument never opens on its tallest block" is a property of `pack`, and `pack` runs
   * only where the model wrote **more** than `MOST_PARTS` sentences — nine of the 375 recorded
   * strings. On the other 366 every boundary is cut, so the blocks *are* the model's sentences
   * and the opening block is the first of them. There is no packing decision left to make: the
   * only way to make that block shorter would be to cut inside a sentence, and every part this
   * function returns is a raw slice of what the model wrote.
   *
   * **Applying the ceiling regardless would change nothing, and that is measured rather than
   * argued.** At `count === mostParts` the table has exactly one feasible partition — one
   * sentence per block — and the ceiling's own escape (`through > 1`) exempts a first block that
   * is a single sentence, which is what that partition makes it. Forcing `pack` to run on every
   * string and comparing the parts changes **0 of the 375**.
   *
   * So the guarantee is conditional, the condition is "where the model wrote more sentences than
   * the cap allows", and this is the corpus's worst case under it: 673 characters in two
   * sentences, the first of them 524 characters — seven line boxes against two. `docs/known-defects.md`
   * carries the decision not to close it and `ui/prose.test-corpus.ts` carries the rest of the
   * measurement, including the 17-line single sentence that is the tallest block in the corpus
   * and that no ceiling on an opening block would reach either.
   */
  it("leaves a string under the cap cut exactly where the model punctuated it, wall and all", () => {
    const { source, chars, sentences: found, blockChars } = UNDER_CAP_WALL;
    // The transcript is checked against its own record before anything is concluded from it.
    expect(source.length, UNDER_CAP_WALL.subject).toBe(chars);
    expect(sentences(source, Number.MAX_SAFE_INTEGER), UNDER_CAP_WALL.subject).toHaveLength(found);
    expect(
      found,
      `${UNDER_CAP_WALL.subject}: past the cap, so it is not this case`,
    ).toBeLessThanOrEqual(6);

    // The record is internally consistent before it is quoted: one line count per block, and
    // the block this entry is about is the tall one. jsdom lays nothing out, so the line counts
    // themselves are checkable only in a browser — `docs/known-defects.md` says where.
    expect(UNDER_CAP_WALL.blockLines).toHaveLength(UNDER_CAP_WALL.blockChars.length);
    expect(UNDER_CAP_WALL.blockLines[0]).toBeGreaterThan(
      Math.max(...UNDER_CAP_WALL.blockLines.slice(1)),
    );

    const parts = sentences(source);
    // The cap changed nothing: every boundary the model wrote is a cut.
    expect(parts).toEqual(sentences(source, Number.MAX_SAFE_INTEGER));
    expect(parts.map((part) => part.length)).toEqual([...blockChars]);
    expect(parts.join(" ")).toBe(source);

    // And it opens on its tallest block, which the nine strings over the cap never do. This is
    // the assertion that makes the condition visible: it is the opposite of what
    // "packs by length, and never opens on its tallest block" asserts, on a string that test
    // cannot reach.
    expect(parts[0].length).toBeGreaterThan(Math.max(...parts.slice(1).map((part) => part.length)));

    // No ceiling could have helped, which is why this is documented rather than fixed: the
    // opening block is already one sentence, and one sentence is the smallest block there is.
    expect(
      sentences(parts[0], Number.MAX_SAFE_INTEGER),
      "the opening block holds more than one sentence, so something could have been taken out " +
        "of it and the hole is a real one after all",
    ).toHaveLength(1);
  });
});

/**
 * A citation in the middle of a sentence, which is our own identifier and not the model's
 * punctuation.
 *
 * The string is the one that started this: a real answer arrived with the bracketed key from
 * the finding listing standing where the finding's name should have been. Both conversation
 * contracts now say the key never goes in a sentence, and this is the net under that — so what
 * is asserted here is every rung of the ladder, including the two that give up the link.
 */
const HELD = "candidate_3dcc1d5ac92ac0b5baf6e2e0";
const RECORDER: Citation = {
  name: "CaseSnapshotRecorder",
  title: "persistence.ports.CaseSnapshotRecorder — a protocol with one implementation",
};

function citing(source: string, onOpen?: (candidateId: string) => void) {
  const { container } = render(
    <Citations find={(id) => (id === HELD ? RECORDER : undefined)} onOpen={onOpen}>
      <div data-testid="cited">
        <Prose>{source}</Prose>
      </div>
    </Citations>,
  );
  return container.querySelector("[data-testid='cited']") as HTMLElement;
}

describe("a cited finding", () => {
  it("draws the name the sentence needed, and never the key", () => {
    const host = citing(`Finding [${HELD}] is held because intent cannot be read.`, () => {});

    expect(host.textContent).toBe(
      "Finding CaseSnapshotRecorder is held because intent cannot be read.",
    );
    expect(host.textContent).not.toContain("candidate_");
  });

  it("opens the row it points at", () => {
    const open = vi.fn();
    citing(`Finding [${HELD}] is held.`, open);

    fireEvent.click(screen.getByRole("button", { name: "CaseSnapshotRecorder" }));
    expect(open).toHaveBeenCalledWith(HELD);
  });

  it("wears the mark only where there is somewhere to go", () => {
    const goes = citing(`Finding [${HELD}] is held.`, () => {});
    const stays = citing(`Finding [${HELD}] is held.`);

    // `--mark` is the product's one non-verdict chroma and it means "the way to the source".
    expect(goes.querySelector("button")?.className).toContain("text-mark");
    // Nowhere to go, so no promise of one: the name, drawn as the name it is.
    expect(stays.querySelector("button")).toBeNull();
    expect(stays.querySelector("code")?.textContent).toBe("CaseSnapshotRecorder");
    expect(stays.querySelector("code")?.className).not.toContain("text-mark");
  });

  it("reads the key with its brackets and without them", () => {
    expect(citing(`Finding ${HELD} is held.`, () => {}).textContent).toBe(
      "Finding CaseSnapshotRecorder is held.",
    );
  });

  it("keeps the whole key where this review holds no such finding", () => {
    const missing = "candidate_0000000000000000000000ff";
    const host = citing(`Finding [${missing}] is held.`);

    // The whole identifier, in a chip: a machine string is a thing somebody copies, and half
    // of one is worse than all of it. The title is what says what happened to it.
    const chip = host.querySelector("code") as HTMLElement;
    expect(chip.textContent).toBe(`[${missing}]`);
    expect(chip.getAttribute("title")).toContain("holds no finding");
  });

  it("leaves a quoted identifier as the string it was asked to show", () => {
    // A code span's content is never re-parsed here. A reader who backticked an identifier —
    // or a model quoting one back at them — meant to be shown it.
    const host = citing(`You asked about \`${HELD}\`.`, () => {});
    expect(host.querySelector("button")).toBeNull();
    expect(host.querySelector("code")?.textContent).toBe(HELD);
  });

  it("does not take a word that merely starts candidate_ for a key", () => {
    const plain = "The candidate_summary field is not an identifier.";
    expect(citing(plain, () => {}).textContent).toBe(plain);
  });

  it("resolves through plainProse the same way, so a title and its paragraph agree", () => {
    const find = (id: string) => (id === HELD ? RECORDER : undefined);
    expect(plainProse(`Finding [${HELD}] is held.`, find)).toBe(
      "Finding CaseSnapshotRecorder is held.",
    );
    // No lookup, so no name — and the brackets still come off, because they are punctuation
    // written for a renderer, which is the same reason a backtick's do.
    expect(plainProse(`Finding [${HELD}] is held.`)).toBe(`Finding ${HELD} is held.`);
  });
});
