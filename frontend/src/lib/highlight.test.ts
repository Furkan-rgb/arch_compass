import { describe, expect, it } from "vitest";

import { escapeHtml, highlight, isSupported, languageForPath } from "./highlight";

describe("colouring code", () => {
  it("marks up the parts of a Python excerpt that carry meaning", () => {
    const html = highlight('class Clock:\n    """Now."""\n', "python");
    expect(html).toContain("hljs-keyword");
    expect(html).toContain("hljs-string");
    // The text itself survives the markup.
    expect(html).toContain("Clock");
  });

  it("takes the language from the file the excerpt was read out of", () => {
    expect(languageForPath("src/archcompass/ports.py")).toBe("python");
    expect(languageForPath("pyproject.toml")).toBeUndefined();
    expect(languageForPath("Makefile")).toBeUndefined();
    expect(languageForPath(null)).toBeUndefined();
  });

  it("never guesses", () => {
    // Detection on a four-line excerpt is a coin toss, and confidently wrong colouring is
    // worse than none: the colours are a claim about what the tokens mean.
    const html = highlight("def judge(candidate):\n    return candidate\n");
    expect(html).not.toContain("hljs-");
    expect(html).toContain("def judge(candidate):");
  });

  it("escapes code it is not colouring, so an excerpt cannot become markup", () => {
    // The excerpt is repository text and reaches the DOM through `innerHTML`.
    expect(highlight('<img src="x" onerror="alert(1)">')).toBe(
      "&lt;img src=&quot;x&quot; onerror=&quot;alert(1)&quot;&gt;",
    );
    expect(escapeHtml("a & b < c")).toBe("a &amp; b &lt; c");
  });

  it("escapes code it is colouring too", () => {
    const html = highlight('x = "<script>"', "python");
    expect(html).not.toContain("<script>");
    expect(html).toContain("&lt;script&gt;");
  });

  it("knows which fences it can colour", () => {
    expect(isSupported("python")).toBe(true);
    expect(isSupported("py")).toBe(true);
    expect(isSupported("brainfuck")).toBe(false);
    expect(isSupported(undefined)).toBe(false);
  });

  it("returns the excerpt rather than throwing on a fragment", () => {
    // Evidence is a slice out of the middle of a file, so it is routinely unbalanced.
    expect(highlight('    return Preferences.from_row(row)\n        """', "python")).toContain(
      "Preferences",
    );
  });
});
