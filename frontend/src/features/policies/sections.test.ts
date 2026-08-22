import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";

import {
  REQUIRED_SECTIONS,
  SECTION_PROMPTS,
  missingSections,
  policyTemplate,
  sectionsIn,
} from "./sections";

describe("policy sections", () => {
  /**
   * The list is the workspace's, not this page's. If `REQUIRED_SECTIONS` in the Markdown
   * adapter grows a tenth section, the editor would go on accepting drafts the workspace
   * then refuses — so the two are compared directly.
   */
  it("matches the sections the workspace parser requires", () => {
    const adapter = readFileSync(
      resolve(process.cwd(), "../src/archcompass/policies/adapters/markdown.py"),
      "utf8",
    );
    const block = /REQUIRED_SECTIONS = \{([^}]*)\}/.exec(adapter)?.[1] ?? "";
    const required = [...block.matchAll(/"([^"]+)"/g)].map((match) => match[1]).sort();

    expect(required).toEqual([...REQUIRED_SECTIONS].map((name) => name.toLowerCase()).sort());
  });

  it("reads a section only when something is written under it", () => {
    const body = "## Intent\n\nKeep adapters thin.\n\n## Guidance\n\n## Signals\n\nWide adapters.\n";
    const sections = sectionsIn(body);
    expect(sections.get("intent")).toBe("Keep adapters thin.");
    expect(sections.get("guidance")).toBe("");
    expect(missingSections(body)).toContain("Guidance");
    expect(missingSections(body)).not.toContain("Intent");
  });

  /**
   * The claim this test used to make was that the scaffold "already satisfies the parser",
   * and it was true: the template wrote its own prompt under every heading and
   * `sectionStates` asked only whether a heading had text beneath it. So a title, a
   * description and an untouched body were enough to press Create policy, and what reached
   * the retrieval corpus — and the judge, as authored guidance — was nine instructions to
   * the author. A scaffold is a shape to fill in; nothing about it is written yet.
   */
  it("scaffolds the sections without writing any of them", () => {
    const template = policyTemplate();
    for (const section of REQUIRED_SECTIONS) {
      expect(template).toContain(`## ${section}`);
    }
    expect(missingSections(template)).toEqual([...REQUIRED_SECTIONS]);
    expect(template).not.toContain(SECTION_PROMPTS.Intent);
  });

  it("does not count a section that still holds the prompt it was asked", () => {
    const pasted = `## Intent\n\n${SECTION_PROMPTS.Intent}\n\n## Guidance\n\nName the port.\n`;
    expect(missingSections(pasted)).toContain("Intent");
    expect(missingSections(pasted)).not.toContain("Guidance");
  });

  it("ignores headings that are not level two, as the parser does", () => {
    expect(sectionsIn("# Intent\n\nNot a section.\n").size).toBe(0);
    expect(sectionsIn("### Intent\n\nNot a section.\n").size).toBe(0);
  });
});
