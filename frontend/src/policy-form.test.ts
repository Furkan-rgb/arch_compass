import { describe, expect, it } from "vitest";

import { POLICY_BODY_SKELETON, policyDraft, policyFormValues } from "./policy-form";
import type { Policy } from "./types";

const STORED: Policy = {
  id: "keep-imports-pointing-inward",
  title: "Keep imports pointing inward",
  description: "A module that imports its caller has no boundary left to defend.",
  scope: "general",
  applies_to: null,
  strength: "preferred",
  tags: ["layering", "dependencies"],
  source: { author: "Workspace", inspiration: [] },
  body: "## Intent\nKeep the arrows going one way.",
  source_path: "/workspace/.archcompass/policies/keep-imports-pointing-inward.md",
  content_hash: "one",
  origin: "workspace",
};

describe("policyFormValues", () => {
  it("opens a new policy on the section frame the corpus is written in", () => {
    const values = policyFormValues(null);

    expect(values.title).toBe("");
    expect(values.strength).toBe("guidance");
    // All nine, because the parser requires all nine: a form that offered three would be
    // teaching someone to write a policy the workspace then refuses.
    expect(values.body).toBe(POLICY_BODY_SKELETON);
    expect(values.body.match(/^## /gm)).toHaveLength(9);
    expect(values.body).toContain("## Diagnostic questions");
    expect(values.body).toContain("## Related policies");
  });

  it("shows a stored policy as it is, tags on one line", () => {
    const values = policyFormValues(STORED);

    expect(values.title).toBe("Keep imports pointing inward");
    expect(values.tags).toBe("layering, dependencies");
    expect(values.strength).toBe("preferred");
    expect(values.body).toBe(STORED.body);
  });
});

describe("policyDraft", () => {
  it("sends what was written and nothing the server decides", () => {
    const draft = policyDraft({
      title: "  Keep imports pointing inward  ",
      description: "  A module that imports its caller has no boundary.  ",
      tags: "layering,  dependencies ,, ",
      strength: "required",
      body: "\n## Intent\nKeep the arrows going one way.\n\n",
    });

    expect(draft).toEqual({
      title: "Keep imports pointing inward",
      description: "A module that imports its caller has no boundary.",
      tags: ["layering", "dependencies"],
      strength: "required",
      body: "## Intent\nKeep the arrows going one way.",
    });
    // No id and no scope: the id is a slug of the title the server derives, and anything
    // written here is general. A form that could send either could file a policy under a
    // name its title does not say.
    expect(draft).not.toHaveProperty("id");
    expect(draft).not.toHaveProperty("scope");
  });

  it("round-trips a stored policy unchanged", () => {
    expect(policyDraft(policyFormValues(STORED))).toEqual({
      title: STORED.title,
      description: STORED.description,
      tags: STORED.tags,
      strength: STORED.strength,
      body: STORED.body,
    });
  });
});
