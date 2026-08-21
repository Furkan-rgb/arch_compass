import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it } from "vitest";

import { VIEWPORT, setViewportWidth } from "../../test-setup";
import { LandingPage } from "./landing-page";

beforeEach(() => setViewportWidth(VIEWPORT.desktop));

/**
 * The specimen currently on show.
 *
 * All three are in the DOM at once — that is what keeps the card one height — so a query
 * has to be scoped to the visible one, and the other two are `aria-hidden` precisely so
 * that `getByRole` finds exactly this one.
 */
const specimen = () => screen.getByRole("group", { name: /^(Material|Held|Cleared)$/ });

function renderLanding() {
  return render(
    <MemoryRouter>
      <LandingPage />
    </MemoryRouter>,
  );
}

describe("the landing page", () => {
  it("leads with guidance, and with both calls to action", () => {
    renderLanding();

    expect(
      screen.getByRole("heading", {
        level: 1,
        name: "Write your guidance once. Every review weighs it.",
      }),
    ).toBeInTheDocument();
    expect(screen.getAllByRole("link", { name: /Review a repository/ })[0]).toHaveAttribute(
      "href",
      "/start",
    );
    expect(screen.getByRole("link", { name: "Read a real finding" })).toHaveAttribute(
      "href",
      "/reviews",
    );
  });

  /**
   * The hero's whole claim is that a verdict rests on guidance somebody wrote, so the
   * policy it names has to be one that actually ships. A specimen is allowed; an invented
   * corpus is not.
   */
  it("names a policy the bundled corpus really contains", () => {
    renderLanding();

    expect(
      screen.getByRole("heading", { name: "Delay abstractions until variation is credible" }),
    ).toBeInTheDocument();
    expect(screen.getByText("delay-premature-abstraction")).toBeInTheDocument();
  });

  /**
   * Retrieval pulls several policies and only some of them bear on the verdict. Both counts
   * are recorded on a real review, and printing only the first would overstate how much of
   * the corpus was actually weighed.
   */
  it("separates what retrieval pulled from what bore on the judgement", () => {
    renderLanding();

    expect(within(specimen()).getByText(/retrieved/)).toHaveTextContent(
      "6 retrieved · 2 bore on the judgement",
    );
  });

  /**
   * `Verdict` has three values and `FindingOutput.material` is a bool, so there is no
   * magnitude in the domain. Anything on this page that looked like a score would be
   * asserting a measurement nothing took.
   */
  it("shows a verdict as one of three states and never as a score", () => {
    renderLanding();

    const picker = screen.getByRole("group", { name: "Example bearings" });
    const buttons = within(picker).getAllByRole("button");
    expect(buttons.map((button) => button.textContent)).toEqual(["Material", "Held", "Cleared"]);
    expect(buttons[0]).toHaveAttribute("aria-pressed", "true");

    fireEvent.click(buttons[1]);
    expect(buttons[1]).toHaveAttribute("aria-pressed", "true");
    expect(buttons[0]).toHaveAttribute("aria-pressed", "false");
    // The held specimen is the one that cannot be settled without a person.
    expect(within(specimen()).getByText(/Hinges on:/)).toBeInTheDocument();
  });

  /**
   * The card used to carry a `min-h` measured off one browser at one text size, with three
   * pixels of headroom. At a 20px root size the held specimen wrapped an extra line, grew
   * past it, and shoved the rest of the page down every six seconds.
   *
   * jsdom has no layout to measure, so what is asserted here is the mechanism that makes
   * the height constant: every specimen is in the DOM, stacked in one grid cell, with the
   * two that are not on show hidden by visibility rather than unmounted. Render only the
   * active one and this fails.
   */
  it("keeps every specimen in the layout so the card holds one height", () => {
    renderLanding();

    // Every specimen's policy id is in the document at once, so all three are laid out.
    for (const id of [
      "delay-premature-abstraction",
      "give-state-one-writer",
      "explicit-source-of-truth",
    ]) {
      expect(screen.getByText(id)).toBeInTheDocument();
    }
    // And exactly one of them is on show: the other two are hidden, not unmounted.
    expect(screen.getAllByRole("group", { name: /^(Material|Held|Cleared)$/ })).toHaveLength(1);
  });

  it("says plainly what the product is not", () => {
    renderLanding();

    expect(screen.getByRole("heading", { name: "Not an autonomous agent" })).toBeInTheDocument();
    expect(screen.getByText(/It does not roam the repository/)).toBeInTheDocument();
  });

  it("expands one FAQ answer at a time", () => {
    renderLanding();

    const question = screen.getByRole("button", { name: "Can I use Ollama?" });
    expect(question).toHaveAttribute("aria-expanded", "false");
    fireEvent.click(question);
    expect(question).toHaveAttribute("aria-expanded", "true");
    expect(
      screen.getByRole("button", { name: /Does it send my whole repository/ }),
    ).toHaveAttribute("aria-expanded", "false");
  });

  it("reveals scroll sections immediately when motion is unavailable", async () => {
    renderLanding();
    // jsdom has no IntersectionObserver, which is the same path a reduced-motion reader takes:
    // the content is present and finished rather than waiting for an animation.
    await waitFor(() =>
      expect(document.querySelectorAll('.reveal[data-revealed="true"]').length).toBeGreaterThan(3),
    );
  });

  it("keeps the section navigation reachable behind a menu on a phone", async () => {
    setViewportWidth(VIEWPORT.phone);
    renderLanding();

    fireEvent.click(screen.getByRole("button", { name: "Open menu" }));
    const drawer = await screen.findByRole("dialog", { name: "ArchCompass" });
    expect(drawer).toBeInTheDocument();
    expect(screen.getAllByRole("link", { name: "How it works" })[0]).toHaveAttribute(
      "href",
      "#how",
    );
  });
});
