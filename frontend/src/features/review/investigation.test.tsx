import { describe, expect, it } from "vitest";

import { investigationFixture } from "../../test-fixtures";
import { investigationSummary, lookupLabel } from "./investigation";

/**
 * A stored review is an immutable record, so this surface has to read every shape the product
 * has ever written — including the ones it no longer produces.
 */
describe("an investigation as a reader sees it", () => {
  it("says a truncation was a truncation", () => {
    expect(
      investigationSummary(investigationFixture({ termination: "lookup_limit" })),
    ).toContain("no lookups left");
  });

  it("does not read an unrecorded termination as a natural end", () => {
    // The legacy shape: a review stored before terminations were kept. Calling that
    // "the pass stopped looking" would tell a reader the search was complete on the
    // strength of a field that did not exist yet.
    const summary = investigationSummary(investigationFixture({ termination: null }));

    expect(summary).toContain("not recorded");
    expect(summary).not.toContain("stopped looking");
  });

  it("tells a run that never asked anything apart from one that asked and found nothing", () => {
    expect(
      investigationSummary(
        investigationFixture({ lookups: [], termination: "provider_error" }),
      ),
    ).toContain("the model stopped answering");

    expect(
      investigationSummary(
        investigationFixture({ lookups: [], withheld: "index the repository again" }),
      ),
    ).toBe("nothing could be looked up");
  });

  it("renders a lookup written under the old tool vocabulary", () => {
    // `find_code` and `node_id` were replaced by `search_code` and `qualified_name`, and a
    // review recorded before that is still a review somebody opens.
    expect(
      lookupLabel({
        tool: "related_code",
        arguments: { node_id: "node_a1", kind: "implementations" },
        result: "1 implementation",
      }),
    ).toBe("asked what implementations node_a1");

    expect(
      lookupLabel({
        tool: "find_code",
        arguments: { name: "PersistenceGateway" },
        result: "1 match",
      }),
    ).toBe("searched for PersistenceGateway");
  });
});
