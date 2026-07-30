import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { useState } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { api } from "./api";
import {
  ReviewAtlas,
  reviewAtlasEdges,
  reviewAtlasNodes,
  reviewContextNodeIds,
} from "./review-atlas";
import type {
  AtlasMetricValue,
  AtlasQueryResult,
  AtlasSignal,
  ReviewedBoundary,
} from "./types";

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
    // Derived by the review, not by the page: the wording depends on which shape was
    // judged, so the map shows whatever the review computed rather than its own phrase.
    verdict_label: material ? "Not earning its place" : "Earning its place",
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
    expect(byId.get("node_a")?.description).toContain("Not earning its place");
    expect(byId.get("node_b")?.description).toContain("Earning its place");
    expect(byId.get("node_a_impl")?.description).toContain("BR-001");
  });

  it("collapses a node that several inspections returned", () => {
    const twice = reviewAtlasNodes([...results, ...results], boundaries);

    expect(twice.filter((item) => item.id === "node_a")).toHaveLength(1);
  });

  it("marks the nodes a verdict was written about, and only those", () => {
    // What the map offers a way back to the finding from. The implementation is drawn and
    // labelled, but the finding is filed under the boundary.
    const byId = new Map(reviewAtlasNodes(results, boundaries).map((n) => [n.id, n]));

    expect(byId.get("node_a")?.hasFinding).toBe(true);
    expect(byId.get("node_b")?.hasFinding).toBe(true);
    expect(byId.get("node_a_impl")?.hasFinding).toBe(false);
    expect(byId.get("node_other")?.hasFinding).toBe(false);
  });
});

/**
 * The measurements and signals the atlas returned, on the nodes they were taken of.
 *
 * These arrived with every result and were dropped: the map handed the detail panel an empty
 * list, so a boundary the atlas had measured showed "Evidence references: 0" beside it. The
 * scope and the limitations travel with the number, because a reach of 41 read without its
 * scope is a number a reader will take to mean more than it does.
 */
describe("reviewAtlasNodes, measurements and signals", () => {
  function metric(nodeId: string, name: string, value: number): AtlasMetricValue {
    return {
      node_id: nodeId,
      metric: name,
      value,
      nature: "structural_proxy",
      scope: "reverse_static_impact_neighbourhood",
      definition: `What ${name} counts.`,
      limitations: "Only statically resolved references.",
    };
  }

  function signal(nodeId: string, code: string, line = 4): AtlasSignal {
    return {
      code,
      message: `${code} on ${nodeId}.`,
      node_id: nodeId,
      location: { path: "src/ports.py", start_line: line, end_line: line },
      nature: "structural_proxy",
      definition: `What ${code} means.`,
      limitations: "A static count cannot see runtime registration.",
    };
  }

  const results = [
    result({
      node_summaries: [node("node_a", "ports.Clock"), node("node_b", "ports.Store")],
      metric_values: [
        metric("node_a", "reverse_dependency_reach", 41),
        metric("node_b", "reverse_dependency_reach", 2),
      ],
      signals: [signal("node_a", "sole-implementation")],
    }),
  ];

  it("puts each measurement on its own node, with its scope and its limits", () => {
    const byId = new Map(reviewAtlasNodes(results, []).map((n) => [n.id, n]));

    expect(byId.get("node_a")?.metrics).toEqual([
      {
        label: "Reverse dependency reach",
        value: 41,
        nature: "structural_proxy",
        scope: "reverse_static_impact_neighbourhood",
        definition: "What reverse_dependency_reach counts.",
        limitations: "Only statically resolved references.",
      },
    ]);
    // Not every node's metrics on every node: the value is about the one it was measured of.
    expect(byId.get("node_b")?.metrics.map((item) => item.value)).toEqual([2]);
  });

  it("puts the signals on the node and counts them for the canvas", () => {
    const byId = new Map(reviewAtlasNodes(results, []).map((n) => [n.id, n]));

    expect(byId.get("node_a")?.signals?.map((item) => item.code)).toEqual([
      "sole-implementation",
    ]);
    expect(byId.get("node_a")?.signalCount).toBe(1);
    expect(byId.get("node_b")?.signalCount).toBe(0);
  });

  it("counts a measurement once however many results carried it", () => {
    // The review context and everything the reader has explored since overlap heavily, and
    // the same node arrives in several of them carrying the same measurement each time.
    const byId = new Map(reviewAtlasNodes([...results, ...results], []).map((n) => [n.id, n]));

    expect(byId.get("node_a")?.metrics).toHaveLength(1);
    expect(byId.get("node_a")?.signalCount).toBe(1);
  });

  it("keeps two signals of one code raised at two places", () => {
    const twice = [
      result({
        node_summaries: [node("node_a", "ports.Clock")],
        signals: [signal("node_a", "wide-reach", 4), signal("node_a", "wide-reach", 90)],
      }),
    ];

    expect(reviewAtlasNodes(twice, [])[0].signalCount).toBe(2);
  });
});

