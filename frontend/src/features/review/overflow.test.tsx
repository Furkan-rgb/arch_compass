import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, within } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";

import { api } from "../../api";
import { AppShell } from "../../app/shell";
import { Tag } from "../../ui/badge";
import { Markdown } from "../../ui/markdown";
import { splitQualified } from "../../lib/format";
import { ReviewPage } from "./review-page";
import { reviewFixture, workspaceFixture } from "../../test-fixtures";

const LONG_IDENTIFIER =
  "infrastructure.persistence.repositories.SqlAlchemyNotificationPreferenceRepository";

/** The docket on a review whose one candidate is named the way real ones are. */
function renderDocketWithLongIdentifier() {
  const base = reviewFixture({ status: "completed", questions: [] });
  // The one that still wants a person, because the docket opens on the attention filter and
  // a cleared candidate is deliberately not in it.
  const finding = base.findings.find((item) => item.verdict !== "cleared")!;
  const review = {
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

/**
 * A row may not be wider than the column it is in, whatever it is asked to hold.
 *
 * This is the bug that shipped: a rail's scroller is `overflow-y-auto`, CSS resolves the
 * other axis to `auto` alongside it, and nothing in a row broke a dotted identifier — so one
 * real name (`infrastructure.persistence.repositories.SqlAlchemyNotificationPreferenceRepository`)
 * took the content from 266px to 651px inside a 266px box. The example repository's names
 * are `ports.Clock`, which is why no test caught it.
 *
 * The rail is gone and the rule outlived it. A docket row is wider than the rail ever was and
 * that only moves the threshold: a name is still one token to the line breaker, and a phone is
 * still 390px. jsdom does no layout, so this asserts the properties that make the pixels
 * impossible rather than the pixels: the identity may break mid-token, the context above it
 * may be cut, and the column holding both may be narrower than its content.
 */
describe("a docket row's width", () => {
  it("gives every part of a row a way not to grow", async () => {
    renderDocketWithLongIdentifier();
    await screen.findByRole("list", { name: "Candidates" });

    const { namespace, leaf } = splitQualified(LONG_IDENTIFIER);

    // The namespace is context and is allowed to be cut off.
    const namespaceNode = screen.getByText(`${namespace}.`);
    expect(namespaceNode.className).toContain("truncate");
    expect(namespaceNode.className).toContain("min-w-0");

    // The leaf is the identity, so it is kept — by wrapping mid-token if it has to.
    const leafNode = screen.getByText(leaf);
    expect(leafNode.className).toContain("[overflow-wrap:anywhere]");

    // The column holding them can be narrower than its content, and so can the one above it.
    expect(leafNode.parentElement?.parentElement?.className).toContain("min-w-0");
  });

  it("keeps the whole identifier readable even though the row is not", async () => {
    renderDocketWithLongIdentifier();
    await screen.findByRole("list", { name: "Candidates" });

    // Truncating for the eye is not the same as hiding: hovering still names the thing.
    // Asked for by `data-candidate` rather than by name, because the name is on more than one
    // control now — the open row's involved-code list carries a copy button per participant,
    // and what is being asserted is the *row's* title.
    const row = document.querySelector<HTMLElement>("[data-candidate]")!;
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
 * the drawer it now lives in is a fixed 20rem track. `truncate` sets `white-space: nowrap`,
 * which makes the element's min-content width the whole string, so a grid or flex ancestor
 * left at its default `min-width: auto` is widened by the very thing the truncation was
 * supposed to hide. Truncation is a promise the ancestors have to keep.
 *
 * The 232px sidebar this used to guard is gone — six links and a path down the full height of
 * every screen, charged to the one surface that needed the width. The path moved into the
 * navigation drawer, which is the same fixed track one component along, so the rule outlived
 * the rail and this opens the drawer to reach it.
 */
describe("the navigation drawer's width", () => {
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

    fireEvent.click(screen.getByRole("button", { name: "Open navigation" }));

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
 * The other axis, and the bug that shipped with it — now answered by not having the box.
 *
 * The queue used to be a capped rail: `flex-1 min-h-0 overflow-y-auto` inside a
 * `max-h-… overflow-hidden` panel, which only bounds itself if every box above it lays its
 * children out with a height to divide. One of them was still block flow, so the list grew to
 * its full content height and the cap clipped it — no scrollbar, and the last row cut in half.
 *
 * There is no capped rail any more. The docket is one column that scrolls with the document,
 * which is the version of this that cannot come back: a page has no height to divide up and
 * nothing to clip. So the guard is that nobody reintroduces one, rather than a chain walk.
 */
describe("the docket's height", () => {
  it("scrolls with the page rather than inside a box of its own", async () => {
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

    const list = await screen.findByRole("list", { name: "Candidates" });

    // Nothing between the list and the page caps a height or scrolls an axis of its own.
    let node: HTMLElement | null = list.parentElement;
    while (node && node !== container) {
      expect(node.className).not.toMatch(/\bmax-h-|\boverflow-y-(auto|scroll)\b/);
      node = node.parentElement;
    }
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

    // Both closed disclosures, because each one's summary is built from different data and
    // only one of them is the section that happens to be shortest today. `Measured` was a
    // third until the machine's evidence came out from behind it and onto the surface, beside
    // the claim it supports.
    for (const name of ["Policies", "Provenance"]) {
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
