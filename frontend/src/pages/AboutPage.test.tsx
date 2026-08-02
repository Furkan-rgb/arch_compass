/**
 * The method, stated.
 *
 * Two things are defended, both inherited from the front door. The annotated verdict is
 * fabricated, so it must say so where it is drawn. And the page reads nothing from the
 * workspace, so it makes the same argument on every machine. What is proper to this page:
 * every stage wears exactly one of the two lane words, and every mark on the anatomy card
 * has a legend entry — a mark with no explanation is decoration, which this figure must
 * never be.
 */

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import { api } from "../api";
import { AboutPage } from "./AboutPage";

function open() {
  render(
    <QueryClientProvider
      client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}
    >
      <MemoryRouter>
        <AboutPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

const anatomy = () =>
  document.querySelector('[data-slot="verdict-anatomy"]') as HTMLElement;

afterEach(() => vi.restoreAllMocks());

describe("the page's own claims", () => {
  it("states the method from a standing start", () => {
    open();

    expect(
      screen.getByRole("heading", { level: 1, name: "How a verdict is made" }),
    ).toBeInTheDocument();
    for (const stage of [
      "The atlas",
      "The sweep",
      "The judgement",
      "Reading the set",
      "The record",
    ]) {
      expect(screen.getByRole("heading", { level: 3, name: new RegExp(stage) })).toBeInTheDocument();
    }
  });

  it("reads nothing from the workspace", () => {
    const listed = vi.spyOn(api, "reviews");
    const read = vi.spyOn(api, "review");

    open();

    expect(listed).not.toHaveBeenCalled();
    expect(read).not.toHaveBeenCalled();
  });

  it("does not describe the product by where it runs", () => {
    open();

    expect(document.body.textContent).not.toMatch(/local|127\.0\.0\.1|leaves your machine/i);
  });
});

describe("the two lanes", () => {
  it("marks every stage as computed or judged, and nothing as both", () => {
    open();

    const list = document.querySelector('[data-slot="stage-list"]') as HTMLElement;
    const stages = Array.from(list.querySelectorAll(":scope > li")) as HTMLElement[];
    expect(stages).toHaveLength(5);
    for (const stage of stages) {
      const marks = within(stage).queryAllByText(/^(computed|judged by the model)$/);
      expect(marks).toHaveLength(1);
    }
    // The split itself: judgement happens in exactly two of the five stages.
    expect(
      stages.filter((stage) => within(stage).queryByText("judged by the model")),
    ).toHaveLength(2);
  });
});

describe("the scrolled run", () => {
  it("is labelled a specimen, and is decoration to a screen reader", () => {
    open();

    const figure = document.querySelector('[data-slot="run-figure"]') as HTMLElement;
    // Five layers of ledger would read as five reviews; the stage prose beside the figure
    // already states everything it draws.
    expect(figure.getAttribute("aria-hidden")).toBe("true");
    expect(
      within(figure).getByText(/Specimen run/),
    ).toBeInTheDocument();
  });

  it("draws the run from the same records the front door replays", () => {
    open();

    const figure = within(document.querySelector('[data-slot="run-figure"]') as HTMLElement);
    // One name from the shared specimen set, present in every ledger layer.
    expect(
      figure.getAllByText("orders.adapters.RepositoryPort").length,
    ).toBeGreaterThan(0);
    // The judging layer exists even though jsdom has no IntersectionObserver to reach it.
    expect(figure.getByText("judging…")).toBeInTheDocument();
    // And the held layer stops at the question, in the advisor's own accent panel.
    expect(figure.getByText(/awaiting answers/)).toBeInTheDocument();
  });
});

describe("the anatomy figure", () => {
  it("is labelled as a specimen", () => {
    open();

    expect(
      screen.getByText(/Specimen verdict, annotated/),
    ).toBeInTheDocument();
  });

  it("explains every mark it draws", () => {
    open();

    const figure = within(anatomy());
    for (const letter of ["a", "b", "c", "d"]) {
      // Once on the card, once at the head of its legend entry — never an orphan.
      expect(figure.getAllByText(letter, { exact: true })).toHaveLength(2);
    }
    expect(figure.getByText("avoid-pass-through-parameters")).toBeInTheDocument();
    expect(
      figure.getByText(/nothing the model writes is ever used as an\s*identifier/i),
    ).toBeInTheDocument();
  });
});
