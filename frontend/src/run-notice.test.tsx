/**
 * The signals a run sends to a reader who is not looking at it.
 *
 * Everything here fails silently on the machine it was written on. A title left saying
 * "Reviewing…" after the run ended, a favicon still badged once the reader came back, a toast
 * raised on the very page it is announcing — each of them needs a hidden tab, another route, or
 * an unmount to show itself, and none of those is where anyone is looking while they build it.
 *
 * So the decisions are tested as functions, and the three effects that have a wrong answer
 * worth naming — the title through a whole run, the badge through a return, and the notice's
 * suppression on its own page — are tested through the component.
 */

import { render, screen, act } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { MemoryRouter } from "react-router-dom";

import {
  applyFavicon,
  documentTitle,
  FAVICON_ATTENTION_HREF,
  FAVICON_HREF,
  isSettled,
  NOTICE_LIFETIME_MS,
  PRODUCT_TITLE,
  reviewPath,
  RunSignals,
  shouldNotice,
  type RunPhase,
} from "./run-notice";

/** Pretend the tab is hidden or shown, and tell the page about it as a browser would. */
function setVisibility(state: DocumentVisibilityState) {
  Object.defineProperty(document, "visibilityState", {
    configurable: true,
    value: state,
  });
  act(() => {
    document.dispatchEvent(new Event("visibilitychange"));
  });
}

function iconLink(): HTMLLinkElement {
  const link = document.createElement("link");
  link.setAttribute("rel", "icon");
  link.setAttribute("href", FAVICON_HREF);
  document.head.append(link);
  return link;
}

afterEach(() => {
  document.head.querySelectorAll('link[rel="icon"]').forEach((link) => link.remove());
  Object.defineProperty(document, "visibilityState", {
    configurable: true,
    value: "visible",
  });
  document.title = "";
});

describe("documentTitle", () => {
  it("says a run is going whether or not anyone is watching", () => {
    // The one signal that does not depend on where the reader is: they started it, and the
    // question the tab strip answers is "did that actually take?".
    expect(documentTitle("running", false)).toBe("Reviewing… · Arch Compass");
    expect(documentTitle("running", true)).toBe("Reviewing… · Arch Compass");
  });

  it("leads with the word a truncated tab keeps", () => {
    expect(documentTitle("concluded", true)).toBe("Review ready · Arch Compass");
    expect(documentTitle("holding", true)).toBe("Questions waiting · Arch Compass");
    expect(documentTitle("failed", true)).toBe("Review failed · Arch Compass");
  });

  it("goes quiet once the reader is back, even though the run is still over", () => {
    // The prefix is not a record of what happened — the review's page is that. It is a message
    // to someone who is elsewhere, and it has no business surviving their return.
    expect(documentTitle("concluded", false)).toBe(PRODUCT_TITLE);
    expect(documentTitle("holding", false)).toBe(PRODUCT_TITLE);
    expect(documentTitle("failed", false)).toBe(PRODUCT_TITLE);
  });

  it("is the plain product title when there is no run at all", () => {
    expect(documentTitle(null, false)).toBe(PRODUCT_TITLE);
    // Attention cannot be pending with no run to have raised it, but a title is not the place
    // to discover that: the answer is still the quiet one.
    expect(documentTitle(null, true)).toBe(PRODUCT_TITLE);
  });
});

describe("isSettled", () => {
  it("counts every way a run ends and nothing else", () => {
    expect(isSettled("concluded")).toBe(true);
    expect(isSettled("holding")).toBe(true);
    expect(isSettled("failed")).toBe(true);
    expect(isSettled("running")).toBe(false);
    expect(isSettled(null)).toBe(false);
  });
});

describe("shouldNotice", () => {
  it("does not announce a run to the page already drawing it", () => {
    // The review's own page has the stages, the hold banner and the verdicts, live. A card
    // repeating any of that would be the same fact twice, with one of them in the way.
    expect(shouldNotice("concluded", "rev_1", reviewPath("rev_1"))).toBe(false);
    expect(shouldNotice("holding", "rev_1", "/reviews/rev_1")).toBe(false);
  });

  it("announces it anywhere else in the app", () => {
    expect(shouldNotice("concluded", "rev_1", "/")).toBe(true);
    expect(shouldNotice("holding", "rev_1", "/reviews")).toBe(true);
    expect(shouldNotice("failed", "rev_1", "/policies")).toBe(true);
    // A different review's page is somewhere else, not the page showing this run.
    expect(shouldNotice("concluded", "rev_1", "/reviews/rev_2")).toBe(true);
  });

  it("stays silent while the run is still going", () => {
    expect(shouldNotice("running", "rev_1", "/")).toBe(false);
    expect(shouldNotice(null, "rev_1", "/")).toBe(false);
  });

  it("stays silent when the run failed before there was a review to link to", () => {
    // Nothing navigated, so the reader is still on the start step — which draws the failure
    // itself. A card with no page to send them to would be an apology, not a signal.
    expect(shouldNotice("failed", null, "/")).toBe(false);
  });
});

describe("applyFavicon", () => {
  it("swaps the declared icon and puts it back", () => {
    const link = iconLink();
    applyFavicon(document, true);
    expect(link.getAttribute("href")).toBe(FAVICON_ATTENTION_HREF);
    applyFavicon(document, false);
    expect(link.getAttribute("href")).toBe(FAVICON_HREF);
  });

  it("leaves a document that declares no icon alone", () => {
    // A host that stripped the link said something about what it wants in that slot.
    expect(() => applyFavicon(document, true)).not.toThrow();
    expect(document.querySelector('link[rel="icon"]')).toBeNull();
  });
});

