import { fireEvent, render, screen } from "@testing-library/react";
import { vi } from "vitest";

import { Badge } from "@/components/ui/badge";

import { ApiError, UNREACHABLE_CODE, UNREACHABLE_MESSAGE } from "./api";
import { EmptyState, ErrorPanel, Loading } from "./components";

describe("workspace primitives", () => {
  it("renders a semantic status badge", () => {
    // The chip is a vendored component now, so the meaning is carried by the variant it was
    // asked for rather than by a modifier class. Still the same claim: a chip that reports a
    // verdict is drawn in that verdict's family and not in the neutral one.
    render(<Badge variant="cleared">succeeded</Badge>);
    const chip = screen.getByText("succeeded");
    expect(chip).toHaveAttribute("data-variant", "cleared");
    expect(chip).toHaveClass("text-cleared");
  });

  it("renders an actionable empty state", () => {
    // The icon-in-a-circle went with the restyle; what has to survive is the pair that
    // makes an empty state useful — the sentence saying what would fill this, and the
    // control that starts filling it.
    render(
      <EmptyState
        title="No reviews"
        description="Start with a focused architecture case."
        action={<button type="button">Start a review</button>}
      />,
    );
    expect(screen.getByRole("heading", { name: "No reviews" })).toBeVisible();
    expect(screen.getByText("Start with a focused architecture case.")).toBeVisible();
    expect(screen.getByRole("button", { name: "Start a review" })).toBeEnabled();
  });

  it("waits in the shape of the rows it is waiting for", () => {
    // A skeleton at the final density, so nothing moves when the data lands. The label is
    // announced rather than drawn — every list on every page used to say it at once.
    render(<Loading label="Reading reviews…" rows={4} />);

    expect(screen.getByRole("status")).toHaveTextContent("Reading reviews…");
    // Rows are drawn from the Skeleton primitive now, so they are counted by the slot they
    // fill rather than by a class name — four rows, each still one row of the list to come.
    expect(document.querySelectorAll('[data-slot="skeleton-row"]')).toHaveLength(4);
  });
});

/**
 * A failure the reader can do something about is a different thing from a failure they can
 * only read, and the difference is one prop. What has to hold: the server's own words survive
 * whatever else is drawn beside them, the retry is absent unless a caller offered one, and it
 * cannot be pressed twice while the first attempt is still out.
 */
describe("ErrorPanel", () => {
  it("keeps the server's own words and offers nothing to press", () => {
    render(<ErrorPanel error={new ApiError("case.title must not be empty", 422)} />);

    expect(screen.getByRole("alert")).toHaveTextContent("case.title must not be empty");
    expect(screen.queryByRole("button")).toBeNull();
  });

  it("renders a retry and calls back when it is pressed", () => {
    const onRetry = vi.fn();
    render(<ErrorPanel error={new ApiError("The atlas could not be read.", 500)} onRetry={onRetry} />);

    const retry = screen.getByRole("button", { name: "Try again" });
    fireEvent.click(retry);

    expect(onRetry).toHaveBeenCalledTimes(1);
    expect(retry).toBeEnabled();
  });

  it("names the repeat in the caller's own words", () => {
    render(<ErrorPanel error={new Error("nope")} onRetry={() => {}} retryLabel="Ask again" />);

    expect(screen.getByRole("button", { name: "Ask again" })).toBeVisible();
  });

  it("says it is busy and refuses a second press while the first is out", () => {
    const onRetry = vi.fn();
    render(
      <ErrorPanel error={new Error("nope")} onRetry={onRetry} retrying retryLabel="Ask again" />,
    );

    const retry = screen.getByRole("button", { name: "Trying…" });
    expect(retry).toBeDisabled();
    fireEvent.click(retry);
    expect(onRetry).not.toHaveBeenCalled();
  });

  it("names the cure for a workspace that is not there, however it failed", () => {
    // Both shapes of the same situation: the connection that was refused outright, and the
    // reply that came from whatever is still serving the page instead of from the API.
    for (const error of [
      new TypeError("Failed to fetch"),
      new ApiError(UNREACHABLE_MESSAGE, 0, UNREACHABLE_CODE),
    ]) {
      const { unmount } = render(<ErrorPanel error={error} />);
      const alert = screen.getByRole("alert");

      expect(alert).toHaveTextContent(UNREACHABLE_MESSAGE);
      expect(alert).toHaveTextContent("archcompass web");
      // Never the parser's sentence, and never `fetch`'s either.
      expect(alert).not.toHaveTextContent("Failed to fetch");
      unmount();
    }
  });
});
