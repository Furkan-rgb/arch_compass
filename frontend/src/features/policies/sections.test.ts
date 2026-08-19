import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";

import { REQUIRED_SECTIONS, missingSections, policyTemplate, sectionsIn } from "./sections";

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

  it("scaffolds a draft that already satisfies the parser", () => {
    expect(missingSections(policyTemplate())).toEqual([]);
    for (const section of REQUIRED_SECTIONS) {
      expect(policyTemplate()).toContain(`## ${section}`);
    }
  });

  it("ignores headings that are not level two, as the parser does", () => {
    expect(sectionsIn("# Intent\n\nNot a section.\n").size).toBe(0);
    expect(sectionsIn("### Intent\n\nNot a section.\n").size).toBe(0);
  });
});
