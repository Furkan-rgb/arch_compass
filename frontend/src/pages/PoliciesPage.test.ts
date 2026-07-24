import { describe, expect, it } from "vitest";

import type { Policy } from "../types";
import { filterPolicies } from "./PoliciesPage";

const policies: Policy[] = [
  {
    id: "POL-OWN-001",
    title: "Keep capability knowledge with its owner",
    scope: "general",
    strength: "preferred",
    tags: ["ownership", "providers"],
    source: { author: "Arch Compass", inspiration: [] },
    body: "Provider-specific capability discovery belongs behind the provider boundary.",
    source_path: "/policies/ownership.md",
    content_hash: "one",
  },
  {
    id: "POL-LOCAL-001",
    title: "Keep one behavior local",
    scope: "repository",
    strength: "guidance",
    tags: ["abstraction"],
    source: { author: "Team", inspiration: [] },
    body: "Do not introduce a conceptual interface without credible independent variation.",
    source_path: "/repo/.archcompass/policies/local.md",
    content_hash: "two",
  },
];

describe("policy catalog filtering", () => {
  it("matches authored body text and tags", () => {
    expect(filterPolicies(policies, "provider boundary", "all")).toEqual([
      policies[0],
    ]);
    expect(filterPolicies(policies, "abstraction", "all")).toEqual([policies[1]]);
  });

  it("combines search with scope", () => {
    expect(filterPolicies(policies, "local", "repository")).toEqual([policies[1]]);
    expect(filterPolicies(policies, "local", "general")).toEqual([]);
  });
});
