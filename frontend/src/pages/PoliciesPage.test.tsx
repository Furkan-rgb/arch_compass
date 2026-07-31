import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import { api } from "../api";
import { policyApplicabilityLabel } from "../policy-applicability";
import type { Policy } from "../types";
import { filterPolicies, PoliciesPage } from "./PoliciesPage";

const policies: Policy[] = [
  {
    id: "POL-OWN-001",
    title: "Keep capability knowledge with its owner",
    description:
      "Discovering what a provider can do is the provider's own business. Spread across "
      + "callers, every new provider becomes an edit in each of them.",
    scope: "general",
    applies_to: null,
    strength: "preferred",
    tags: ["ownership", "providers"],
    source: { author: "Arch Compass", inspiration: [] },
    body: "Provider-specific capability discovery belongs behind the provider boundary.",
    source_path: "/policies/ownership.md",
    content_hash: "one",
  },
  {
    id: "POL-LOCAL-001",
    title: "Keep one behavior local",
    scope: "repository",
    applies_to: "repo_arch_compass",
    strength: "guidance",
    tags: ["abstraction"],
    source: { author: "Team", inspiration: [] },
    body: "Do not introduce a conceptual interface without credible independent variation.",
    source_path: "/repo/.archcompass/policies/local.md",
    content_hash: "two",
  },
];

/* The one this workspace wrote. Nothing about the fixture says so except `origin`, which is
   the point: the path below is the same shape as the repository-scoped policy above, and a
   page that read editability off a path would offer the wrong two rows. */
const authored: Policy = {
  id: "keep-imports-pointing-inward",
  title: "Keep imports pointing inward",
  description: "A module that imports its caller has no boundary left to defend.",
  scope: "general",
  applies_to: null,
  strength: "guidance",
  tags: ["layering"],
  source: { author: "Workspace", inspiration: [] },
  body: "## Intent\nKeep the arrows going one way.",
  source_path: "/workspace/.archcompass/policies/keep-imports-pointing-inward.md",
  content_hash: "three",
  origin: "workspace",
};

describe("policy catalog filtering", () => {
  it("matches authored body text and tags", () => {
    expect(filterPolicies(policies, "provider boundary", "all")).toEqual([
      policies[0],
    ]);
    expect(filterPolicies(policies, "abstraction", "all")).toEqual([policies[1]]);
  });

  it("matches the authored description, and policies without one still match", () => {
    expect(filterPolicies(policies, "the provider's own business", "all")).toEqual([
      policies[0],
    ]);
    // The second fixture carries no description at all — what external policy sources look
    // like — and is still reachable by everything else it does carry.
    expect(policies[1].description).toBeUndefined();
    expect(filterPolicies(policies, "credible independent variation", "all")).toEqual([
      policies[1],
    ]);
  });

  it("combines search with scope", () => {
    expect(filterPolicies(policies, "local", "repository")).toEqual([policies[1]]);
    expect(filterPolicies(policies, "local", "general")).toEqual([]);
  });

  it("searches and labels scoped policy identity", () => {
    expect(filterPolicies(policies, "repo_arch_compass", "all")).toEqual([
      policies[1],
    ]);
    expect(policyApplicabilityLabel("general", null)).toBe("All contexts");
    expect(
      policyApplicabilityLabel("repository", "repo_arch_compass"),
    ).toBe("repository · repo_arch_compass");
  });
});

/** The corpus this page reads, with the catalog under the test's control. */
function corpus(catalog: Policy[]) {
  vi.spyOn(api, "policies").mockResolvedValue(catalog);
  vi.spyOn(api, "policySources").mockResolvedValue([]);
}