function mount(phase: RunPhase | null, reviewId: string | null, route = "/") {
  return render(
    <MemoryRouter initialEntries={[route]}>
      <RunSignals phase={phase} reviewId={reviewId} />
    </MemoryRouter>,
  );
}

describe("RunSignals: the title through a run", () => {
  it("never leaves the tab claiming a run that is over", () => {
    const view = mount("running", "rev_1");
    expect(document.title).toBe("Reviewing… · Arch Compass");
    view.rerender(
      <MemoryRouter initialEntries={["/"]}>
        <RunSignals phase="concluded" reviewId="rev_1" />
      </MemoryRouter>,
    );
    // The reader was here when it landed, so the page in front of them is the news.
    expect(document.title).toBe(PRODUCT_TITLE);
  });

  it("restores the product title when it goes away", () => {
    const view = mount("running", "rev_1");
    expect(document.title).toBe("Reviewing… · Arch Compass");
    view.unmount();
    expect(document.title).toBe(PRODUCT_TITLE);
  });
});

describe("RunSignals: attention while the tab is hidden", () => {
  it("holds the title and the badge until the reader comes back", () => {
    const link = iconLink();
    const view = mount("running", "rev_1");
    setVisibility("hidden");

    view.rerender(
      <MemoryRouter initialEntries={["/"]}>
        <RunSignals phase="holding" reviewId="rev_1" />
      </MemoryRouter>,
    );
    expect(document.title).toBe("Questions waiting · Arch Compass");
    expect(link.getAttribute("href")).toBe(FAVICON_ATTENTION_HREF);

    setVisibility("visible");
    expect(document.title).toBe(PRODUCT_TITLE);
    expect(link.getAttribute("href")).toBe(FAVICON_HREF);
  });

  it("clears on a window focus, for a tab that was never hidden", () => {
    // Behind another application is not `hidden`, but it is just as away.
    const view = mount("running", "rev_1");
    setVisibility("hidden");
    view.rerender(
      <MemoryRouter initialEntries={["/"]}>
        <RunSignals phase="concluded" reviewId="rev_1" />
      </MemoryRouter>,
    );
    expect(document.title).toBe("Review ready · Arch Compass");

    Object.defineProperty(document, "visibilityState", {
      configurable: true,
      value: "visible",
    });
    act(() => {
      window.dispatchEvent(new Event("focus"));
    });
    expect(document.title).toBe(PRODUCT_TITLE);
  });
});

describe("RunSignals: the notice", () => {
  it("names where the run got to and links to it", () => {
    const view = mount("running", "rev_1");
    view.rerender(
      <MemoryRouter initialEntries={["/"]}>
        <RunSignals phase="holding" reviewId="rev_1" />
      </MemoryRouter>,
    );
    expect(screen.getByText("The review is holding")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Answer the questions" })).toHaveAttribute(
      "href",
      "/reviews/rev_1",
    );
  });

  it("says nothing on the review's own page", () => {
    const view = render(
      <MemoryRouter initialEntries={["/reviews/rev_1"]}>
        <RunSignals phase="running" reviewId="rev_1" />
      </MemoryRouter>,
    );
    view.rerender(
      <MemoryRouter initialEntries={["/reviews/rev_1"]}>
        <RunSignals phase="concluded" reviewId="rev_1" />
      </MemoryRouter>,
    );
    expect(screen.queryByText("The review has finished")).not.toBeInTheDocument();
  });

  it("can be dismissed by hand", async () => {
    const view = mount("running", "rev_1");
    view.rerender(
      <MemoryRouter initialEntries={["/"]}>
        <RunSignals phase="concluded" reviewId="rev_1" />
      </MemoryRouter>,
    );
    const dismiss = screen.getByRole("button", { name: "Dismiss this notice" });
    act(() => {
      dismiss.click();
    });
    expect(screen.queryByText("The review has finished")).not.toBeInTheDocument();
  });

  it("does not spend its life on a tab nobody is looking at", () => {
    // The whole failure this module exists to fix, reintroduced by a timer: the clock must not
    // run out while the reader is away, or the notice is gone before they return.
    vi.useFakeTimers();
    try {
      const link = iconLink();
      expect(link).toBeInTheDocument();
      const view = mount("running", "rev_1");
      setVisibility("hidden");
      view.rerender(
        <MemoryRouter initialEntries={["/"]}>
          <RunSignals phase="concluded" reviewId="rev_1" />
        </MemoryRouter>,
      );
      expect(screen.getByText("The review has finished")).toBeInTheDocument();

      act(() => {
        vi.advanceTimersByTime(NOTICE_LIFETIME_MS * 3);
      });
      expect(screen.getByText("The review has finished")).toBeInTheDocument();

      setVisibility("visible");
      act(() => {
        vi.advanceTimersByTime(NOTICE_LIFETIME_MS + 1);
      });
      expect(screen.queryByText("The review has finished")).not.toBeInTheDocument();
    } finally {
      vi.useRealTimers();
    }
  });

  it("is announced politely rather than interrupting", () => {
    // The region is mounted before there is anything in it: a live region announces what is
    // inserted, so one that arrives with its own content has nothing to announce.
    mount(null, null);
    const region = document.querySelector('[data-slot="run-notices"]');
    expect(region).toHaveAttribute("aria-live", "polite");
  });
});
