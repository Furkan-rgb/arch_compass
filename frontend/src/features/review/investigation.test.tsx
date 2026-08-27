import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

import { render } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import type { Investigation, InvestigationLookup } from "../../api";
import { InvestigationTranscript, investigationSummary } from "./investigation";
import { parsePythonList, splitGutter, splitTrailer } from "./lookup-result";

/**
 * What a lookup result is drawn as, shape by shape.
 *
 * The surface had one rendering for six shapes — every result into one `<code>` at one ink,
 * uncoloured — and the reason it is six now rather than one call to `highlight()` is in the
 * docstring of `lookup-result.tsx`: colours are a claim about what the tokens mean, and 45% of
 * this surface is not code.
 *
 * Every fixture here is a real result, copied out of a read-only copy of
 * `.archcompass/workspace.sqlite3` — `core_review_snapshots.review_json ->
 * investigation_manifest[].lookups[]`, 955 lookups over 7 reviews — and shortened. Where a
 * count appears in a comment it was measured over those 955 and the method is stated in
 * `lookup-result.tsx`. Nothing here is a shape somebody imagined the tools might produce.
 *
 * jsdom applies no stylesheet and lays nothing out, so nothing in this file is a measurement.
 * What it can see is which element a string is in, which is the whole of what "drawn as the
 * thing it is" means here: a line number that is a column rather than the first characters of
 * a line of Python, a basename that is a different element from its directory, a path list
 * that is a list. The one geometric claim — that the gutter and the code sit on the same
 * baselines — belongs to `ui/code.tsx`'s `NumberedCode`, which both surfaces now share.
 */

function transcript(lookups: InvestigationLookup[]): Investigation {
  return {
    candidate_id: "candidate-1",
    lookups,
    closing: "",
    withheld: "",
    termination: "natural_end",
    atlas_fingerprint: "content-fingerprint",
    prompt_identity: "investigate-hinge:v1",
    model_identity: "fake:deterministic",
  };
}

function draw(lookups: InvestigationLookup[]) {
  return render(<InvestigationTranscript investigation={transcript(lookups)} />).container;
}

/** The first line of a real `read_file` result, with its gutter, and the trailer it ends on. */
const READ_FILE = [
  '  1  """Provider protocol and types shared by local and hosted TTS backends."""',
  "  2  ",
  "  3  from __future__ import annotations",
  "",
  "[Read 3 lines (lines 1-3 of 212 total). 209 lines remaining from offset 3.]",
].join("\n");

