import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

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

/**
 * The three verdicts in the picker, without the pause control that stands beside them.
 *
 * The picker is a legend and a chooser and now an off switch as well, so "the buttons in the
 * picker" is no longer the same set as "the verdicts".
 */
const verdictButtons = () =>
  within(screen.getByRole("group", { name: "Example bearings" }))
    .getAllByRole("button")
    .filter((button) => !button.getAttribute("aria-label")?.includes("showcase"));

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
    // One primary action, and the second is a walk down this page rather than a second
    // button pointing at a review list that is empty on a first visit.
    expect(screen.getByRole("link", { name: "See how a finding is made" })).toHaveAttribute(
      "href",
      "#finding",
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
   * Retrieval finds several policies and only some of them apply to the verdict. Both counts
   * are recorded on a real review, and printing only the first would overstate how much of
   * the corpus was actually weighed.
   */
  it("separates what retrieval found from what applied to the judgement", () => {
    renderLanding();

    expect(within(specimen()).getByText(/found/)).toHaveTextContent("6 found · 2 applied");
  });

  /**
   * `Verdict` has three values and the judge chooses one of them by name, so there is no
   * magnitude anywhere in the domain. Anything on this page that looked like a score would
   * be asserting a measurement nothing took.
   */
  it("shows a verdict as one of three states and never as a score", () => {
    renderLanding();

    const buttons = verdictButtons();
    expect(buttons.map((button) => button.textContent)).toEqual(["Material", "Held", "Cleared"]);
    expect(buttons[0]).toHaveAttribute("aria-pressed", "true");

    fireEvent.click(buttons[1]);
    expect(buttons[1]).toHaveAttribute("aria-pressed", "true");
    expect(buttons[0]).toHaveAttribute("aria-pressed", "false");
    // The held specimen is the one that cannot be settled without a person.
    expect(within(specimen()).getByText(/Hinges on:/)).toBeInTheDocument();
  });

  /**
   * The map and the callout are one statement, not two illustrations that happen to sit
   * near each other: the candidate a finding was made against is a place on the atlas, and
   * moving between the specimens has to move which place is lit. Render them independently
   * and the hero is back to claiming the deterministic half rather than showing it.
   *
   * The map is `aria-hidden` — the callout names the candidate in text, so announcing the
   * labels would say it twice — which is why this reads the DOM rather than the roles.
   */
  it("lights the atlas node the shown finding was made against", () => {
    renderLanding();
    const lit = () => document.querySelector("svg text.font-semibold:not([class*=uppercase])");

    expect(lit()).toHaveTextContent("gateway");

    const picker = screen.getByRole("group", { name: "Example bearings" });
    fireEvent.click(within(picker).getAllByRole("button")[1]);
    expect(lit()).toHaveTextContent("orders");
    // The same name the finding section four screens down gives this candidate. The hero and
    // the exhibit are deliberately the same three, and this one used to be `orders.Repository`
    // here and `domain.orders` there — the same policy, claim and file, offered under two
    // qualified names.
    expect(within(specimen()).getByText("domain.orders")).toBeInTheDocument();
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

  /**
   * The picker is a showcase before it is a control.
   *
   * Two seconds is short enough that a visitor sees all three verdicts without deciding to,
   * and the five-second hold is what stops that being hostile: touching a verdict has to buy
   * enough time to read the one you asked for. Both numbers are the point of the feature, so
   * both are asserted rather than the mere fact that something moves.
   */
  describe("the hero's showcase", () => {
    beforeEach(() => vi.useFakeTimers({ shouldAdvanceTime: true }));
    afterEach(() => vi.useRealTimers());

    const pressed = () =>
      verdictButtons().findIndex((button) => button.getAttribute("aria-pressed") === "true");
    const pause = () => screen.getByRole("button", { name: "Pause the showcase" });

    /**
     * One pass, and then it is the reader's page again.
     *
     * Three verdicts is the whole vocabulary: six seconds teaches that there are three of
     * them and that the picker moves between them. After that the movement has nothing left
     * to say and is only taking a ninety-word specimen away from somebody reading it, on the
     * first screen of the page, for ever.
     */
    it("moves through the three verdicts, two seconds each, and then stops", () => {
      renderLanding();

      expect(pressed()).toBe(0);
      act(() => void vi.advanceTimersByTime(2000));
      expect(pressed()).toBe(1);
      act(() => void vi.advanceTimersByTime(2000));
      expect(pressed()).toBe(2);
      act(() => void vi.advanceTimersByTime(2000));
      expect(pressed()).toBe(0);

      // The pass ended where it began, and the reader gets to finish that one.
      act(() => void vi.advanceTimersByTime(6000));
      expect(pressed()).toBe(0);
      // And the toggle claims nothing. It used to report `!showcasing`, which goes false when
      // the pass ends by itself — so six seconds after load a control nobody had touched
      // filled in and announced `aria-pressed="true"`. What it reports is the reader's own
      // press; the next test is the one that presses it.
      expect(pause()).toHaveAttribute("aria-pressed", "false");
    });

    it("stops on the specimen being read when the pause is pressed, and replays it", () => {
      renderLanding();

      expect(pause()).toHaveAttribute("aria-pressed", "false");
      fireEvent.click(pause());
      expect(pause()).toHaveAttribute("aria-pressed", "true");

      // Two full cycles' worth of time, and nothing moved.
      act(() => void vi.advanceTimersByTime(4000));
      expect(pressed()).toBe(0);

      // Pressing it again runs the pass from the top rather than being a control for nothing.
      fireEvent.click(pause());
      expect(pause()).toHaveAttribute("aria-pressed", "false");
      act(() => void vi.advanceTimersByTime(2000));
      expect(pressed()).toBe(1);
    });

    it("holds a chosen verdict for five seconds before the showcase resumes", () => {
      renderLanding();
      const buttons = verdictButtons();

      fireEvent.click(buttons[2]);
      expect(pressed()).toBe(2);

      // Four seconds in, the two-second cycle would have moved twice. The hold is what keeps
      // the reader on the one they asked for.
      act(() => void vi.advanceTimersByTime(4000));
      expect(pressed()).toBe(2);

      // Five seconds, then the first interval of the resumed showcase.
      act(() => void vi.advanceTimersByTime(1000));
      act(() => void vi.advanceTimersByTime(2000));
      expect(pressed()).toBe(0);
    });

    /**
     * The pause belongs to the figure, not to the screen.
     *
     * `holdProps` used to sit on the whole hero section, which is most of a first screen —
     * so a cursor resting anywhere in it stopped the showcase before it ran once. At eleven
     * seconds a specimen that was invisible; at two it is the whole feature not working.
     */
    it("keeps moving while the cursor is elsewhere in the hero", () => {
      renderLanding();

      fireEvent.mouseEnter(screen.getByRole("heading", { level: 1 }));
      act(() => void vi.advanceTimersByTime(2000));
      expect(pressed()).toBe(1);
    });

    it("stops while the specimen or the picker is being read", () => {
      renderLanding();

      fireEvent.mouseEnter(specimen().parentElement as HTMLElement);
      act(() => void vi.advanceTimersByTime(6000));
      expect(pressed()).toBe(0);

      fireEvent.mouseLeave(specimen().parentElement as HTMLElement);
      act(() => void vi.advanceTimersByTime(2000));
      expect(pressed()).toBe(1);
    });

    it("restarts the hold when the same verdict is chosen again", () => {
      renderLanding();
      const buttons = verdictButtons();

      fireEvent.click(buttons[1]);
      act(() => void vi.advanceTimersByTime(4000));
      fireEvent.click(buttons[1]);
      act(() => void vi.advanceTimersByTime(4000));
      expect(pressed()).toBe(1);
    });
  });

  /**
   * The section used to draw its own copy of the finding surface, and outlived it: the
   * attribution gutter it drew was deleted when the queue and the workbench became one
   * docket, and the page kept showing it. What is asserted here is that the page renders the
   * workbench's own component — the attribution lines, the measurement labels and the folds
   * are `FindingBody`'s, and none of them can be produced by a drawing of it.
   */
  it("shows the workbench's own finding surface rather than a copy of it", async () => {
    renderLanding();

    // The section is loaded on its own, after the page. Scoped to it, because the hero names
    // the same candidate — an unscoped query would pass on the specimen and prove nothing.
    const surface = () => within(document.querySelector("#finding") as HTMLElement);
    expect(await surface().findByText("Judged")).toBeInTheDocument();

    // `Attribution`, `MEASUREMENT_LABELS` and `Disclosure` — all three from `finding-detail`.
    expect(surface().getByText("Measured")).toBeInTheDocument();
    expect(surface().getByText("referenced by")).toBeInTheDocument();
    expect(surface().getByText("Provenance")).toBeInTheDocument();
    expect(surface().getByText(/2 of 6 policies applied/)).toBeInTheDocument();
    // And the decision it offers is the workbench's own wording, off `CHOICES`.
    expect(surface().getByText("Accept and act")).toBeInTheDocument();
  });

  /** A row states its own claim, and opens in place. That is the docket's whole argument. */
  it("opens a docket row in place", async () => {
    renderLanding();

    const row = await screen.findByRole("button", { name: /The orders domain imports/ });
    expect(row).toHaveAttribute("aria-expanded", "false");
    fireEvent.click(row);
    expect(row).toHaveAttribute("aria-expanded", "true");
    // The lookups behind the hinge, which is the newest thing on the finding surface.
    expect(screen.getByText("Looked up")).toBeInTheDocument();
  });

  it("names the catalogue by the ids the application owns", () => {
    renderLanding();

    // Mono, because the id is the machine quoting itself. `corpus.test.ts` is what checks
    // these three against `FindingPattern`; this only checks the page draws them.
    expect(screen.getByText("sole_implementation")).toBeInTheDocument();
    expect(screen.getByText("duplicated_knowledge")).toBeInTheDocument();
    expect(screen.getByText("scattered_concept")).toBeInTheDocument();
    expect(
      screen.getByRole("heading", { name: "An abstraction with one implementation behind it" }),
    ).toBeInTheDocument();
  });

  it("says what the catalogue declines to raise, not only what it finds", () => {
    renderLanding();

    expect(
      screen.getByRole("heading", { name: "A type parameter is not a constant" }),
    ).toBeInTheDocument();
    expect(screen.getByText(/are not fifteen modules repeating themselves/)).toBeInTheDocument();
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
