import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { api, type AtlasQueryResult, type Review } from "../../api";
import { reviewFixture } from "../../test-fixtures";
import { AtlasSurface, reviewAnchors, reviewAtlasEdges, reviewAtlasNodes } from "./atlas-surface";

/**
 * The atlas the fixture's review was judged against, as the route would answer it.
 *
 * Three judged elements, the class each of them reaches, and the packages that contain them —
 * which is the shape a review context comes back in: the subjects asked for, plus the
 * neighbourhood that makes them mean something.
 */
function atlasResult(): AtlasQueryResult {
  const node = (id: string, type: string, qualified: string) => ({
    node_id: id,
    qualified_name: qualified,
    node_type: type as never,
    path: `${qualified.replaceAll(".", "/")}.py`,
    location: { path: `${qualified.replaceAll(".", "/")}.py`, start_line: 1, end_line: 20 },
    is_public: true,
  });
  const edge = (from: string, to: string, type: string) => ({
    edge_id: `${from}-${type}-${to}`,
    source_id: from,
    target_id: to,
    edge_type: type as never,
    confidence: 1,
  });

  return {
    query: { kind: "review_context", node_ids: [], limit: 25 } as never,
    node_ids: [],
    node_summaries: [
      node("node-candidate-1", "class", "domain.orders.Orders"),
      node("node-candidate-2", "class", "domain.billing.Billing"),
      node("node-candidate-3", "class", "domain.invoice.Invoice"),
      node("adapter", "class", "adapters.db.Store"),
      node("pkg-domain", "package", "domain"),
      // The name the fixture's own participants carry, for the review that recorded no ids.
      node("by-name", "class", "domain.orders"),
    ],
    metric_values: [
      {
        node_id: "node-candidate-1",
        metric: "reverse_dependency_reach",
        value: 12,
        nature: "structural_proxy" as never,
        definition: "How much of the repository reaches this element.",
        limitations: "Static imports only.",
      },
    ],
    relationships: [
      edge("pkg-domain", "node-candidate-1", "contains"),
      edge("pkg-domain", "node-candidate-2", "contains"),
      edge("pkg-domain", "node-candidate-3", "contains"),
      edge("node-candidate-1", "adapter", "imports"),
      edge("node-candidate-2", "adapter", "imports"),
      edge("by-name", "adapter", "imports"),
    ],
    signals: [
      {
        node_id: "node-candidate-1",
        code: "wide-reach",
        message: "Reached from twelve modules.",
        nature: "structural_proxy" as never,
      },
    ],
  } as AtlasQueryResult;
}

function wrap(children: ReactNode) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}

afterEach(() => vi.restoreAllMocks());