describe("a lookup result is drawn as the thing it is", () => {
  it("colours a read file as its own language, with the gutter as a column rather than as code", () => {
    // The whole of the user's report, on 501 of the 955 stored lookups. The gutter has to come
    // off first: `  1  """Provider` handed to a Python grammar colours the number as a literal
    // and the docstring that opens on the same line is then read from the wrong offset.
    const container = draw([
      { tool: "read_file", arguments: { file_path: "/src/providers/base.py" }, result: READ_FILE },
    ]);

    const code = container.querySelector("code.language-python");
    expect(code).not.toBeNull();
    // Coloured, which is the thing that was missing.
    expect(code!.innerHTML).toContain("hljs-");
    // And coloured as one document: `from __future__ import annotations` is three keywords,
    // which is what a grammar reading the body finds and what a grammar reading `  3  from …`
    // would have had to recover from.
    expect(code!.innerHTML).toContain("hljs-keyword");
    // The numbers are not in the code. If they were, the colouring above would be a claim
    // about a string that is not the file's.
    expect(code!.textContent).not.toContain("  1  ");
    expect(code!.textContent).toContain('"""Provider protocol');

    // They are their own column instead, hidden from a screen reader for the same reason
    // `ui/code.tsx` hides the excerpt's: a line number is furniture beside the line.
    const gutter = container.querySelector('[aria-hidden="true"]');
    expect(gutter!.textContent).toBe("123");
  });

  it("says the tool's own note about a result beside the result, not inside it", () => {
    // 382 of the 501 stored `read_file` results end on a bracketed sentence about the read
    // itself. Left in the body it is a fourth line of Python numbered 4.
    const container = draw([
      { tool: "read_file", arguments: { file_path: "/src/providers/base.py" }, result: READ_FILE },
    ]);
    const code = container.querySelector("code.language-python");
    expect(code!.textContent).not.toContain("209 lines remaining");
    expect(container.textContent).toContain("209 lines remaining from offset 3.");
    // Three numbers, not four: the note is not a line of the file.
    expect(container.querySelector('[aria-hidden="true"]')!.textContent).toBe("123");
  });

  it("gives a grep result its basenames, and does not colour any of it", () => {
    // 320 of the 369 stored grep results are exactly this: a bare list of absolute paths, no
    // line numbers, no matched text. What a reader does with all 320 is scan for a filename.
    const container = draw([
      {
        tool: "grep",
        arguments: { pattern: "SynthesisProvider" },
        result: "/src/audiobook/synthesis/providers/base.py\n/src/audiobook/ui/library.py",
      },
    ]);
    const rows = [...container.querySelectorAll("li li")];
    expect(rows).toHaveLength(2);
    expect(rows[0].textContent).toBe("/src/audiobook/synthesis/providers/base.py");
    // The basename is its own element, which is the whole device — the directory recedes and
    // the name the eye is hunting for is in full ink.
    expect(rows[0].querySelector("span")!.textContent).toBe("base.py");
    expect(rows[1].querySelector("span")!.textContent).toBe("library.py");
    // A list of paths is not code and is not coloured as code.
    expect(container.querySelector("[class*=language-]")).toBeNull();
    expect(container.innerHTML).not.toContain("hljs-");
  });

  it("reads a search that found nothing as a state rather than as a line of text", () => {
    const container = draw([
      { tool: "grep", arguments: { pattern: "CODEOWNERS" }, result: "No matches found" },
    ]);
    expect(container.textContent).toContain("Nothing in the repository matched.");
    expect(container.querySelector("ul ul")).toBeNull();
  });

  it("keeps a search that stopped early saying so", () => {
    // 3 of the 369. The sentence is the reason the list above it cannot be read as complete,
    // which is exactly what a reader weighing a verdict needs and exactly what disappears
    // when it is the last paragraph of a monospace wall.
    const container = draw([
      {
        tool: "grep",
        arguments: { pattern: "class " },
        result:
          "/src/archcompass/domain/atlas.py\n/src/archcompass/domain/case.py\n\n" +
          "Note: the search stopped early (it hit its time limit or the maximum match count).",
      },
    ]);
    expect([...container.querySelectorAll("li li")]).toHaveLength(2);
    expect(container.textContent).toContain("Note: the search stopped early");
  });

  it("turns a glob's one long line into the list it is a repr of", () => {
    // All 38 stored glob results are a single-line Python list repr, and the longest is 13,111
    // characters on one line inside a 256px-high box. The defect is a list drawn as a
    // sentence; colour was never its fix.
    const container = draw([
      {
        tool: "glob",
        arguments: { pattern: "**/*.json" },
        result: "['/.claude/settings.json', '/.vscode/settings.json', '/package.json']",
      },
    ]);
    const rows = [...container.querySelectorAll("li li")];
    expect(rows).toHaveLength(3);
    expect(rows[0].textContent).toBe("/.claude/settings.json");
    expect(rows[2].querySelector("span")!.textContent).toBe("package.json");
    // The repr's own punctuation is gone, which is the proof it was parsed rather than split.
    expect(container.textContent).not.toContain("['");
  });

  it("shows the raw result when a glob repr will not parse, rather than showing nothing", () => {
    // A parser that drops what it did not understand is worse than no parser. `parsePythonList`
    // round-trips before it answers, so an escape it does not implement fails the comparison.
    const container = draw([
      { tool: "glob", arguments: { pattern: "*" }, result: "['/a/it\\'s.py', '/b.py']" },
    ]);
    expect(container.querySelector("li li")).toBeNull();
    expect(container.textContent).toContain("['/a/it\\'s.py', '/b.py']");
  });

  it("gives a related-code row its three fields at three weights, and names the relation", () => {
    const container = draw([
      {
        tool: "related_code",
        arguments: { qualified_name: "archcompass.ports.atlas.SourceReader", relation: "implementations" },
        result: [
          "1 related nodes",
          "  archcompass.analysis.adapters.source_reader.SafeSourceReader  [class]  src/archcompass/analysis/adapters/source_reader.py:10-53",
          "  archcompass.analysis.adapters.source_reader.SafeSourceReader --implements--> archcompass.ports.atlas.SourceReader  (by types)",
        ].join("\n"),
      },
    ]);
    expect(container.textContent).toContain("1 related nodes");
    // The location goes through `PathRef`, which is the product's one device for getting back
    // to the source — the same component an evidence block uses, so it copies `path:line` and
    // offers an editor link on the same terms.
    const source = container.querySelector('button[aria-label^="Copy src/"]');
    expect(source).not.toBeNull();
    expect(source!.textContent).toBe("src/archcompass/analysis/adapters/source_reader.py:10-53");
    // The kind is a field of its own rather than the literal `[class]` it arrives as.
    expect(container.textContent).toContain("class");
    expect(container.textContent).not.toContain("[class]");
    // The arrow is the atlas's, so the relation is named and the raw edge syntax is not shown.
    expect(container.textContent).toContain("implements");
    expect(container.textContent).not.toContain("--implements-->");
    expect(container.querySelector("svg")).not.toBeNull();
  });

  it("does not dress a tool's refusal up as a listing", () => {
    // 2 of the 39 stored `related_code` results are the tool saying it does not know the name,
    // in a full sentence. A count line over an empty list would read as a listing that failed.
    const refusal =
      "Nothing in this repository is called 'archcompass.domain.repository.DEFAULT_BRANCH_NAME'." +
      " Names are exact and qualified, like 'ports.TaskStore'.";
    const container = draw([
      { tool: "related_code", arguments: { qualified_name: "x" }, result: refusal },
    ]);
    expect(container.textContent).toContain(refusal);
    expect(container.querySelector("li ul")).toBeNull();
  });

  it("colours a policy through the grammar already in the bundle, not through the renderer", () => {
    // One lookup in 955 is Markdown, which is nowhere near paying for `ui/markdown.tsx` and the
    // ~160KB deliberately split out of this bundle. `markdown` is one of the nine grammars
    // `lib/highlight.ts` already registers and `finding-detail.tsx` already pulls in, so the
    // headings are told from the body for nothing.
    const container = draw([
      {
        tool: "search_policies",
        arguments: { query: "single implementation port" },
        result: "Policy ID: honor-substitution-contracts\n## Intent\nKeep an abstraction worth depending on.",
      },
    ]);
    const code = container.querySelector("code.language-markdown");
    expect(code).not.toBeNull();
    expect(code!.innerHTML).toContain("hljs-section");
    expect(code!.textContent).toContain("Keep an abstraction worth depending on.");
  });

  it("still renders a tool this file has never seen", () => {
    // `flagged_signals`, `ls`, `describe_code` and `read_code` are all reachable from the
    // investigator and none of them occurs in the store. A dispatch that only drew the six
    // measured shapes would make a seventh disappear.
    const container = draw([
      { tool: "flagged_signals", arguments: {}, result: "no signals were flagged" },
    ]);
    expect(container.textContent).toContain("no signals were flagged");
  });

  it("renders a result containing markup as text, on every shape", () => {
    // The one security question on this surface rather than a question of taste. Highlighted
    // output reaches the DOM through `dangerouslySetInnerHTML`, and a lookup result is
    // repository text chosen by a model — so every shape is checked, not the two that colour.
    const payload = '<script>alert(1)</script>';
    const container = draw([
      { tool: "read_file", arguments: { file_path: "/a.py" }, result: `  1  x = "${payload}"` },
      { tool: "grep", arguments: { pattern: "x" }, result: `/${payload}.py` },
      { tool: "glob", arguments: { pattern: "*" }, result: `['/${payload}.py']` },
      {
        tool: "related_code",
        arguments: { qualified_name: "x" },
        result: `1 related nodes\n  ${payload}  [class]  src/a.py:1-2`,
      },
      { tool: "search_policies", arguments: { query: "x" }, result: `## ${payload}` },
      { tool: "flagged_signals", arguments: {}, result: payload },
    ]);

    expect(container.querySelector("script")).toBeNull();
    expect(container.querySelectorAll("script")).toHaveLength(0);
    // Six results, and the payload is readable text in every one of them rather than markup.
    expect(container.textContent!.split(payload)).toHaveLength(7);
  });
});

