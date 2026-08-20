import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import type { ReactNode } from "react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { api } from "../../api";
import { policyFixture } from "../../test-fixtures";
import { PoliciesPage } from "./policies-page";
import { policyTemplate } from "./sections";

function wrap(children: ReactNode) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return (
    <QueryClientProvider client={client}>
      <MemoryRouter>{children}</MemoryRouter>
    </QueryClientProvider>
  );
}

const corpus = [
  policyFixture(),
  policyFixture({
    id: "ports-and-adapters",
    title: "Ports belong to the domain",
    description: "The interface is owned by the side that needs it.",
    strength: "preferred",
    scope: "organisation",
    tags: ["ports"],
    body: "Prefer a port defined by the domain.",
  }),
  policyFixture({
    id: "team-convention",
    title: "Team convention",
    description: "Authored in this workspace.",
    strength: "guidance",
    origin: "workspace",
    tags: [],
    body: "Local guidance.",
  }),
];

beforeEach(() => {
  vi.spyOn(api, "policies").mockResolvedValue(corpus);
  vi.spyOn(api, "policySources").mockResolvedValue([]);
});

afterEach(() => vi.restoreAllMocks());

describe("the policy corpus", () => {
  it("renders the policy body as Markdown, not as raw text", async () => {
    render(wrap(<PoliciesPage />));

    fireEvent.click(await screen.findByRole("button", { name: /Dependencies point inward/ }));

    expect(await screen.findByRole("heading", { name: "When this applies" })).toBeInTheDocument();
    expect(screen.getAllByRole("listitem").map((item) => item.textContent)).toContain(
      "Ports belong to the domain",
    );
    expect(screen.getByText("must not").tagName).toBe("STRONG");
    expect(screen.queryByText(/## When this applies/)).not.toBeInTheDocument();
  });

  it("filters by search, strength and scope", async () => {
    render(wrap(<PoliciesPage />));

    expect(await screen.findByText("Ports belong to the domain")).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText("Search policies"), { target: { value: "interface" } });
    expect(screen.queryByText("Dependencies point inward")).not.toBeInTheDocument();
    expect(screen.getByText("Ports belong to the domain")).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText("Search policies"), { target: { value: "" } });
    fireEvent.click(screen.getByRole("button", { name: "required" }));
    expect(screen.getByText("Dependencies point inward")).toBeInTheDocument();
    expect(screen.queryByText("Ports belong to the domain")).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "all" }));
    fireEvent.change(screen.getByLabelText("Filter by scope"), {
      target: { value: "organisation" },
    });
    expect(screen.getByText("Ports belong to the domain")).toBeInTheDocument();
    expect(screen.queryByText("Dependencies point inward")).not.toBeInTheDocument();
  });

  it("offers editing and deletion only for policies this workspace owns", async () => {
    render(wrap(<PoliciesPage />));

    fireEvent.click(await screen.findByRole("button", { name: /Dependencies point inward/ }));
    expect(screen.getByText(/Read from a registered source/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Edit" })).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /Team convention/ }));
    expect(screen.getByRole("button", { name: "Edit" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Delete" })).toBeInTheDocument();
  });

  it("previews the Markdown while it is being authored", async () => {
    const create = vi.spyOn(api, "createPolicy").mockResolvedValue(corpus[2]);
    const body = `${policyTemplate()}\n## Rule\n\nAdapters **translate**.\n`;
    render(wrap(<PoliciesPage />));

    fireEvent.click(await screen.findByRole("button", { name: "Author policy" }));
    fireEvent.change(screen.getByLabelText("Title"), { target: { value: "Keep adapters thin" } });
    fireEvent.change(screen.getByLabelText("Description"), {
      target: { value: "Adapters translate, they do not decide." },
    });
    fireEvent.change(screen.getByLabelText("Policy body"), { target: { value: body } });
    fireEvent.change(screen.getByLabelText("Tags"), { target: { value: "adapters, boundaries" } });

    fireEvent.click(screen.getByRole("tab", { name: "Preview" }));
    const preview = screen.getByRole("tabpanel");
    expect(within(preview).getByRole("heading", { name: "Rule" })).toBeInTheDocument();
    expect(within(preview).getByText("translate")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Create policy" }));
    await waitFor(() =>
      expect(create).toHaveBeenCalledWith({
        title: "Keep adapters thin",
        description: "Adapters translate, they do not decide.",
        body: body.trim(),
        tags: ["adapters", "boundaries"],
        strength: "guidance",
      }),
    );
  });

  it("refuses to save a policy the workspace parser would reject", async () => {
    const create = vi.spyOn(api, "createPolicy");
    render(wrap(<PoliciesPage />));

    fireEvent.click(await screen.findByRole("button", { name: "Author policy" }));
    fireEvent.change(screen.getByLabelText("Title"), { target: { value: "Keep adapters thin" } });
    fireEvent.change(screen.getByLabelText("Description"), { target: { value: "Thin adapters." } });
    fireEvent.change(screen.getByLabelText("Policy body"), {
      target: { value: "## Intent\n\nKeep adapters thin.\n" },
    });

    expect(screen.getByRole("button", { name: "Create policy" })).toBeDisabled();
    expect(screen.getByText(/Still to write: Guidance/)).toBeInTheDocument();
    expect(create).not.toHaveBeenCalled();

    // The scaffold the form starts from is, by itself, a document the workspace accepts.
    fireEvent.change(screen.getByLabelText("Policy body"), { target: { value: policyTemplate() } });
    expect(screen.getByRole("button", { name: "Create policy" })).not.toBeDisabled();
  });

  it("edits an existing workspace policy through the same form", async () => {
    const update = vi.spyOn(api, "updatePolicy").mockResolvedValue(corpus[2]);
    render(wrap(<PoliciesPage />));

    fireEvent.click(await screen.findByRole("button", { name: /Team convention/ }));
    fireEvent.click(screen.getByRole("button", { name: "Edit" }));

    const title = screen.getByLabelText("Title") as HTMLInputElement;
    expect(title.value).toBe("Team convention");
    fireEvent.change(title, { target: { value: "Team convention, revised" } });
    fireEvent.change(screen.getByLabelText("Policy body"), { target: { value: policyTemplate() } });
    fireEvent.click(screen.getByRole("button", { name: "Save changes" }));

    await waitFor(() =>
      expect(update).toHaveBeenCalledWith(
        "team-convention",
        expect.objectContaining({ title: "Team convention, revised", strength: "guidance" }),
      ),
    );
  });
});
