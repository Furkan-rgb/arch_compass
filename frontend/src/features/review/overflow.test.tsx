import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import type React from "react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";

import { api } from "../../api";
import { AppShell } from "../../app/shell";
import { splitQualified } from "../../lib/format";
import { AttentionQueue } from "./attention-queue";
import { ReviewPage } from "./review-page";
import { reviewFixture, workspaceFixture } from "../../test-fixtures";

/**
 * The rail may not be wider than its column, whatever it is asked to hold.
 *
 * This is the bug that shipped: the queue's scroller is `overflow-y-auto`, CSS resolves the
 * other axis to `auto` alongside it, and nothing in a row broke a dotted identifier — so one
 * real name (`infrastructure.persistence.repositories.SqlAlchemyNotificationPreferenceRepository`)
 * took the content from 266px to 651px inside a 266px box. The example repository's names
 * are `ports.Clock`, which is why no test caught it.
 *
 * jsdom does no layout, so this cannot assert on pixels. It asserts on the two properties
 * that make the pixels impossible instead: the axis is clipped, and every element on the
 * path from the column to the text either wraps at any character or is truncated.
 */
/** The queue reads the branch's standing decisions, so it needs a client even alone. */
function withClient(node: React.ReactNode) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={client}>{node}</QueryClientProvider>;
}

const LONG_IDENTIFIER =
  "infrastructure.persistence.repositories.SqlAlchemyNotificationPreferenceRepository";

function queueWithLongIdentifier() {
  const base = reviewFixture();
  const [finding] = base.findings;
  return {
    ...base,
    findings: [
      {
        ...finding,
        candidate: {
          ...finding.candidate,
          summary:
            "One repository implementation serves both the billing and the notification boundary.",
          participants: [
            { qualified_name: LONG_IDENTIFIER, role: "implementation" },
            ...finding.candidate.participants.slice(1),
          ],
        },
      },
    ],
  };
}

describe("the attention queue's width", () => {
  it("clips the axis a vertical scroller must never scroll on", () => {
    const review = queueWithLongIdentifier();
    const { container } = render(
      withClient(
        <AttentionQueue
          review={review}
          selection={null}
          onSelect={() => {}}
          filter="all"
          onFilterChange={() => {}}
        />,
      ),
    );

    const scroller = container.querySelector(".overflow-y-auto");
    expect(scroller).not.toBeNull();
    expect(scroller?.className).toContain("overflow-x-clip");
  });

  it("gives every part of a row a way not to grow", () => {
    const review = queueWithLongIdentifier();
    render(
      withClient(
        <AttentionQueue
          review={review}
          selection={null}
          onSelect={() => {}}
          filter="all"
          onFilterChange={() => {}}
        />,
      ),
    );

    const { namespace, leaf } = splitQualified(LONG_IDENTIFIER);

    // The namespace is context and is allowed to be cut off.
    const namespaceNode = screen.getByText(namespace);
    expect(namespaceNode.className).toContain("truncate");

    // The leaf is the identity, so it is kept — by wrapping mid-token if it has to.
    const leafNode = screen.getByText(leaf);
    expect(leafNode.className).toContain("[overflow-wrap:anywhere]");
    expect(leafNode.className).toContain("line-clamp-2");

    // The column holding them can be narrower than its content.
    const column = leafNode.parentElement;
    expect(column?.className).toContain("min-w-0");
  });

  it("keeps the whole identifier readable even though the row is not", () => {
    const review = queueWithLongIdentifier();
    render(
      withClient(
        <AttentionQueue
          review={review}
          selection={null}
          onSelect={() => {}}
          filter="all"
          onFilterChange={() => {}}
        />,
      ),
    );

    // Truncating for the eye is not the same as hiding: hovering still names the thing.
    const row = screen.getByRole("button", { name: new RegExp(splitQualified(LONG_IDENTIFIER).leaf) });
    expect(row).toHaveAttribute("title", LONG_IDENTIFIER);
  });

  it("splits a qualified name into where it lives and what it is called", () => {
    expect(splitQualified(LONG_IDENTIFIER)).toEqual({
      namespace: "infrastructure.persistence.repositories",
      leaf: "SqlAlchemyNotificationPreferenceRepository",
    });
    // A bare name has nowhere to live, and is all identity.
    expect(splitQualified("Clock")).toEqual({ namespace: "", leaf: "Clock" });
  });
});