describe("the parsers a shape is chosen by", () => {
  it("splits a numbered listing only when every line carries a number", () => {
    expect(splitGutter("  1  a\n  2  b")).toEqual({ startLine: 1, code: "a\nb" });
    //  98/ 99/100 is where the padding changes width, and the padding is not part of either
    // column: the code starts after the two spaces, wherever the number ended.
    expect(splitGutter(" 99  a\n100  b")).toEqual({ startLine: 99, code: "a\nb" });
    // A blank line in the file is a number and nothing after it.
    expect(splitGutter("  1  a\n  2  ")).toEqual({ startLine: 1, code: "a\n" });
    // One line without a number and the whole split is off. A partial split would hand a
    // grammar a body that is code on some lines and `  42  code` on others.
    expect(splitGutter("  1  a\nb")).toBeNull();
  });

  it("takes the tool's trailing sentence off the end and nowhere else", () => {
    expect(splitTrailer("a\n\n[Read 3 lines]")).toEqual({ body: "a", note: "Read 3 lines" });
    expect(splitTrailer("a\n\nNote: it stopped")).toEqual({ body: "a", note: "Note: it stopped" });
    // Anchored to the end after a blank line, so a bracket in the middle of a result is part
    // of the result — which for a list of Python paths is most of them.
    expect(splitTrailer("[a]\nb")).toEqual({ body: "[a]\nb", note: "" });
    expect(splitTrailer("x = [1]")).toEqual({ body: "x = [1]", note: "" });
  });

  it("answers null rather than a half-parsed list", () => {
    expect(parsePythonList("['/a.py', '/b.py']")).toEqual(["/a.py", "/b.py"]);
    expect(parsePythonList("[]")).toEqual([]);
    // The round trip is the check. An escape this does not implement changes the length of the
    // rebuilt string, so it cannot come back subtly wrong — a mangled path is the one failure
    // the reader has no way to notice.
    expect(parsePythonList("['/a\\'b.py']")).toBeNull();
    expect(parsePythonList("['/a, b.py', '/c.py']")).toEqual(["/a, b.py", "/c.py"]);
    expect(parsePythonList("not a list")).toBeNull();
  });
});

