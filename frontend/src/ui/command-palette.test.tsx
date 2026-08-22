import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { useState } from "react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { api } from "../api";
import { reviewFixture } from "../test-fixtures";
import { CommandPalette, useCommandPalette } from "./command-palette";

/**
 * The palette's doc comment described three guards for months and the handler had one.
 *
 * It said the shortcut was "refused while something is being typed into and while a modal is
 * already up — the same three guards the decision keys carry". It checked the key and the
 * modifier. So `Ctrl+K` inside a waiver's reason box — kill-to-end-of-line on macOS — opened
 * the palette over what was being written, and `⌘K` with the judgement drawer open stacked a
 * second `aria-modal` dialog on a live focus trap, where the two Escape handlers fought.
 */
function Harness() {
  const palette = useCommandPalette();
  const [modal, setModal] = useState(false);
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return (
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={["/reviews"]}>
        <button type="button" onClick={palette.open}>
          Search everything
        </button>
        <input aria-label="Reason" />
        <button type="button" onClick={() => setModal(true)}>
          Open a drawer
        </button>
        {modal ? <div role="dialog" aria-modal="true" aria-label="A drawer" /> : null}
        <CommandPalette
          open={palette.isOpen}
          onClose={palette.close}
          sections={[
            { to: "/reviews", label: "Reviews" },
            { to: "/policies", label: "Policies" },
          ]}
        />
      </MemoryRouter>
    </QueryClientProvider>
  );
}

const meta = () => screen.queryByRole("dialog", { name: "Search everything" });

beforeEach(() => {
  vi.spyOn(api, "reviews").mockResolvedValue([reviewFixture()]);
  vi.spyOn(api, "repositories").mockResolvedValue([]);
});

afterEach(() => vi.restoreAllMocks());

describe("the command palette", () => {
  it("opens on the shortcut every tool has trained people to try", async () => {
    render(<Harness />);
    fireEvent.keyDown(document, { key: "k", metaKey: true });
    expect(await screen.findByRole("dialog", { name: "Search everything" })).toBeInTheDocument();
  });

  it("refuses the shortcut inside a field, over a modal, and without the modifier", async () => {
    render(<Harness />);

    const field = screen.getByRole("textbox", { name: "Reason" });
    field.focus();
    fireEvent.keyDown(field, { key: "k", ctrlKey: true, target: field });
    expect(meta()).not.toBeInTheDocument();

    fireEvent.keyDown(document, { key: "k" });
    expect(meta()).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Open a drawer" }));
    fireEvent.keyDown(document, { key: "k", metaKey: true });
    expect(meta()).not.toBeInTheDocument();
  });

  /**
   * It toggled. Escape is how a palette closes, and a shortcut that also closes has to decide
   * what to do when a query has been typed and the key is pressed again.
   */
  it("opens rather than toggles, and closes on Escape", async () => {
    render(<Harness />);
    fireEvent.keyDown(document, { key: "k", metaKey: true });
    await screen.findByRole("dialog", { name: "Search everything" });

    fireEvent.keyDown(document, { key: "k", metaKey: true });
    expect(meta()).toBeInTheDocument();

    fireEvent.keyDown(document, { key: "Escape" });
    await waitFor(() => expect(meta()).not.toBeInTheDocument());
  });

  /**
   * It declared `role="dialog" aria-modal="true"` and trapped nothing: Tab from the last
   * result walked into the page behind the overlay, and focus never came back to the opener.
   */
  it("takes focus into the search field and hands it back to whatever opened it", async () => {
    render(<Harness />);
    const opener = screen.getByRole("button", { name: "Search everything" });
    opener.focus();
    fireEvent.click(opener);

    const field = await screen.findByRole("combobox");
    await waitFor(() => expect(document.activeElement).toBe(field));

    fireEvent.keyDown(document, { key: "Escape" });
    await waitFor(() => expect(document.activeElement).toBe(opener));
  });

  /**
   * The results were buttons carrying `aria-current`, walked by the arrow keys — a highlight
   * that is visible and completely silent, because nothing announces a moving `aria-current`
   * on a button. A listbox with `aria-activedescendant` on the field is the markup that says
   * what the interaction already was.
   */
  it("is a real listbox, and says which option the field is on", async () => {
    render(<Harness />);
    fireEvent.keyDown(document, { key: "k", metaKey: true });

    const field = await screen.findByRole("combobox");
    const list = await screen.findByRole("listbox", { name: "Results" });
    const options = await screen.findAllByRole("option");

    expect(list).toContainElement(options[0]);
    expect(options[0]).toHaveAttribute("aria-selected", "true");
    expect(field).toHaveAttribute("aria-activedescendant", options[0].id);

    fireEvent.keyDown(field, { key: "ArrowDown" });
    expect(screen.getAllByRole("option")[1]).toHaveAttribute("aria-selected", "true");
    expect(field).toHaveAttribute("aria-activedescendant", screen.getAllByRole("option")[1].id);
  });

  it("finds a review by name, and offers the sections beside it", async () => {
    render(<Harness />);
    fireEvent.keyDown(document, { key: "k", metaKey: true });

    const field = await screen.findByRole("combobox");
    await waitFor(() =>
      expect(screen.getAllByRole("option").length).toBeGreaterThan(2),
    );

    fireEvent.change(field, { target: { value: "policies" } });
    const options = screen.getAllByRole("option");
    expect(options).toHaveLength(1);
    expect(options[0]).toHaveTextContent("Policies");
  });
});