function open() {
  render(
    <QueryClientProvider
      client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}
    >
      <MemoryRouter>
        <PoliciesPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

/** Open one policy's card by pressing its title, and hand back the card. */
async function openCard(title: string): Promise<HTMLElement> {
  fireEvent.click(await screen.findByRole("button", { name: title }));
  return await screen.findByRole("dialog");
}

afterEach(() => vi.restoreAllMocks());

describe("authoring a policy from the catalog", () => {
  it("offers editing only on the policies this workspace wrote", async () => {
    corpus([policies[0], authored]);

    open();

    // The marker is on the authored row and on no other, and it is `origin` that put it
    // there — both fixtures are `general` policies with a description and a path.
    const rows = await screen.findAllByRole("row");
    const marked = rows.filter((row) => within(row).queryByText("yours"));
    expect(marked).toHaveLength(1);
    expect(within(marked[0]).getByText("Keep imports pointing inward")).toBeInTheDocument();

    const readOnly = await openCard("Keep capability knowledge with its owner");
    expect(within(readOnly).queryByRole("button", { name: "Edit" })).toBeNull();
    expect(within(readOnly).queryByRole("button", { name: "Delete" })).toBeNull();
    fireEvent.click(within(readOnly).getByRole("button", { name: "Close policy" }));

    const editable = await openCard("Keep imports pointing inward");
    expect(within(editable).getByRole("button", { name: "Edit" })).toBeInTheDocument();
    expect(within(editable).getByRole("button", { name: "Delete" })).toBeInTheDocument();
  });

  it("sends the form to the API, id and scope left to the server", async () => {
    corpus([policies[0]]);
    const created = vi.spyOn(api, "createPolicy").mockResolvedValue(authored);

    open();
    fireEvent.click(await screen.findByRole("button", { name: /New policy/ }));

    const editor = await screen.findByRole("dialog");
    const body = within(editor).getByRole("textbox", { name: /nine sections/ });
    // The frame is already in the box, so nobody has to know the nine headings by heart.
    expect((body as HTMLTextAreaElement).value).toContain("## Diagnostic questions");

    fireEvent.change(within(editor).getByRole("textbox", { name: /What is the rule/ }), {
      target: { value: "Keep imports pointing inward" },
    });
    fireEvent.change(within(editor).getByRole("textbox", { name: /The précis/ }), {
      target: { value: "A module that imports its caller has no boundary left." },
    });
    fireEvent.change(within(editor).getByRole("textbox", { name: /Tags/ }), {
      target: { value: "layering, dependencies" },
    });
    fireEvent.change(body, { target: { value: "## Intent\nOne way only." } });
    fireEvent.click(within(editor).getByRole("button", { name: "Create policy" }));

    await waitFor(() => expect(created).toHaveBeenCalledTimes(1));
    expect(created).toHaveBeenCalledWith({
      title: "Keep imports pointing inward",
      description: "A module that imports its caller has no boundary left.",
      tags: ["layering", "dependencies"],
      strength: "guidance",
      body: "## Intent\nOne way only.",
    });
  });

  it("edits through the route that keeps the id, prefilled with what is stored", async () => {
    corpus([authored]);
    const updated = vi.spyOn(api, "updatePolicy").mockResolvedValue(authored);

    open();
    const card = await openCard("Keep imports pointing inward");
    fireEvent.click(within(card).getByRole("button", { name: "Edit" }));

    const editor = await screen.findByRole("form", { name: "Edit policy" });
    expect(within(editor).getByRole("textbox", { name: /What is the rule/ })).toHaveValue(
      "Keep imports pointing inward",
    );
    expect(within(editor).getByRole("textbox", { name: /Tags/ })).toHaveValue("layering");
    fireEvent.click(within(editor).getByRole("button", { name: "Save policy" }));

    await waitFor(() => expect(updated).toHaveBeenCalledTimes(1));
    expect(updated.mock.calls[0][0]).toBe("keep-imports-pointing-inward");
  });

  it("asks before deleting, and deletes nothing until it is answered", async () => {
    corpus([authored]);
    const deleted = vi.spyOn(api, "deletePolicy").mockResolvedValue(undefined);

    open();
    const card = await openCard("Keep imports pointing inward");
    fireEvent.click(within(card).getByRole("button", { name: "Delete" }));

    const ask = await screen.findByRole("group", {
      name: "Delete Keep imports pointing inward?",
    });
    expect(deleted).not.toHaveBeenCalled();

    // Backing out leaves the policy open and untouched, which is the answer this has to
    // make as reliably as the other one.
    fireEvent.click(within(ask).getByRole("button", { name: "Keep it" }));
    expect(
      screen.queryByRole("group", { name: /^Delete Keep imports/ }),
    ).toBeNull();
    expect(deleted).not.toHaveBeenCalled();

    fireEvent.click(within(card).getByRole("button", { name: "Delete" }));
    fireEvent.click(await screen.findByRole("button", { name: "Delete permanently" }));

    await waitFor(() => expect(deleted).toHaveBeenCalledTimes(1));
    expect(deleted.mock.calls[0][0]).toBe("keep-imports-pointing-inward");
  });
});