describe("a review, turned into a map", () => {
  /**
   * The subject of every finding before the context of any of them. The route takes forty ids,
   * and a sweep large enough to reach that limit should still have all of its verdicts drawn.
   */
  it("asks for the elements its findings were about", () => {
    expect(reviewAnchors(reviewFixture())).toEqual({
      nodeIds: ["node-candidate-1", "node-candidate-2", "node-candidate-3"],
      qualifiedNames: [],
      dropped: 0,
    });
  });

  it("asks the same question however the findings are ordered", () => {
    const review = reviewFixture();
    const reversed = { ...review, findings: [...review.findings].reverse() };
    expect(reviewAnchors(reversed)).toEqual(reviewAnchors(review));
  });

  /**
   * A review judged before the atlas id travelled with a finding has only the name. Asking by
   * name is weaker — one name can answer to two nodes across a rebuild — and it is still the
   * difference between a map with a caveat and a sentence saying there is no map.
   */
  it("falls back to the qualified name where a finding recorded no element", () => {
    const review = reviewFixture();
    const older = {
      ...review,
      findings: review.findings.map((finding) => ({
        ...finding,
        candidate: {
          ...finding.candidate,
          participants: finding.candidate.participants.map(({ node_id: _, ...rest }) => rest),
        },
      })),
    };
    expect(reviewAnchors(older)).toEqual({
      nodeIds: [],
      qualifiedNames: ["domain.orders"],
      dropped: 0,
    });
  });

  /**
   * The verdict belongs to the element the candidate is about. Attach it anywhere else and the
   * map lights a dependency instead of the thing that was judged.
   */
  it("puts each verdict on the element it was written about, and nowhere else", () => {
    const review = reviewFixture();
    const nodes = reviewAtlasNodes([atlasResult()], review);
    const toned = nodes.filter((node) => node.tone);

    expect(toned.map((node) => [node.id, node.tone]).sort()).toEqual([
      ["node-candidate-1", "held"],
      ["node-candidate-2", "material"],
      ["node-candidate-3", "cleared"],
    ]);
    expect(toned.every((node) => node.candidateId)).toBe(true);
    // The neighbourhood is drawn, and it is drawn as the neighbourhood.
    expect(nodes.find((node) => node.id === "adapter")?.tone).toBeUndefined();
  });

  /** What the atlas measured travels with the element, or the panel beside it has nothing. */
  it("carries the measurements and the signals onto the element", () => {
    const nodes = reviewAtlasNodes([atlasResult()], reviewFixture());
    const subject = nodes.find((node) => node.id === "node-candidate-1")!;
    expect(subject.metrics[0]).toMatchObject({ value: 12, nature: "structural_proxy" });
    // A number whose scope a reader cannot see is a number they will over-read.
    expect(subject.metrics[0].limitations).toBeTruthy();
    expect(subject.signalCount).toBe(1);
  });

  /** An edge to something that was not drawn is a line to nowhere. */
  it("draws only the relationships whose both ends are on the map", () => {
    const nodes = reviewAtlasNodes([atlasResult()], reviewFixture());
    const edges = reviewAtlasEdges(
      [
        {
          ...atlasResult(),
          relationships: [
            ...(atlasResult().relationships ?? []),
            {
              edge_id: "dangling",
              source_id: "node-candidate-1",
              target_id: "not-on-the-map",
              edge_type: "imports" as never,
              confidence: 1,
            },
          ],
        },
      ],
      nodes,
    );
    const drawn = new Set(nodes.map((node) => node.id));
    expect(edges.every((edge) => drawn.has(edge.sourceId) && drawn.has(edge.targetId))).toBe(
      true,
    );
    expect(edges.some((edge) => edge.id === "dangling")).toBe(false);
  });
});