/**
 * The same rule, one level up.
 *
 * A workspace path is long by nature — `/Users/…/Documents/arch_compass/eval/cases/…` — and
 * the sidebar is a fixed 232px track. `truncate` sets `white-space: nowrap`, which makes the
 * element's min-content width the whole string, so a grid or flex ancestor left at its
 * default `min-width: auto` is widened by the very thing the truncation was supposed to
 * hide. Truncation is a promise the ancestors have to keep.
 */
describe("the sidebar's width", () => {
  it("keeps a long workspace path inside the rail", async () => {
    vi.spyOn(api, "workspace").mockResolvedValue(
      workspaceFixture({
        workspace: "/Users/someone/Documents/work/platform/services/notifications/.archcompass",
      }),
    );
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const { container } = render(
      <QueryClientProvider client={client}>
        <MemoryRouter>
          <AppShell>
            <div>content</div>
          </AppShell>
        </MemoryRouter>
      </QueryClientProvider>,
    );

    const path = await screen.findByTitle(
      "/Users/someone/Documents/work/platform/services/notifications/.archcompass",
    );
    expect(path.className).toContain("truncate");

    // Every box between the fixed track and the truncated text can be narrower than its
    // content. Without this the truncation is decorative and the rail grows instead.
    let node: HTMLElement | null = path.parentElement;
    let shrinkable = 0;
    while (node && node !== container) {
      if (node.className.includes("min-w-0")) shrinkable += 1;
      node = node.parentElement;
    }
    expect(shrinkable).toBeGreaterThanOrEqual(3);
  });
});

/**
 * The other axis, and the bug that shipped with it.
 *
 * The queue's scroller is `flex-1 min-h-0 overflow-y-auto`, which only bounds itself if
 * every box above it is laying its children out with a height to divide. The rail's panel
 * was capped (`max-h-… overflow-hidden`) but still block flow, so the list grew to its full
 * content height and the cap clipped it: no scrollbar, and the last row cut in half.
 *
 * jsdom does no layout, so this asserts the chain instead of the pixels — from the capped
 * box down to the scroller, every element is a flex column and the scroller may shrink.
 */
describe("the attention queue's height", () => {
  it("spends the height it caps, so the last row is reachable", async () => {
    const review = reviewFixture({ status: "completed", questions: [] });
    vi.spyOn(api, "review").mockResolvedValue(review);
    vi.spyOn(api, "reviews").mockResolvedValue([review]);
    vi.spyOn(api, "reviewRuns").mockResolvedValue([]);
    vi.spyOn(api, "decisions").mockResolvedValue({ branch_id: "branch-1", decisions: [] });

    const client = new QueryClient({
      defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
    });
    const { container } = render(
      <QueryClientProvider client={client}>
        <MemoryRouter initialEntries={["/reviews/review-1"]}>
          <Routes>
            <Route path="/reviews/:reviewId" element={<ReviewPage />} />
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>,
    );

    await screen.findByRole("list", { name: "Candidates" });

    const scroller = container.querySelector<HTMLElement>(".overflow-y-auto");
    expect(scroller).not.toBeNull();
    expect(scroller?.className).toContain("min-h-0");

    // Walk up to the box that caps the height. Everything in between must be a flex column,
    // and everything in between must be allowed to be shorter than its content — otherwise
    // the cap is a pair of scissors rather than a budget.
    let node = scroller?.parentElement ?? null;
    let capped: HTMLElement | null = null;
    while (node && node !== container) {
      expect(node.className).toContain("flex-col");
      if (node.className.includes("max-h-")) {
        capped = node;
        break;
      }
      // Only the box that sets the cap is allowed to insist on its own height.
      expect(node.className).toContain("min-h-0");
      node = node.parentElement;
    }
    expect(capped).not.toBeNull();
    expect(capped?.className).toContain("overflow-hidden");
  });
});
