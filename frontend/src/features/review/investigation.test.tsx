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

/**
 * The tools a judgement actually uses today. They arrived with the filesystem the judge
 * reads the reviewed revision through, and this surface knew none of their names — so the
 * majority of every trace rendered as a bare `read_file` with no file in it, on a fold whose
 * entire job is to say what was checked. Measured on one review: 33 of 49 lookups.
 */
describe("what a repository check says it did", () => {
  const lookup = (tool: string, args: Record<string, string>) =>
    ({ tool, arguments: args, result: "" }) as Parameters<typeof lookupLabel>[0];

  it("names the file that was read", () => {
    expect(lookupLabel(lookup("read_file", { file_path: "/ports.py" }))).toBe("read /ports.py");
    // The offset and limit are how much was read, not what was read, and saying them here
    // would push the filename out of a line that has to stay scannable.
    expect(
      lookupLabel(lookup("read_file", { file_path: "/adapters.py", limit: "100", offset: "0" })),
    ).toBe("read /adapters.py");
  });

  it("names what a search was for, and where it looked when that was narrowed", () => {
    expect(lookupLabel(lookup("grep", { pattern: "Protocol" }))).toContain("Protocol");
    // "searched for Protocol" and "searched tests for Protocol" are different checks, and a
    // reader weighing whether substitution was established needs to tell them apart.
    expect(lookupLabel(lookup("grep", { pattern: "Protocol", path: "/tests" }))).toBe(
      "searched /tests for Protocol",
    );
    expect(lookupLabel(lookup("glob", { pattern: "*.py" }))).toContain("*.py");
    expect(lookupLabel(lookup("ls", { path: "/" }))).toBe("listed /");
  });

  it("says a policy search was a policy search", () => {
    expect(lookupLabel(lookup("search_policies", { query: "substitution" }))).toContain(
      "policies about substitution",
    );
  });

  it("still renders the tools stored reviews were written with", () => {
    // A stored review is immutable, so the names the product used before must keep reading
    // as sentences rather than falling through to the raw call.
    expect(lookupLabel(lookup("describe_code", { qualified_name: "app.Gateway" }))).toBe(
      "inspected app.Gateway",
    );
    expect(lookupLabel(lookup("read_code", { node_id: "node_a1" }))).toContain("node_a1");
  });

  it("falls back to the tool's own name rather than disappearing", () => {
    expect(lookupLabel(lookup("some_tool_added_later", {}))).toBe("some_tool_added_later");
    // A known tool with the argument missing must not render a sentence with a hole in it.
    expect(lookupLabel(lookup("read_file", {}))).toBe("read_file");
  });
});
