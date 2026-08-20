import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, within } from "@testing-library/react";
import type React from "react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";

import { api } from "../../api";
import { AppShell } from "../../app/shell";
import { Tag } from "../../ui/badge";
import { Markdown } from "../../ui/markdown";
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
 * A workspace path is long by nature — `/Users/…/Documents/arch_compass/examples/cases/…` — and
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

/**
 * A fixed label beside a line that is as long as the data made it.
 *
 * This used to guard the attribution gutter, a `6.75rem` grid track that the finding no
 * longer has: the gutter charged that width to every row to print section labels that were
 * not voices, and it went with the serif. The shape of the bug outlived it, though, and moved
 * one component down. A disclosure summary is the same arrangement — a label that must not
 * shrink, beside a line that holds counts, a repository-relative path and a line range, none
 * of which the component chooses the length of.
 *
 * jsdom does no layout, so this asserts the three properties that make the overflow
 * impossible rather than measuring it: the label refuses to shrink, the line beside it is
 * allowed to, and its text may break at any character — because
 * `dependants_of_abstraction (proxy)` and `src/archcompass/domain/orders.py:118-140` are each
 * one token to the line breaker.
 */
describe("a disclosure summary's width", () => {
  it("lets the line beside a fixed label shrink, and break", async () => {
    const review = reviewFixture({ status: "completed", questions: [] });
    vi.spyOn(api, "review").mockResolvedValue(review);
    vi.spyOn(api, "reviews").mockResolvedValue([review]);
    vi.spyOn(api, "reviewRuns").mockResolvedValue([]);
    vi.spyOn(api, "decisions").mockResolvedValue({ branch_id: "branch-1", decisions: [] });

    const client = new QueryClient({
      defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
    });
    render(
      <QueryClientProvider client={client}>
        <MemoryRouter initialEntries={["/reviews/review-1"]}>
          <Routes>
            <Route path="/reviews/:reviewId" element={<ReviewPage />} />
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>,
    );

    // All three closed disclosures, because each one's summary is built from different data
    // and only one of them is the section that happens to be shortest today.
    for (const name of ["Measured", "Policies", "Provenance"]) {
      const label = await screen.findByText(name);
      expect(label.className).toContain("shrink-0");

      const line = label.nextElementSibling as HTMLElement;
      expect(line.className).toContain("min-w-0");
      expect(line.className).toContain("overflow-wrap:anywhere");

      // And the row itself lays them out along the axis it is allowed to grow on, so a long
      // line pushes the chevron nowhere.
      expect(label.parentElement!.className).toContain("flex");
    }
  });
});

/**
 * The same rule again, one component down: a chip is not always a word.
 *
 * `flex-wrap` was doing the work everywhere a row of chips appears — the finding's involved
 * code and an answer's citations — and `flex-wrap` wraps *between* items. (The delta's causes
 * were a third such row until they became a sentence; the rule outlived that particular one.)
 * It has no answer for a single chip wider than the row, and half of these hold a qualified
 * name, which is one token to the line breaker. On the finding that was invisible rather
 * than obvious: the article is `overflow-hidden`, so the chip was not escaping the panel,
 * it was being sliced mid-identifier inside it.
 */
describe("a chip that holds a name", () => {
  function renderFindingWith(qualifiedName: string) {
    const base = reviewFixture({ status: "completed", questions: [] });
    const review = {
      ...base,
      findings: base.findings.map((item) => ({
        ...item,
        candidate: {
          ...item.candidate,
          participants: [{ qualified_name: qualifiedName, role: "implementation" }],
        },
      })),
    };
    vi.spyOn(api, "review").mockResolvedValue(review);
    vi.spyOn(api, "reviews").mockResolvedValue([review]);
    vi.spyOn(api, "reviewRuns").mockResolvedValue([]);
    vi.spyOn(api, "decisions").mockResolvedValue({ branch_id: "branch-1", decisions: [] });

    const client = new QueryClient({
      defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
    });
    return render(
      <QueryClientProvider client={client}>
        <MemoryRouter initialEntries={["/reviews/review-1"]}>
          <Routes>
            <Route path="/reviews/:reviewId" element={<ReviewPage />} />
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>,
    );
  }

  it("caps a participant at the row and breaks the name instead", async () => {
    renderFindingWith(LONG_IDENTIFIER);

    // The name is on screen more than once — the queue lists it too — so this asks the
    // involved-code list for its own copy. Found by its accessible name rather than by a
    // visible heading: the count moved onto the chips themselves, and the list keeps the
    // label for assistive tech, which is the more durable hook of the two anyway.
    const list = await screen.findByRole("list", { name: "Involved code" });
    const name = within(list).getByText(LONG_IDENTIFIER);
    // The name may break at any character, because there is no other place to break it.
    expect(name.className).toContain("wrap-anywhere");
    // And the chip around it, and the list item around that, may be narrower than it.
    expect(name.parentElement?.className).toContain("max-w-full");
    expect(name.parentElement?.parentElement?.className).toContain("max-w-full");
  });

  it("caps every tag, wherever the row it sits in happens to be", () => {
    const { container } = render(<Tag>{LONG_IDENTIFIER}</Tag>);
    const tag = container.firstElementChild!;
    expect(tag.className).toContain("max-w-full");
    expect(tag.className).toContain("wrap-anywhere");
  });
});

/**
 * The report is Markdown, and its headings are names.
 *
 * Every finding in the report leads with its identifier, so `## \`…base.SynthesisProvider\``
 * is a heading whose whole content is one token — at `text-lg` that is wider than a phone,
 * and nothing above it was clipping, so the *page* scrolled sideways rather than the
 * heading. Prose still breaks on spaces; `overflow-wrap: anywhere` only acts on a word with
 * nowhere else to go.
 */
describe("a heading that is a name", () => {
  it("breaks the identifier rather than the page", () => {
    const { container } = render(<Markdown>{`## \`${LONG_IDENTIFIER}\` is implemented once`}</Markdown>);

    const heading = container.querySelector("h3")!;
    expect(heading.className).toContain("wrap-anywhere");
    // Inline code carries the same names inside a sentence, and the same rule.
    expect(container.querySelector("code")!.className).toContain("wrap-anywhere");
  });
});
