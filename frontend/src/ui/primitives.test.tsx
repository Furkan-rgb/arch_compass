import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { STORAGE_KEY as EDITOR_KEY } from "../lib/editor";
import { setReducedMotion } from "../test-setup";
import { Button, CopyButton } from "./button";
import { SourceExcerpt } from "./code";
import { Drawer } from "./drawer";
import { PathRef } from "./meta";
import { ErrorNotice, Spinner } from "./states";
import { Tabs } from "./tabs";
import { ToastProvider, useToast } from "./toast";

const written: string[] = [];

beforeEach(() => {
  written.length = 0;
  window.localStorage.clear();
  setReducedMotion(false);
  Object.defineProperty(navigator, "clipboard", {
    configurable: true,
    value: {
      writeText: vi.fn(async (text: string) => {
        written.push(text);
      }),
    },
  });
});

afterEach(() => vi.restoreAllMocks());

/**
 * `navigator.clipboard` appeared nowhere in `src/`, so the reviewer's next action after
 * reading a finding — go to the file, paste the path, paste the run id — was to select a
 * truncated string by hand. These are the two controls that answer it.
 */
describe("copying", () => {
  it("puts the value on the clipboard and says so for a moment", async () => {
    render(<CopyButton value="/work/payments/domain/orders.py:41" label="Copy the path" />);

    const button = screen.getByRole("button", { name: "Copy the path" });
    fireEvent.click(button);

    await waitFor(() =>
      expect(screen.getByRole("button", { name: /copied/i })).toBeInTheDocument(),
    );
    expect(written).toEqual(["/work/payments/domain/orders.py:41"]);
  });

  /**
   * The API is absent over plain HTTP, absent in some webviews, and *rejects* when the
   * document does not have focus. None of those is worth an unhandled rejection, and all of
   * them mean the same thing: do not claim the text was copied.
   */
  it("claims nothing when the clipboard refuses", async () => {
    Object.defineProperty(navigator, "clipboard", {
      configurable: true,
      value: { writeText: vi.fn(async () => Promise.reject(new Error("not allowed"))) },
    });
    const onCopied = vi.fn();
    render(<CopyButton value="x" label="Copy the path" onCopied={onCopied} />);

    fireEvent.click(screen.getByRole("button", { name: "Copy the path" }));

    await waitFor(() => expect(onCopied).toHaveBeenCalledWith(false));
    expect(screen.queryByRole("button", { name: /copied/i })).not.toBeInTheDocument();
  });

  it("hands an excerpt over as the file's own text, without the line numbers", async () => {
    render(<SourceExcerpt excerpt={"def total():\n    return 1\n"} startLine={40} path="a.py" />);

    fireEvent.click(screen.getByRole("button", { name: "Copy the excerpt" }));
    await waitFor(() => expect(written).toEqual(["def total():\n    return 1"]));
  });
});

/**
 * Every source path in the product wore the underline this system reserves for "this goes
 * to the source", and went nowhere at all. It copies now, and it links where somebody has
 * said which editor they use.
 */
describe("a path reference", () => {
  it("copies path and line, in the form an editor takes", async () => {
    render(<PathRef path="/work/payments/domain/orders.py" line={41} endLine={58} />);

    // The range reads well on screen and is not what any editor or search box accepts.
    expect(screen.getByText(":41-58")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /^Copy/ }));
    await waitFor(() => expect(written).toEqual(["/work/payments/domain/orders.py:41"]));
  });

  it("offers no editor link until somebody says which editor they use", () => {
    const { unmount } = render(<PathRef path="/work/payments/domain/orders.py" line={41} />);
    expect(screen.queryByRole("link")).not.toBeInTheDocument();
    unmount();

    window.localStorage.setItem(EDITOR_KEY, "vscode");
    render(<PathRef path="/work/payments/domain/orders.py" line={41} />);
    expect(screen.getByRole("link", { name: "Open in your editor" })).toHaveAttribute(
      "href",
      "vscode://file/work/payments/domain/orders.py:41",
    );
  });

  it("refuses a relative path, which would open the wrong file or none", () => {
    window.localStorage.setItem(EDITOR_KEY, "cursor");
    render(<PathRef path="domain/orders.py" line={4} />);
    expect(screen.queryByRole("link")).not.toBeInTheDocument();
  });
});

