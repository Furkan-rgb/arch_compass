import { reviewAtlasEdges, reviewAtlasNodes } from "./review-atlas";
import type { AtlasQueryResult, ReviewedBoundary } from "./types";

function node(nodeId: string, qualifiedName: string, nodeType = "interface") {
  return {
    node_id: nodeId,
    qualified_name: qualifiedName,
    node_type: nodeType,
    path: "src/ports.py",
    location: null,
    is_public: true,
  };
}

function result(fields: Partial<AtlasQueryResult>): AtlasQueryResult {
  return {
    query: { kind: "inspect" },
    node_ids: [],
    summary: "",
    node_summaries: [],
    metric_values: [],
    relationships: [],
    test_ids: [],
    signals: [],
    excerpts: [],
    ...fields,
  };
}

function boundary(
  reference: string,
  material: boolean,
  abstractionId: string,
  implementationId: string,
): ReviewedBoundary {
  return {
    reference,
    material,
    rationale: `Why ${reference} came out this way.`,
    recommended_response: "",
    policy_bearings: [],
    candidate: {
      candidate_id: `cand_${reference}`,
      pattern: "sole_implementation",
      summary: "One abstraction, one implementation.",
      limitations: "A static count cannot see runtime registration.",
      participants: [
        node(abstractionId, "ports.Clock"),
        node(implementationId, "adapters.SystemClock", "class"),
      ],
      measurements: [],
    },
  } as unknown as ReviewedBoundary;
}

describe("reviewAtlasNodes", () => {
  const boundaries = [
    boundary("BR-001", true, "node_a", "node_a_impl"),
    boundary("BR-002", false, "node_b", "node_b_impl"),
  ];
  const results = [
    result({
      node_summaries: [
        node("node_a", "ports.Clock"),
        node("node_b", "ports.TaskStore"),
        node("node_a_impl", "adapters.SystemClock", "class"),
        node("node_other", "adapters.Report", "class"),
        node("node_pkg", "adapters", "package"),
      ],
    }),
  ];

  it("draws a cleared boundary as cleared, not as an ordinary node", () => {
    const byId = new Map(reviewAtlasNodes(results, boundaries).map((n) => [n.id, n]));

    // "Examined and found to be earning its place" and "never looked at" are different
    // facts, and an exhaustive sweep is worth nothing if the map erases the difference.
    expect(byId.get("node_a")?.state).toBe("hotspot");
    expect(byId.get("node_b")?.state).toBe("cleared");
    expect(byId.get("node_other")?.state).toBe("normal");
    expect(byId.get("node_pkg")?.state).toBe("contained");
  });

  it("carries the verdict and its reference onto the node", () => {
    const byId = new Map(reviewAtlasNodes(results, boundaries).map((n) => [n.id, n]));

    expect(byId.get("node_a")?.description).toContain("BR-001");
    expect(byId.get("node_a")?.description).toContain("Should change");
    expect(byId.get("node_b")?.description).toContain("Earning its place");
    expect(byId.get("node_a_impl")?.description).toContain("BR-001");
  });

  it("collapses a node that several inspections returned", () => {
    const twice = reviewAtlasNodes([...results, ...results], boundaries);

    expect(twice.filter((item) => item.id === "node_a")).toHaveLength(1);
  });
});

describe("reviewAtlasEdges", () => {
  it("keeps only edges whose ends are both on the map", () => {
    const results = [
      result({
        node_summaries: [node("node_a", "ports.Clock")],
        relationships: [
          {
            edge_id: "e1",
            source_id: "node_a",
            target_id: "node_a",
            edge_type: "defines",
            confidence: 1,
          },
          // An edge to a node no inspection returned would be drawn from nowhere.
          {
            edge_id: "e2",
            source_id: "node_a",
            target_id: "node_missing",
            edge_type: "imports",
            confidence: 1,
          },
        ],
      }),
    ];
    const nodes = reviewAtlasNodes(results, []);

    expect(reviewAtlasEdges(results, nodes).map((edge) => edge.id)).toEqual(["e1"]);
  });

  it("draws an edge once however many inspections returned it", () => {
    const relationship = {
      edge_id: "e1",
      source_id: "node_a",
      target_id: "node_b",
      edge_type: "imports",
      confidence: 1,
    };
    const results = [
      result({
        node_summaries: [node("node_a", "ports.Clock"), node("node_b", "ports.Store")],
        relationships: [relationship],
      }),
      result({ node_summaries: [], relationships: [relationship] }),
    ];
    const nodes = reviewAtlasNodes(results, []);

    expect(reviewAtlasEdges(results, nodes)).toHaveLength(1);
  });
});
