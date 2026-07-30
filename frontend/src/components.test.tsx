import { fireEvent, render, screen } from "@testing-library/react";
import { vi } from "vitest";

import { Badge } from "@/components/ui/badge";

import { EmptyState, Loading, useDialogFocus } from "./components";

function TestDialog({ onClose }: { onClose: () => void }) {
  const ref = useDialogFocus(onClose);
  return (
    <aside ref={ref} role="dialog">
      <button type="button">Close dialog</button>
      <a href="#evidence">Evidence</a>
    </aside>
  );
}

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

  it("focuses dialogs and lets keyboard users close them", () => {
    const onClose = vi.fn();
    render(<TestDialog onClose={onClose} />);
    const dialog = screen.getByRole("dialog");

    expect(screen.getByRole("button", { name: "Close dialog" })).toHaveFocus();
    fireEvent.keyDown(dialog, { key: "Escape" });
    expect(onClose).toHaveBeenCalledOnce();
  });
});