describe("the states", () => {
  /**
   * Fifteen `ErrorNotice`s across `src/features` said what went wrong and offered nothing, so
   * the only recovery the product documented was a page reload — for a class of failure that
   * a second attempt usually answers.
   */
  it("carries a way out of a failed request, and reads the same without one", () => {
    const view = render(<ErrorNotice error={new Error("Connection refused")} />);
    expect(screen.getByRole("alert")).toHaveTextContent("Connection refused");

    const retry = vi.fn();
    view.rerender(
      <ErrorNotice
        error={new Error("Connection refused")}
        action={<Button onClick={retry}>Try again</Button>}
      />,
    );
    fireEvent.click(screen.getByRole("button", { name: "Try again" }));
    expect(retry).toHaveBeenCalledOnce();
  });

  /**
   * It is the whole progress signal on a pressed button and inside a chip, and it was
   * `aria-hidden` — so those places announced nothing. Under reduced motion the stylesheet
   * stops every animation, which froze the ring mid-rotation into something that reads as a
   * rendering fault; `.spinner` is what makes the still version deliberate.
   */
  it("says it is working, and is still on purpose for a reader who asked for stillness", () => {
    const { container } = render(<Spinner />);
    expect(screen.getByText("Working")).toHaveClass("sr-only");
    expect(container.querySelector(".spinner")).toBeInTheDocument();
  });

  it("says nothing twice where the caller already printed the label", () => {
    render(<Spinner label="" />);
    expect(screen.queryByText("Working")).not.toBeInTheDocument();
  });
});

describe("a tablist", () => {
  const items = [
    { id: "docket", label: "Docket" },
    { id: "delta", label: "Delta" },
    { id: "report", label: "Report" },
  ];

  it("walks with the arrows and jumps with Home and End", () => {
    const onChange = vi.fn();
    render(<Tabs items={items} active="delta" onChange={onChange} label="Surfaces" />);
    const list = screen.getByRole("tablist", { name: "Surfaces" });

    fireEvent.keyDown(list, { key: "ArrowRight" });
    expect(onChange).toHaveBeenLastCalledWith("report");

    fireEvent.keyDown(list, { key: "Home" });
    expect(onChange).toHaveBeenLastCalledWith("docket");

    fireEvent.keyDown(list, { key: "End" });
    expect(onChange).toHaveBeenLastCalledWith("report");
  });
});

/**
 * The only success signal in the product was a `sr-only` live region, so a sighted reviewer
 * saw nothing at all — and a failure two panels above where you are looking is invisible in
 * the same way from the other side.
 */
describe("the toast", () => {
  function Speaker() {
    const toast = useToast();
    return (
      <>
        <Button onClick={() => toast.say("Decision recorded.")}>Say it</Button>
        <Button onClick={() => toast.warn("The workspace refused that.")}>Warn</Button>
      </>
    );
  }

  const speak = () =>
    render(
      <MemoryRouter>
        <ToastProvider>
          <Speaker />
        </ToastProvider>
      </MemoryRouter>,
    );

  it("announces in one polite region, and can be dismissed", async () => {
    speak();
    fireEvent.click(screen.getByRole("button", { name: "Say it" }));

    const region = await screen.findByRole("status");
    expect(region).toHaveAttribute("aria-live", "polite");
    expect(region).toHaveTextContent("Decision recorded.");

    fireEvent.click(screen.getByRole("button", { name: /^Dismiss:/ }));
    await waitFor(() => expect(region).not.toHaveTextContent("Decision recorded."));
  });

  it("keeps at most three, and keeps the newest", () => {
    speak();
    for (let n = 0; n < 5; n += 1) {
      fireEvent.click(screen.getByRole("button", { name: "Warn" }));
    }
    expect(screen.getAllByRole("button", { name: /^Dismiss:/ })).toHaveLength(3);
  });
});

describe("a drawer", () => {
  /**
   * A panel arrives from the edge it is anchored to, and the left one did not.
   *
   * There was one horizontal animation — `slide-left`, which enters from `+16px` — and both
   * sides used it, so the navigation sat against the left edge and slid in from the right:
   * a panel appearing to come out from under the page it covers. Asserted on the class
   * because the class is the mechanism that was wrong, and because jsdom computes no
   * keyframes to assert on instead.
   */
  it("enters from the side it is anchored to", () => {
    const { rerender } = render(
      <Drawer open onClose={() => {}} side="left" title="Navigation">
        <span>Somewhere to go</span>
      </Drawer>,
    );
    const left = screen.getByRole("dialog", { name: "Navigation" });
    expect(left.className).toContain("animate-slide-right");
    expect(left.className).not.toContain("animate-slide-left");

    rerender(
      <Drawer open onClose={() => {}} side="right" title="Judgement context">
        <span>Why this verdict</span>
      </Drawer>,
    );
    const right = screen.getByRole("dialog", { name: "Judgement context" });
    expect(right.className).toContain("animate-slide-left");
    expect(right.className).not.toContain("animate-slide-right");
  });
});
