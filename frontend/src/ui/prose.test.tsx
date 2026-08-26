import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { INLINE_CODE_BARE, Prose, plainProse } from "./prose";

/**
 * The scanner in `ui/prose.tsx`, which is a parser and will therefore be wrong in an edge
 * case if nobody checks.
 *
 * The acceptance test is the second block: a name the model quotes has to arrive on screen
 * byte-identical, because a wrong name looks exactly like a right one and is a worse failure
 * than the backtick this whole file exists to remove. The strings there are taken from real
 * recorded model output.
 */

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
   * contains: two bare `__init__`, one bare `__file__`, 113 bare snake_case tokens, and 52
   * bracketed runs. A full Markdown pipeline turns the first of those into a bold "init" —
   * CommonMark's intraword rule does not save it, because the leading `__` is preceded by a
   * space and so is left-flanking.
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
