/**
 * Colouring the code the application read, as opposed to the code a model wrote.
 *
 * Two different amounts of evidence, and the same policy applied to each. A fenced block in an
 * answer is coloured only when it names its language, because a short snippet is ambiguous
 * between half the registered grammars and a wrong guess lights up the wrong words with
 * complete confidence. A recorded excerpt was read out of a file at a path the review pinned,
 * so `.py` is not a guess about that file — it is what the repository calls it.
 */

import { render } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { HighlightedCode, languageForPath } from "./markdown";

describe("languageForPath", () => {
  it("names the grammar the extension names", () => {
    expect(languageForPath("src/archcompass/domain/case.py")).toBe("python");
    expect(languageForPath("frontend/src/markdown.tsx")).toBe("typescript");
    expect(languageForPath("config/models.google.yaml")).toBe("yaml");
    expect(languageForPath("package.json")).toBe("json");
    expect(languageForPath("scripts/run.sh")).toBe("bash");
    expect(languageForPath("migrations/019_revisions.sql")).toBe("sql");
    expect(languageForPath("fix.patch")).toBe("diff");
  });

  it("treats the JavaScript family as TypeScript, which is the grammar carried", () => {
    // Not a compromise: the TypeScript grammar is a superset, so a `.js` file is coloured
    // correctly by it. Registering a second near-identical grammar would cost bundle for
    // nothing — and the bundle cost is why refractor's bare core is used at all.
    for (const path of ["a.js", "a.jsx", "a.mjs", "a.cjs"]) {
      expect(languageForPath(path)).toBe("typescript");
    }
  });

  it("is case-insensitive about the extension but not about anything else", () => {
    expect(languageForPath("Legacy/MODULE.PY")).toBe("python");
  });

  it("has nothing to say about a file whose extension it does not carry", () => {
    // Plain monospace is the honest result. A repository ArchCompass cannot analyse is not one
    // whose excerpts it should pretend to understand either.
    expect(languageForPath("lib/thing.rb")).toBeNull();
    expect(languageForPath("Makefile")).toBeNull();
    expect(languageForPath("LICENSE")).toBeNull();
  });

  it("reads the extension from the last segment, and a dotfile is not an extension", () => {
    // `a.b/c` has no extension at all, and `.gitignore` has nothing before its dot — its name
    // is not a claim about a grammar.
    expect(languageForPath("has.dots/in-a-directory")).toBeNull();
    expect(languageForPath(".gitignore")).toBeNull();
    expect(languageForPath("mod.test.ts")).toBe("typescript");
  });

  it("says nothing where there is no path, which is a span that could not be read", () => {
    expect(languageForPath(null)).toBeNull();
    expect(languageForPath(undefined)).toBeNull();
    expect(languageForPath("")).toBeNull();
  });
});

describe("HighlightedCode", () => {
  it("tokenizes Python so a reader can tell a keyword from a string", () => {
    const { container } = render(
      <HighlightedCode code={'def sink(name):\n    return "voice"\n'} language="python" />,
    );

    // The token classes are what the sheet colours; asserting them rather than a colour keeps
    // this a test of the renderer and not of the palette.
    const tokens = [...container.querySelectorAll("span.token")];
    expect(tokens.length).toBeGreaterThan(0);
    expect(container.querySelector("span.token.keyword")?.textContent).toBe("def");
    expect(container.querySelector("span.token.string")?.textContent).toBe('"voice"');
    // Every character survives the trip. A highlighter that dropped one would be reporting the
    // reader's own file wrongly, which is worse than not colouring it (§12.0).
    expect(container.textContent).toBe('def sink(name):\n    return "voice"\n');
  });

  it("nests a token inside the construct that contains it", () => {
    // Refractor returns a tree rather than a flat run, so the renderer has to recurse. An
    // f-string is the shortest thing that proves it: the interpolation is a token inside the
    // string token, and a renderer that only walked the top level would print `{name}` twice or
    // not at all.
    const code = 'sink = f"the {name} voice"\n';
    const { container } = render(<HighlightedCode code={code} language="python" />);

    expect(container.querySelector("span.token .token")).not.toBeNull();
    expect(container.textContent).toBe(code);
  });

  it("renders the code plain when there is no grammar to be sure of", () => {
    const { container } = render(
      <HighlightedCode code="module Thing; end" language={null} />,
    );

    expect(container.querySelector("span.token")).toBeNull();
    expect(container.textContent).toBe("module Thing; end");
  });

  it("renders it plain rather than nothing when a grammar is not registered", () => {
    // The map only names registered grammars, so this is a guard rather than a path anything
    // takes today — and the failure it prevents is a blank excerpt, not a mis-coloured one.
    const { container } = render(
      <HighlightedCode code="SELECT 1" language="not-a-grammar" />,
    );

    expect(container.textContent).toBe("SELECT 1");
  });

  it("survives a fragment that begins inside an unclosed construct", () => {
    // An excerpt is a recorded span, so it can start mid-file and end mid-string. Losing the
    // reader's code to the highlighter would be a far worse outcome than showing it plain.
    const fragment = '    return "an unterminated string\n';
    const { container } = render(
      <HighlightedCode code={fragment} language="python" />,
    );

    expect(container.textContent).toBe(fragment);
  });
});