describe("the atlas surface", () => {
  it("draws the review's elements, and opens the finding behind a judged one", async () => {
    vi.spyOn(api, "reviewContext").mockResolvedValue(atlasResult());
    const onOpen = vi.fn();
    render(wrap(<AtlasSurface review={reviewFixture()} onOpen={onOpen} />));

    const map = await screen.findByRole("group", { name: /structure/i });
    const card = await within(map).findByRole("button", {
      name: "domain.orders.Orders, class, Held",
    });
    fireEvent.click(card);

    // The panel names it too, so the whole name is now in three places: the card's hover, its
    // accessible name, and here.
    expect(await screen.findAllByText("domain.orders.Orders")).toHaveLength(2);
    fireEvent.click(screen.getByRole("button", { name: "Open the finding" }));
    expect(onOpen).toHaveBeenCalledWith("candidate-1");
  });

  /**
   * The map is one request, not one per finding. The neighbourhoods of a review's candidates
   * overlap almost entirely, so asking per finding fetched the same packages and the same
   * edges once each, with a loading state apiece.
   */
  it("reads the whole neighbourhood in one request", async () => {
    const reviewContext = vi.spyOn(api, "reviewContext").mockResolvedValue(atlasResult());
    render(wrap(<AtlasSurface review={reviewFixture()} />));

    await screen.findByRole("group", { name: /structure/i });
    expect(reviewContext).toHaveBeenCalledTimes(1);
    // The neighbour bound is per anchor and therefore multiplies, so it is derived from a
    // budget on the whole map rather than fixed. Three anchors get a generous share.
    expect(reviewContext).toHaveBeenCalledWith(
      "/work/payments-platform",
      ["node-candidate-1", "node-candidate-2", "node-candidate-3"],
      [],
      25,
    );
  });

  /**
   * The bound the route takes is per anchor, so sixteen anchors at twenty-five neighbours is
   * four hundred cards. A real review came back with 235 and fit-to-view answered it by
   * zooming to fifteen percent.
   */
  it("shrinks each element's share of the map as a review names more of them", async () => {
    const reviewContext = vi.spyOn(api, "reviewContext").mockResolvedValue(atlasResult());
    const review = reviewFixture();
    const many = {
      ...review,
      findings: Array.from({ length: 20 }, (_, index) => ({
        ...review.findings[index % review.findings.length],
        candidate: {
          ...review.findings[index % review.findings.length].candidate,
          id: `candidate-${index}`,
          participants: [
            { qualified_name: `mod${index}.Thing`, role: "source", node_id: `node-${index}` },
          ],
        },
      })),
    };

    render(wrap(<AtlasSurface review={many} />));
    await waitFor(() => expect(reviewContext).toHaveBeenCalled());

    const share = reviewContext.mock.calls[0][3];
    expect(share).toBeLessThan(25);
    expect(share).toBeGreaterThanOrEqual(4);
  });

  /** A count that does not say what it is a count *of* reads as the whole repository. */
  /** The Atlas was the one surface in the workbench running an infinite animation inside the work. */
  it("opens holding still", async () => {
    vi.spyOn(api, "reviewContext").mockResolvedValue(atlasResult());
    render(wrap(<AtlasSurface review={reviewFixture()} />));
    expect(await screen.findByRole("group", { name: /structure/i })).toHaveAttribute(
      "data-pulse",
      "none",
    );
  });

  it("says how much of what it was given is on screen", async () => {
    vi.spyOn(api, "reviewContext").mockResolvedValue(atlasResult());
    render(wrap(<AtlasSurface review={reviewFixture()} />));
    expect(await screen.findByText(/of 6 elements/)).toBeInTheDocument();
  });

  /**
   * An atlas answers plenty of honest questions with nothing, and the map's response to
   * nothing is to stay exactly as it was — so pressing "Dependants" on a leaf looked
   * identical to pressing a button that did not work.
   */
  it("says so when an exploration comes back empty", async () => {
    vi.spyOn(api, "reviewContext").mockResolvedValue(atlasResult());
    vi.spyOn(api, "exploreRepository").mockResolvedValue({
      ...atlasResult(),
      node_summaries: [],
      relationships: [],
    });
    render(wrap(<AtlasSurface review={reviewFixture()} />));

    const map = await screen.findByRole("group", { name: /structure/i });
    fireEvent.click(within(map).getAllByRole("button")[0]);
    fireEvent.click(await screen.findByRole("button", { name: "Dependants" }));

    expect(
      await screen.findByText("Nothing in this atlas depends on this element."),
    ).toBeInTheDocument();
  });

  it("says what an exploration added when it found something", async () => {
    vi.spyOn(api, "reviewContext").mockResolvedValue(atlasResult());
    vi.spyOn(api, "exploreRepository").mockResolvedValue(atlasResult());
    render(wrap(<AtlasSurface review={reviewFixture()} />));

    const map = await screen.findByRole("group", { name: /structure/i });
    fireEvent.click(within(map).getAllByRole("button")[0]);
    fireEvent.click(await screen.findByRole("button", { name: "Callers" }));

    // Every element it returned was already drawn, so the note says that rather than
    // claiming six additions over a map whose count did not move.
    expect(await screen.findByText("6 elements, all already on the map.")).toBeInTheDocument();
  });

  /** What comes back from an explicit request is drawn, whatever lens is on. */
  it("counts what an exploration added, apart from what it found", async () => {
    vi.spyOn(api, "reviewContext").mockResolvedValue(atlasResult());
    vi.spyOn(api, "exploreRepository").mockResolvedValue({
      ...atlasResult(),
      node_summaries: [
        {
          node_id: "brand-new",
          qualified_name: "adapters.http.Client",
          node_type: "class" as never,
          path: "adapters/http.py",
          is_public: true,
        },
      ],
    } as never);
    render(wrap(<AtlasSurface review={reviewFixture()} />));

    const map = await screen.findByRole("group", { name: /structure/i });
    fireEvent.click(within(map).getAllByRole("button")[0]);
    fireEvent.click(await screen.findByRole("button", { name: "Children" }));

    expect(await screen.findByText("1 element, added.")).toBeInTheDocument();
    // And it is on the map, not merely reported: a lens that hid what the reader just asked
    // for would be answering the request by refusing it.
    expect(await screen.findByText(/of 7 elements/)).toBeInTheDocument();
  });

  /**
   * A review that judged nothing has nothing to place, and the atlas it read is still a real
   * record — so the surface says which of the two it is rather than drawing an empty box.
   */
  it("says why it is empty rather than drawing nothing", () => {
    render(wrap(<AtlasSurface review={reviewFixture({ findings: [] })} />));
    expect(screen.getByText(/composed no findings/)).toBeInTheDocument();
  });

  /**
   * A review judged before the atlas id was carried onto a finding cannot be placed at all.
   * That is a different failure from an empty review and it says so, rather than asking the
   * route for an empty set and drawing the blank that comes back.
   */
  it("draws a review that recorded names, and says the cards were matched by name", async () => {
    const reviewContext = vi.spyOn(api, "reviewContext").mockResolvedValue(atlasResult());
    const review = reviewFixture();
    const older: Review = {
      ...review,
      findings: review.findings.map((finding) => ({
        ...finding,
        candidate: {
          ...finding.candidate,
          participants: finding.candidate.participants.map(({ node_id: _, ...rest }) => rest),
        },
      })),
    };

    render(wrap(<AtlasSurface review={older} />));

    await screen.findByRole("group", { name: /structure/i });
    expect(reviewContext).toHaveBeenCalledWith(
      "/work/payments-platform",
      [],
      ["domain.orders"],
      25,
    );
    expect(screen.getByText(/matched by name/)).toBeInTheDocument();
  });

  it("says when its findings named nothing at all to place", () => {
    const reviewContext = vi.spyOn(api, "reviewContext");
    const review = reviewFixture();
    const nameless: Review = {
      ...review,
      findings: review.findings.map((finding) => ({
        ...finding,
        candidate: { ...finding.candidate, participants: [] },
      })),
    };

    render(wrap(<AtlasSurface review={nameless} />));
    expect(screen.getByText(/named an element/)).toBeInTheDocument();
    expect(reviewContext).not.toHaveBeenCalled();
  });

  it("keeps the lens out of the fold that hides the filters on a narrow screen", async () => {
    render(wrap(<AtlasSurface review={reviewFixture()} />));
    // A single-choice `ToggleGroup` is a radio group, which is what one-of-many means.
    const lens = await screen.findByRole("radiogroup", { name: /graph lens/i });

    // A phone has room for the map or for seven rows of controls, not both. Everything that
    // narrows what is already drawn folds away; the lens, which decides what the map is *of*,
    // never does.
    expect(lens.closest("details")).toBeNull();
    expect(screen.getByRole("button", { name: "Hide tests" }).closest("details")).not.toBeNull();
    expect(screen.getByRole("search").closest("details")).not.toBeNull();
    expect(screen.getByText(/search and filters/i).closest("summary")).not.toBeNull();
  });

  /**
   * The canvas has the node count and nothing else, so it printed the caller's sentence
   * whatever had emptied the map — telling a reader who had just pressed a filter that the
   * review's elements were gone from the atlas. A false statement of cause is worse than no
   * statement: it is the reader's own control, and they stop looking for it.
   */
  it("names the control that emptied the map, not the caller's sentence", async () => {
    const result = atlasResult();
    vi.spyOn(api, "reviewContext").mockResolvedValue({
      ...result,
      node_summaries: (result.node_summaries ?? []).map((node) => ({
        ...node,
        is_public: false,
      })),
    } as AtlasQueryResult);
    render(wrap(<AtlasSurface review={reviewFixture()} />));
    await screen.findByRole("group", { name: /structure/i });

    fireEvent.click(screen.getByRole("button", { name: "Public only" }));

    expect(await screen.findByText(/Public only leaves nothing to draw/)).toBeInTheDocument();
    expect(screen.queryByText(/no longer in the indexed atlas/)).not.toBeInTheDocument();

    // And the way back is the thing that did it, offered where the reader is looking.
    fireEvent.click(screen.getByRole("button", { name: "Clear the filters" }));
    expect(await screen.findByRole("group", { name: /structure/i })).toBeInTheDocument();
  });

  /**
   * `find` answers "is there one", which is not the question the box asks. A term with five
   * matches used to select one arbitrary card, mark none of the others and say nothing about
   * how many there were.
   */
  it("finds every card a term matches, and walks them", async () => {
    vi.spyOn(api, "reviewContext").mockResolvedValue(atlasResult());
    const explore = vi.spyOn(api, "exploreRepository");
    render(wrap(<AtlasSurface review={reviewFixture()} />));
    await screen.findByRole("group", { name: /structure/i });

    fireEvent.change(screen.getByRole("searchbox"), { target: { value: "domain" } });
    fireEvent.click(screen.getByRole("button", { name: "Find" }));

    expect(await screen.findByText("1 of 5 match")).toBeInTheDocument();
    // A term the map can answer never becomes a query: a query brings back cards nobody
    // asked to add.
    expect(explore).not.toHaveBeenCalled();

    fireEvent.click(screen.getByRole("button", { name: "Next" }));
    expect(await screen.findByText("2 of 5 match")).toBeInTheDocument();

    fireEvent.keyDown(document, { key: "n" });
    expect(await screen.findByText("3 of 5 match")).toBeInTheDocument();
    fireEvent.keyDown(document, { key: "n", shiftKey: true });
    expect(await screen.findByText("2 of 5 match")).toBeInTheDocument();
  });

  /**
   * The charter: a colour never carries meaning alone, and every verdict has a glyph, a word
   * and a hue. The card had the first and the third, and its accessible name said "judged"
   * for a material finding and for a cleared one.
   */
  it("says the verdict in words on the card and in its accessible name", async () => {
    vi.spyOn(api, "reviewContext").mockResolvedValue(atlasResult());
    render(wrap(<AtlasSurface review={reviewFixture()} />));

    const map = await screen.findByRole("group", { name: /structure/i });
    const material = await within(map).findByRole("button", {
      name: "domain.billing.Billing, class, Material",
    });
    expect(within(material).getByText("Material")).toBeInTheDocument();

    const cleared = within(map).getByRole("button", {
      name: "domain.invoice.Invoice, class, Cleared",
    });
    expect(within(cleared).getByText("Cleared")).toBeInTheDocument();
  });

  /**
   * `orders` is not an identity when three packages have one — the experience doc's own words
   * about this exact case. The leaf was cut to seventeen characters, the accessible name used
   * the same cut string, and nothing on the card carried the rest of it.
   */
  it("keeps the whole name reachable when the card can only show part of it", async () => {
    const result = atlasResult();
    vi.spyOn(api, "reviewContext").mockResolvedValue({
      ...result,
      node_summaries: [
        ...(result.node_summaries ?? []),
        {
          node_id: "long",
          qualified_name: "domain.billing.PaymentGatewayAdapter",
          node_type: "class" as never,
          path: "domain/billing/gateway.py",
          is_public: true,
        },
      ],
      relationships: [
        ...(result.relationships ?? []),
        {
          edge_id: "billing-imports-long",
          source_id: "node-candidate-2",
          target_id: "long",
          edge_type: "imports" as never,
          confidence: 1,
        },
      ],
    } as AtlasQueryResult);
    render(wrap(<AtlasSurface review={reviewFixture()} />));

    const map = await screen.findByRole("group", { name: /structure/i });
    const card = await within(map).findByRole("button", {
      name: "domain.billing.PaymentGatewayAdapter, class",
    });
    expect(within(card).getByText("PaymentGatewayAdapt…")).toBeInTheDocument();
    // The segment that tells two cards cut to the same characters apart, and the whole name
    // on the hover.
    expect(within(card).getByText("billing")).toBeInTheDocument();
    expect(
      within(card).getByText("domain.billing.PaymentGatewayAdapter").tagName,
    ).toBe("title");
  });

  /**
   * The map only grew: three presses of an exploration turned a ninety-card neighbourhood
   * into a mesh held for the rest of the session, and the only way back was a reload.
   */
  it("lists what the reader added to the map, and takes it back off", async () => {
    vi.spyOn(api, "reviewContext").mockResolvedValue(atlasResult());
    vi.spyOn(api, "exploreRepository").mockResolvedValue({
      ...atlasResult(),
      node_summaries: [
        {
          node_id: "brand-new",
          qualified_name: "adapters.http.Client",
          node_type: "class" as never,
          path: "adapters/http.py",
          is_public: true,
        },
      ],
    } as never);
    render(wrap(<AtlasSurface review={reviewFixture()} />));

    const map = await screen.findByRole("group", { name: /structure/i });
    fireEvent.click(within(map).getAllByRole("button")[0]);
    fireEvent.click(await screen.findByRole("button", { name: "Children" }));

    expect(await screen.findByText(/of 7 elements/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Children of/ })).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Reset the map" }));
    expect(await screen.findByText(/of 6 elements/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Children of/ })).not.toBeInTheDocument();
  });

  /**
   * What the reader explicitly asked the atlas for is protected from every lens and filter —
   * `visible-graph.ts` calls that absolute. It was the *last* request only, so asking a second
   * question quietly took the answer to the first one back off the map.
   */
  it("keeps every exploration's answer drawn, not only the last one", async () => {
    vi.spyOn(api, "reviewContext").mockResolvedValue(atlasResult());
    const explore = vi
      .spyOn(api, "exploreRepository")
      .mockResolvedValueOnce({
        ...atlasResult(),
        node_summaries: [
          {
            node_id: "brand-new",
            qualified_name: "adapters.http.Client",
            node_type: "class" as never,
            path: "adapters/http.py",
            is_public: true,
          },
        ],
      } as never)
      .mockResolvedValue(atlasResult());
    render(wrap(<AtlasSurface review={reviewFixture()} />));

    const map = await screen.findByRole("group", { name: /structure/i });
    fireEvent.click(within(map).getAllByRole("button")[0]);
    fireEvent.click(await screen.findByRole("button", { name: "Children" }));
    expect(await screen.findByText(/of 7 elements/)).toBeInTheDocument();

    fireEvent.click(await screen.findByRole("button", { name: "Callers" }));
    await waitFor(() => expect(explore).toHaveBeenCalledTimes(2));

    // Seven drawn, not six: the element the first exploration brought back is judged by
    // nothing and reaches nothing, so only the protection keeps it on a judged map.
    expect(await screen.findByText(/7 of 7 elements/)).toBeInTheDocument();
  });

  it("offers a way to retry the read that failed", async () => {
    vi.spyOn(api, "reviewContext").mockRejectedValue(new Error("the atlas is not indexed"));
    render(wrap(<AtlasSurface review={reviewFixture()} />));

    await waitFor(() =>
      expect(screen.getByText(/the atlas is not indexed/)).toBeInTheDocument(),
    );
    expect(screen.getByRole("button", { name: /try again/i })).toBeInTheDocument();
  });
});
