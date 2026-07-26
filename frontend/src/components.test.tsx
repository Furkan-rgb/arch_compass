import { fireEvent, render, screen } from "@testing-library/react";
import { Compass } from "lucide-react";
import { vi } from "vitest";

import { Badge, EmptyState, useDialogFocus } from "./components";

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
    render(<Badge tone="success">succeeded</Badge>);
    expect(screen.getByText("succeeded")).toHaveClass("badge--success");
  });

  it("renders an actionable empty state", () => {
    render(
      <EmptyState
        icon={<Compass aria-hidden="true" />}
        title="No reviews"
        description="Start with a focused architecture case."
        action={<button type="button">Start a review</button>}
      />,
    );
    expect(screen.getByRole("heading", { name: "No reviews" })).toBeVisible();
    expect(screen.getByRole("button", { name: "Start a review" })).toBeEnabled();
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
