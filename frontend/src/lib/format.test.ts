import { describe, expect, it } from "vitest";

import {
  atlasFreshness,
  humanise,
  relativeTime,
  repositoryName,
  shortPath,
  statusOf,
  strengthOf,
  verdictOf,
  verdictRank,
} from "./format";

describe("product vocabulary", () => {
  it("gives every verdict a word and a mark, so colour is never the only signal", () => {
    for (const verdict of ["material", "held", "cleared"]) {
      const descriptor = verdictOf(verdict);
      expect(descriptor.label).toBeTruthy();
      expect(descriptor.glyph).toBeTruthy();
      expect(descriptor.description).toBeTruthy();
    }
    expect(verdictOf("material").tone).toBe("material");
    expect(verdictOf("cleared").tone).toBe("cleared");
  });

  it("orders what needs a human before what does not", () => {
    const findings = ["cleared", "held", "material"].sort(
      (left, right) => verdictRank(left) - verdictRank(right),
    );
    expect(findings).toEqual(["material", "held", "cleared"]);
  });

  it("falls back to a readable label for a value it has never seen", () => {
    expect(verdictOf("something_new").label).toBe("Something new");
    expect(statusOf("awaiting_answers").label).toBe("Awaiting answers");
    expect(strengthOf("required").tone).toBe("marked");
  });

  it("keeps the verdict hues off anything that is not a verdict", () => {
    // Red, amber and green are a severity scale here: act on it, wait on it, settled. How
    // binding a policy is says none of those things — a required policy is the one to read
    // first, not a problem — and a library of them rendered in the workbench's red read as
    // a list of alarms.
    expect(strengthOf("required").tone).toBe("marked");
    expect(strengthOf("preferred").tone).toBe("neutral");
    expect(strengthOf("guidance").tone).toBe("neutral");
    // The step between them survives without colour, which is what the glyph is for.
    expect(
      new Set(["required", "preferred", "guidance"].map((value) => strengthOf(value).glyph)).size,
    ).toBe(3);
  });

  it("humanises wire values without mangling them", () => {
    expect(humanise("dependency_direction")).toBe("Dependency direction");
    expect(humanise("")).toBe("");
  });
});

describe("paths and identifiers", () => {
  it("names a repository by its folder", () => {
    expect(repositoryName("/work/payments-platform")).toBe("payments-platform");
    expect(repositoryName("payments")).toBe("payments");
  });

  it("elides the middle of a long path and leaves a short one alone", () => {
    expect(shortPath("src/domain/orders/gateway.py")).toBe("src/…/orders/gateway.py");
    expect(shortPath("domain/orders.py")).toBe("domain/orders.py");
  });
});

describe("time", () => {
  const now = Date.parse("2026-01-01T12:00:00Z");

  it("reads elapsed time the way a reviewer asks about it", () => {
    expect(relativeTime("2026-01-01T11:56:00Z", now)).toMatch(/4 minutes ago/);
    expect(relativeTime("2025-12-31T12:00:00Z", now)).toMatch(/yesterday|1 day ago/);
    expect(relativeTime(null, now)).toBe("unknown");
    expect(relativeTime("not a date", now)).toBe("unknown");
  });

  it("states atlas freshness rather than making the reader subtract dates", () => {
    expect(atlasFreshness("2026-01-01T11:30:00Z", now).label).toBe("Fresh");
    expect(atlasFreshness("2025-12-30T12:00:00Z", now).label).toBe("Ageing");
    expect(atlasFreshness("2025-01-01T12:00:00Z", now).label).toBe("Stale");
    expect(atlasFreshness(null, now).label).toBe("Never indexed");
  });
});
