import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it } from "vitest";

import { VIEWPORT, setViewportWidth } from "../../test-setup";
import { LandingPage } from "./landing-page";

beforeEach(() => setViewportWidth(VIEWPORT.desktop));

function renderLanding() {
  return render(
    <MemoryRouter>
      <LandingPage />
    </MemoryRouter>,
  );
}

describe("the landing page", () => {
  it("leads with the product's positioning and both calls to action", () => {
    renderLanding();

    expect(
      screen.getByRole("heading", {
        level: 1,
        name: "Architecture review grounded in your code, policies, and decisions.",
      }),
    ).toBeInTheDocument();
    expect(screen.getAllByRole("link", { name: /Review a repository/ })[0]).toHaveAttribute(
      "href",
      "/start",
    );
    expect(screen.getByRole("link", { name: "Explore an example review" })).toHaveAttribute(
      "href",
      "/reviews",
    );
  });

  it("says plainly what the product is not", () => {
    renderLanding();

    const faq = screen.getByRole("heading", { name: "Is ArchCompass an autonomous coding agent?" });
    expect(faq).toBeInTheDocument();
    expect(screen.getByText(/It does not edit code, open branches/)).toBeInTheDocument();
  });

  it("expands one FAQ answer at a time", () => {
    renderLanding();

    const question = screen.getByRole("button", { name: "Can I use Ollama?" });
    expect(question).toHaveAttribute("aria-expanded", "false");
    fireEvent.click(question);
    expect(question).toHaveAttribute("aria-expanded", "true");
    expect(
      screen.getByRole("button", { name: "Is ArchCompass an autonomous coding agent?" }),
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
      "#how-it-works",
    );
  });
});
