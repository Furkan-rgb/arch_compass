import { load } from "js-yaml";

import { CASE_SKELETON, caseToYaml, checkYamlSyntax } from "./case-editor";
import type { ArchitectureCase } from "./types";

describe("checkYamlSyntax", () => {
  it("accepts a document the server can then judge", () => {
    expect(checkYamlSyntax("title: A boundary decision\nnon_goals: []\n")).toBeNull();
  });

  it("names what is wrong when the document is not YAML at all", () => {
    const problem = checkYamlSyntax("title: [unclosed\n");
    expect(problem).toContain("flow collection");
    expect(problem).toContain("title: [unclosed");
  });

  it("passes the skeleton, so an untouched editor fails at the server, not at syntax", () => {
    expect(checkYamlSyntax(CASE_SKELETON)).toBeNull();
  });
});

describe("caseToYaml", () => {
  const stored = {
    schema_version: 2,
    case_id: "case_abc",
    revision: 3,
    created_at: "2026-07-26T10:00:00Z",
    updated_at: "2026-07-26T11:00:00Z",
    title: "Storage boundary",
    problem_statement: "One implementation behind a port.",
    desired_outcome: "A verdict either way.",
    actors_and_workflows: [],
    non_goals: ["A second database."],
    confirmed_facts: [
      { id: "stmt_1", text: "SQLite is fixed.", kind: "fact", source: null },
    ],
    repository: { root_path: "/repos/scheduler", atlas_version_id: null },
    policy_applicability: { user: null, organisation: null, repository: null },
  } as unknown as ArchitectureCase;

  it("leaves out what ArchCompass generated and what is empty", () => {
    const yaml = caseToYaml(stored);

    expect(yaml).not.toContain("case_abc");
    expect(yaml).not.toContain("schema_version");
    expect(yaml).not.toContain("created_at");
    expect(yaml).not.toContain("stmt_1");
    expect(yaml).not.toContain("actors_and_workflows");
    expect(yaml).not.toContain("policy_applicability");
  });

  it("round-trips as the format the editor accepts", () => {
    const parsed = load(caseToYaml(stored)) as Record<string, unknown>;

    expect(parsed.title).toBe("Storage boundary");
    expect(parsed.non_goals).toEqual(["A second database."]);
    expect(parsed.confirmed_facts).toEqual([{ text: "SQLite is fixed.", kind: "fact" }]);
    expect(parsed.repository).toEqual({ root_path: "/repos/scheduler" });
    expect(checkYamlSyntax(caseToYaml(stored))).toBeNull();
  });
});