/**
 * The nodes the map asks the atlas about: every boundary and the implementation behind it.
 *
 * The implementation was already labelled — "the one implementation behind BR-001" — and the
 * label never appeared, because nothing asked the atlas for that node. A boundary and the
 * single class behind it are the two halves of one finding.
 */
describe("reviewContextNodeIds", () => {
  it("asks for both participants of every boundary", () => {
    expect(
      reviewContextNodeIds([
        boundary("BR-001", true, "node_a", "node_a_impl"),
        boundary("BR-002", false, "node_b", "node_b_impl"),
      ]),
    ).toEqual(["node_a", "node_a_impl", "node_b", "node_b_impl"]);
  });

  it("asks once for a class that implements two of the boundaries examined", () => {
    // Sorted and deduplicated, so the same review asks the same question however its
    // findings happen to be ordered — which is what makes the answer cacheable.
    expect(
      reviewContextNodeIds([
        boundary("BR-002", true, "node_b", "shared_impl"),
        boundary("BR-001", true, "node_a", "shared_impl"),
      ]),
    ).toEqual(["node_a", "node_b", "shared_impl"]);
  });

  it("stops at the forty the route accepts, keeping every judged boundary", () => {
    // A sweep large enough to reach the limit should still have all of its verdicts on the
    // map: the implementations fill what room is left and the rest are one click away.
    const many = Array.from({ length: 30 }, (_, index) =>
      boundary(`BR-${index}`, true, `abstraction_${index}`, `implementation_${index}`),
    );

    const asked = reviewContextNodeIds(many);
    expect(asked).toHaveLength(40);
    expect(asked.filter((id) => id.startsWith("abstraction_"))).toHaveLength(30);
  });

  it("is empty for a review whose boundaries name no node", () => {
    expect(reviewContextNodeIds([])).toEqual([]);
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

/**
 * The map as the review page mounts it.
 *
 * What these hold in place is one request, one vocabulary and one default lens. Each of them
 * replaced something that read as a bug: an inspection per boundary with a loading state each,
 * a legend above the map disagreeing with the legend inside it, and a first view that drew the
 * neighbourhood's dependency edges nowhere because the structural lens draws containment only.
 */
describe("ReviewAtlas", () => {
  const boundaries = [
    boundary("BR-001", true, "node_a", "node_a_impl"),
    boundary("BR-002", false, "node_b", "node_b_impl"),
  ];
  const context = result({
    query: { kind: "review_context" },
    node_ids: ["node_a", "node_b"],
    node_summaries: [
      node("node_a", "ports.Clock"),
      node("node_b", "ports.TaskStore"),
      node("node_a_impl", "adapters.SystemClock", "class"),
      node("node_other", "adapters.Report", "class"),
      node("node_pkg", "adapters", "package"),
    ],
    relationships: [
      {
        edge_id: "e1",
        source_id: "node_a_impl",
        target_id: "node_a",
        edge_type: "implements",
        confidence: 1,
      },
    ],
  });

  function renderMap(
    options: {
      selectedNodeId?: string | null;
      onOpenFinding?: (nodeId: string) => void;
      boundaries?: ReviewedBoundary[];
      context?: AtlasQueryResult;
    } = {},
  ) {
    const fetched = vi
      .spyOn(api, "reviewContext")
      .mockResolvedValue(options.context ?? context);
    const explored = vi.spyOn(api, "repositoryExplore");
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const view = render(
      <QueryClientProvider client={client}>
        <ReviewAtlas
          repositoryRoot="/repos/scheduler"
          boundaries={options.boundaries ?? boundaries}
          selectedNodeId={options.selectedNodeId ?? null}
          onSelectNode={() => {}}
          onOpenFinding={options.onOpenFinding}
        />
      </QueryClientProvider>,
    );
    return { fetched, explored, client, view };
  }

  afterEach(() => vi.restoreAllMocks());

  /**
   * The map with its data in, which is also when its controls stop being disabled.
   *
   * The count under the canvas is the one place the whole graph is stated, so it is what these
   * wait on: a control clicked while the request is still out is a disabled control, and a test
   * that clicked it would pass by asserting nothing.
   */
  function drawn(nodeCount: number) {
    return screen.findByText(new RegExp(`of ${nodeCount} surfaced nodes`));
  }

  it("asks once for every boundary and the implementation behind it", async () => {
    const { fetched } = renderMap();
    await drawn(5);

    expect(fetched).toHaveBeenCalledTimes(1);
    // Both participants. The implementation was labelled "the one implementation behind
    // BR-001" long before anything asked the atlas for it, so the label never appeared.
    expect(fetched).toHaveBeenCalledWith("/repos/scheduler", [
      "node_a",
      "node_a_impl",
      "node_b",
      "node_b_impl",
    ]);
  });

  it("opens on the dependencies lens, which is what this graph is made of", async () => {
    renderMap();
    await drawn(5);

    expect(screen.getByRole("button", { name: "Dependencies" })).toHaveAttribute(
      "aria-pressed",
      "true",
    );
    expect(screen.getByRole("button", { name: "Structure" })).toHaveAttribute(
      "aria-pressed",
      "false",
    );
  });

  it("names the states in the review's words, in the map's own legend", async () => {
    renderMap();
    await drawn(5);
    const legend = within(screen.getByLabelText("Atlas legend"));

    expect(legend.getByText("Should change")).toBeTruthy();
    expect(legend.getByText("Left as it is")).toBeTruthy();
    // The atlas's own tokens are gone from the page. There were two legends saying different
    // words for the same colours, and neither of them named `cleared` at all.
    expect(screen.queryByText("Hotspot")).toBeNull();
    expect(screen.queryByText("Contained")).toBeNull();
  });

  it("keys only the states this graph contains", async () => {
    // A key naming a verdict no boundary came out with sends the reader looking for it.
    renderMap({
      boundaries: [boundary("BR-001", true, "node_a", "node_a_impl")],
      context: result({ node_summaries: [node("node_a", "ports.Clock")] }),
    });
    await drawn(1);
    const legend = within(screen.getByLabelText("Atlas legend"));

    expect(legend.getByText("Should change")).toBeTruthy();
    expect(legend.queryByText("Left as it is")).toBeNull();
  });

  it("offers the way back to the finding from a node a verdict was written about", async () => {
    const opened = vi.fn();
    renderMap({ selectedNodeId: "node_a", onOpenFinding: opened });

    fireEvent.click(await screen.findByRole("button", { name: "Go to finding" }));

    expect(opened).toHaveBeenCalledWith("node_a");
  });

  it("offers it from nothing else on the map", async () => {
    // Most of the map is the neighbourhood, which no finding is about.
    renderMap({ selectedNodeId: "node_other", onOpenFinding: vi.fn() });
    await drawn(5);

    // The panel is showing that node, and has no way back to a finding about it.
    expect(screen.getByRole("heading", { level: 3, name: "Report" })).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Go to finding" })).toBeNull();
  });

  it("keeps what the reader explored when the page is left and come back to", async () => {
    // The inspections were cached and the explorations were in component state, so leaving the
    // page kept the bill and lost the reading.
    const { explored, client, view } = renderMap();
    explored.mockResolvedValue(
      result({
        query: { operation: "cycles" },
        node_summaries: [node("node_cycle", "adapters.Loop", "class")],
      }),
    );
    await drawn(5);

    fireEvent.click(screen.getByRole("button", { name: "Risk" }));
    fireEvent.click(screen.getByRole("button", { name: "Surface cycles" }));
    await drawn(6);
    expect(explored).toHaveBeenCalledTimes(1);

    view.unmount();
    render(
      <QueryClientProvider client={client}>
        <ReviewAtlas
          repositoryRoot="/repos/scheduler"
          boundaries={boundaries}
          selectedNodeId="node_cycle"
          onSelectNode={() => {}}
        />
      </QueryClientProvider>,
    );

    // The same exploration, answered from the cache rather than asked for again.
    expect(await screen.findByRole("heading", { level: 3, name: "Loop" })).toBeTruthy();
    expect(explored).toHaveBeenCalledTimes(1);
  });

  it("traces a path between two nodes, and draws the one that came back", async () => {
    // `onSetPathStart` and `onTracePath` were declared by the map and passed by nobody, so the
    // panel offered a start, took it, and then had no way to ask for the path. What is drawn is
    // the route's own answer: the nodes and edges it says the path runs through.
    const explored = vi.spyOn(api, "repositoryExplore").mockResolvedValue(
      result({
        query: { operation: "shortest_path" },
        node_ids: ["node_a", "node_a_impl"],
        relationships: context.relationships,
      }),
    );
    vi.spyOn(api, "reviewContext").mockResolvedValue(context);
    /* Selection belongs to the page above this component, so tracing a path — which is two
       selections and a gesture between them — needs one here too. */
    const Page = () => {
      const [selected, setSelected] = useState<string | null>("node_a");
      return (
        <ReviewAtlas
          repositoryRoot="/repos/scheduler"
          boundaries={boundaries}
          selectedNodeId={selected}
          onSelectNode={setSelected}
        />
      );
    };
    render(
      <QueryClientProvider
        client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}
      >
        <Page />
      </QueryClientProvider>,
    );
    await drawn(5);

    fireEvent.click(screen.getByRole("button", { name: "Use as path start" }));
    fireEvent.click(screen.getByRole("button", { name: /← implements/ }));
    fireEvent.click(await screen.findByRole("button", { name: /Trace from Clock/ }));

    await waitFor(() =>
      expect(explored).toHaveBeenCalledWith({
        root_path: "/repos/scheduler",
        operation: "shortest_path",
        node_id: "node_a",
        target_id: "node_a_impl",
        limit: 60,
      }),
    );
    await waitFor(() =>
      expect(document.querySelectorAll(".atlas-edge--path")).toHaveLength(1),
    );
  });

  it("asks the same exploration once however many times it is requested", async () => {
    const { explored } = renderMap();
    explored.mockResolvedValue(
      result({
        query: { operation: "cycles" },
        node_summaries: [node("node_cycle", "adapters.Loop", "class")],
      }),
    );
    await drawn(5);

    fireEvent.click(screen.getByRole("button", { name: "Risk" }));
    fireEvent.click(screen.getByRole("button", { name: "Surface cycles" }));
    await drawn(6);
    fireEvent.click(screen.getByRole("button", { name: "Surface cycles" }));

    // Two identical explorations are one exploration, and it stays one entry on the map.
    await waitFor(() => expect(explored).toHaveBeenCalledTimes(1));
    expect(await drawn(6)).toBeTruthy();
  });
});
