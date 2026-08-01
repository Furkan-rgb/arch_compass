import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { RepositoryAtlas, type AtlasEdgeView, type AtlasNodeView } from "./atlas";

/**
 * The motion the map gives a selected node's neighbourhood.
 *
 * What is asserted here is the contract the stylesheet animates against — one overlay path
 * per connected relationship, the direction it was stored in, and nothing drawn where a
 * mode has nothing to say. The animation itself is CSS and is not something jsdom can be
 * asked about; what would silently break it is the markup underneath, so that is what is
 * pinned.
 */

function node(id: string, label: string): AtlasNodeView {
  return {
    id,
    label,
    path: `src/${label}.py`,
    kind: "class",
    state: "normal",
    metrics: [],
  };
}

function edge(id: string, sourceId: string, targetId: string): AtlasEdgeView {
  return { id, sourceId, targetId, kind: "imports" };
}

const NODES = [node("a", "Caller"), node("b", "Middle"), node("c", "Callee"), node("d", "Aside")];

/* `b` is the middle of the chain: one relationship points at it and one points away, which
   is the case every direction decision in the stylesheet turns on. `c → d` reaches none of it. */
const EDGES = [edge("in", "a", "b"), edge("out", "b", "c"), edge("far", "c", "d")];

function draw(selectedNodeId: string | null = "b") {
  return render(
    <RepositoryAtlas
      nodes={NODES}
      edges={EDGES}
      selectedNodeId={selectedNodeId}
      onSelectNode={vi.fn()}
      initialLens="dependencies"
    />,
  );
}

function pulses(container: HTMLElement) {
  return [...container.querySelectorAll(".atlas-pulse")];
}

function chooseMotion(label: string) {
  fireEvent.change(screen.getByLabelText("Highlight motion for the selected node"), {
    target: { value: label },
  });
}

describe("the pulse along a selected node's relationships", () => {
  it("opens on the comet", () => {
    const { container } = draw();
    expect(screen.getByLabelText("Highlight motion for the selected node")).toHaveValue("comet");
    expect(container.querySelector("svg[data-pulse='comet']")).not.toBeNull();
  });

  it("draws one pulse along each relationship the selected node has, and no others", () => {
    const { container } = draw();
    expect(pulses(container)).toHaveLength(2);
  });

  it("marks the relationships drawn towards the selection, which ripple plays backwards", () => {
    const { container } = draw();
    const incoming = pulses(container).filter((path) =>
      path.classList.contains("atlas-pulse--incoming"),
    );
    expect(incoming).toHaveLength(1);
  });

  it("normalises every pulse to the same length, so a long edge is not slower", () => {
    const { container } = draw();
    for (const path of pulses(container)) {
      expect(path.getAttribute("pathLength")).toBe("100");
    }
  });

  it("orders the pulses so ripple can stagger them outward", () => {
    const { container } = draw();
    const ranks = pulses(container).map((path) =>
      path.getAttribute("style")?.match(/--atlas-pulse-rank:\s*(\d+)/)?.[1],
    );
    expect(ranks).toEqual(["0", "1"]);
  });

  it("draws no pulse where nothing is selected", () => {
    const { container } = draw(null);
    expect(pulses(container)).toHaveLength(0);
  });

  /* Breathe animates the highlight that is already there, and still is the highlight the
     map has always drawn. Neither has an overlay to render, and rendering one anyway would
     leave an invisible path over every edge waiting for a stylesheet change to reveal it. */
  it("draws no overlay for the modes that do not use one", () => {
    const { container } = draw();
    chooseMotion("breathe");
    expect(pulses(container)).toHaveLength(0);
    chooseMotion("none");
    expect(pulses(container)).toHaveLength(0);
    chooseMotion("ripple");
    expect(pulses(container)).toHaveLength(2);
  });

  it("rings only the selected node", () => {
    const { container } = draw();
    expect(container.querySelectorAll(".atlas-node__halo")).toHaveLength(1);
    expect(
      container.querySelector(".atlas-node--active .atlas-node__halo"),
    ).not.toBeNull();
  });
});
