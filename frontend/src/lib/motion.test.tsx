import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { useFocusTrap, useOverlay } from "./motion";

/**
 * The bug this file exists for was invisible in the component that had it.
 *
 * `useFocusTrap(open, onClose)` listed `onClose` as a dependency, and every call site builds
 * one with an inline arrow — so the effect tore down and re-ran on every parent render, and
 * each run called `focusable()[0].focus()`. The review page polls the run list every four
 * seconds, which made typing into the drawer's own search field lose its keystrokes on a
 * four-second cycle: a broken input, with nothing in the input's own code to explain it.
 */
function Trapped({ tick, onClose }: { tick: number; onClose?: () => void }) {
  // A fresh arrow on every render, which is what both real call sites pass.
  const ref = useFocusTrap(true, () => onClose?.());
  return (
    <div ref={ref}>
      <button type="button">Close</button>
      <input aria-label="Search" />
      <span data-testid="tick">{tick}</span>
    </div>
  );
}

describe("the overlay hooks", () => {
  it("puts focus in the overlay once, and leaves it where the reader put it", () => {
    const view = render(<Trapped tick={0} />);
    expect(document.activeElement).toBe(screen.getByRole("button", { name: "Close" }));

    const field = screen.getByRole("textbox", { name: "Search" });
    field.focus();

    // Four renders of the parent, the way a polling query produces them.
    for (let tick = 1; tick <= 4; tick += 1) view.rerender(<Trapped tick={tick} />);

    expect(screen.getByTestId("tick")).toHaveTextContent("4");
    expect(document.activeElement).toBe(field);
  });

  it("closes on Escape with whatever the latest render handed it", () => {
    const first = vi.fn();
    const second = vi.fn();
    const view = render(<Trapped tick={0} onClose={first} />);
    view.rerender(<Trapped tick={1} onClose={second} />);

    fireEvent.keyDown(document, { key: "Escape" });

    // The ref is the point: the effect never re-ran, and the callback is still current.
    expect(first).not.toHaveBeenCalled();
    expect(second).toHaveBeenCalledOnce();
  });

  it("stops the page behind an overlay from scrolling, and gives the value back", () => {
    document.body.style.overflow = "auto";

    function Locked({ open }: { open: boolean }) {
      const ref = useOverlay(open, () => {});
      return open ? <div ref={ref} /> : null;
    }

    const view = render(<Locked open={false} />);
    expect(document.body.style.overflow).toBe("auto");

    view.rerender(<Locked open />);
    expect(document.body.style.overflow).toBe("hidden");

    view.rerender(<Locked open={false} />);
    expect(document.body.style.overflow).toBe("auto");
  });
});
