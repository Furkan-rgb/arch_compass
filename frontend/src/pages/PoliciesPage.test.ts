import { describe, expect, it } from "vitest";

import { policyApplicabilityLabel } from "../policy-applicability";
import type { Policy } from "../types";
import { filterPolicies } from "./PoliciesPage";

const policies: Policy[] = [
  {
    id: "POL-OWN-001",
    title: "Keep capability knowledge with its owner",
    description:
      "Discovering what a provider can do is the provider's own business. Spread across "
      + "callers, every new provider becomes an edit in each of them.",
    scope: "general",
    applies_to: null,
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
    applies_to: "repo_arch_compass",
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

  it("matches the authored description, and policies without one still match", () => {
    expect(filterPolicies(policies, "the provider's own business", "all")).toEqual([
      policies[0],
    ]);
    // The second fixture carries no description at all — what external policy sources look
    // like — and is still reachable by everything else it does carry.
    expect(policies[1].description).toBeUndefined();
    expect(filterPolicies(policies, "credible independent variation", "all")).toEqual([
      policies[1],
    ]);
  });

  it("combines search with scope", () => {
    expect(filterPolicies(policies, "local", "repository")).toEqual([policies[1]]);
    expect(filterPolicies(policies, "local", "general")).toEqual([]);
  });

  it("searches and labels scoped policy identity", () => {
    expect(filterPolicies(policies, "repo_arch_compass", "all")).toEqual([
      policies[1],
    ]);
    expect(policyApplicabilityLabel("general", null)).toBe("All contexts");
    expect(
      policyApplicabilityLabel("repository", "repo_arch_compass"),
    ).toBe("repository · repo_arch_compass");
  });
});