/**
 * What the closed fold says about how the looking ended.
 *
 * Seven of the eight terminations start "cut short" and are news. The eighth, `natural_end`,
 * is not: the count beside it has already said how much looking there was, and "the pass
 * stopped looking" after it repeats that in worse words. So the natural end prints nothing,
 * and the cases that are not a natural end must not be able to fall into that same silence —
 * an unrecorded reason especially, which is every investigation stored before terminations
 * existed and would otherwise read as a pass that ran to its own end.
 *
 * The last test here is the one that would have caught the defect the others did not. Five of
 * the eight members had a clause, and they were not the five that occur: over the 147 stored
 * investigations the endings are `natural_end` 143, `repeated_tool_call` 3 and
 * `malformed_judgement` 1, so the second commonest real ending printed "ended: Repeated tool
 * call" — the enum member, title-cased — while four hand-written clauses covered endings that
 * have never happened once. A test naming the members one at a time cannot see that: it
 * passes on exactly the members somebody thought to name.
 */
describe("how the fold says an investigation ended", () => {
  const ended = (termination: Investigation["termination"]) => {
    const lookups: InvestigationLookup[] = [
      { tool: "ls", arguments: { path: "billing/" }, result: "gateway.py" },
      { tool: "read_file", arguments: { file_path: "billing/gateway.py" }, result: "  1  x" },
    ];
    return investigationSummary({ ...transcript(lookups), termination });
  };

  it("says nothing at all about a pass that was not cut short", () => {
    expect(ended("natural_end")).toBe("2 lookups");
  });

  it("says a truncation was a truncation", () => {
    expect(ended("lookup_limit")).toBe("2 lookups · cut short: no lookups left");
    expect(ended("provider_error")).toBe("2 lookups · cut short: the model stopped answering");
  });

  it("does not read an unrecorded reason as a pass that ran to its end", () => {
    expect(ended(null)).toBe("2 lookups · end not recorded");
  });

  it("says the stuck loop was a stuck loop, not a spent budget", () => {
    // `domain/review.py` is explicit that this is not a ceiling being reached: the same
    // question was put to the same read-only tool a third time against a repository that
    // cannot change, so the third answer is the second answer.
    expect(ended("repeated_tool_call")).toBe("2 lookups · cut short: it began repeating itself");
    expect(ended("wall_clock_limit")).toBe("2 lookups · cut short: out of time");
  });

  it("still says something about a termination it has never heard of", () => {
    // Not a member of the union — every member is spoken for now, which is the point of the
    // test below. The fallback exists for the one the backend adds before this file learns
    // it, so the only honest way to reach it is a value the contract does not yet carry.
    const later = "quota_exhausted" as Investigation["termination"];
    expect(ended(later)).toBe("2 lookups · ended: Quota exhausted");
  });

  /**
   * Every ending the contract can carry has words of its own, read off the contract.
   *
   * The list is not written here on purpose. A test that names the members is a test that
   * agrees with whoever last edited the map, and that is exactly how `repeated_tool_call`
   * and `wall_clock_limit` went four months without a clause. `openapi.generated.ts` is
   * generated from the backend enum, so a member added there fails this before it can reach
   * a reader as a title-cased identifier.
   */
  it("has words for every ending the backend can send", () => {
    // Resolved from this file rather than off the working directory, so it is found whichever
    // directory vitest runs from. `fileURLToPath` and not a `URL` object: under jsdom the
    // global `URL` is jsdom's own class, which `readFileSync` refuses.
    const generated = readFileSync(
      fileURLToPath(import.meta.url).replace(
        /features\/review\/investigation\.test\.tsx$/,
        "openapi.generated.ts",
      ),
      "utf8",
    );
    const union = generated.match(/"Termination": ([^;]+);/)?.[1];
    expect(union, "the Termination union moved in the generated types").toBeDefined();
    const members = [...union!.matchAll(/"([a-z_]+)"/g)].map((match) => match[1]);
    // Eight today. If this number is what fails, the enum grew and the map has not heard.
    expect(members).toHaveLength(8);

    for (const member of members) {
      const summary = ended(member as Investigation["termination"]);
      if (member === "natural_end") {
        // The one that earns no clause, which is a decision rather than an omission.
        expect(summary, member).toBe("2 lookups");
        continue;
      }
      expect(summary, member).toMatch(/^2 lookups · cut short: /);
      // `ended: Repeated tool call` is the shape this exists to forbid.
      expect(summary, member).not.toMatch(/ended: /);
    }
  });
});
