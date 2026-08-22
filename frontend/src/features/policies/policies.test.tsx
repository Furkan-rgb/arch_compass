import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import type { ReactNode } from "react";
import { MemoryRouter, useLocation } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { api } from "../../api";
import { policyFixture, reviewFixture, reviewSummaryFixture } from "../../test-fixtures";
import { PoliciesPage } from "./policies-page";
import { REQUIRED_SECTIONS, SECTION_PROMPTS, policyTemplate } from "./sections";

/** The address, so a test can read what the page put in it. */
function Address() {
  return <span data-testid="address">{useLocation().search}</span>;
}

function wrap(children: ReactNode, entries: string[] = ["/policies"]) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return (
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={entries}>
        {children}
        <Address />
      </MemoryRouter>
    </QueryClientProvider>
  );
}

/** Nine sections with something written under each, which is what the parser accepts. */
function authoredBody(): string {
  return REQUIRED_SECTIONS.map((name) => `## ${name}\n\nSomething about ${name}.`).join("\n\n");
}

const corpus = [
  policyFixture(),
  policyFixture({
    id: "ports-and-adapters",
    title: "Ports belong to the domain",
    description: "The interface is owned by the side that needs it.",
    strength: "preferred",
    scope: "organisation",
    applies_to: "acme",
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

const architectureCase = {
  case_id: "case-1",
  revision: 1,
  answers: [],
  policy_context: {},
  created_at: "2026-01-01T00:00:00Z",
  updated_at: "2026-01-01T00:00:00Z",
};

beforeEach(() => {
  vi.spyOn(api, "policies").mockResolvedValue(corpus);
  vi.spyOn(api, "policySources").mockResolvedValue([]);
  // The listing drives the repository chooser and the case; the reviews themselves are
  // only read once a policy is open, to say which of them cited it.
  vi.spyOn(api, "reviewSummaries").mockResolvedValue([reviewSummaryFixture()]);
  vi.spyOn(api, "reviews").mockResolvedValue([reviewFixture()]);
  vi.spyOn(api, "cases").mockResolvedValue([architectureCase]);
  vi.spyOn(api, "workspace").mockResolvedValue({
    workspace: "/home/engineer/.archcompass",
    models: { pinned: false, embedding_pinned: false },
    hosted: false,
    source_hosts: [],
  });
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
    await waitFor(() =>
      expect(screen.queryByText("Dependencies point inward")).not.toBeInTheDocument(),
    );
    expect(screen.getByText("Ports belong to the domain")).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText("Search policies"), { target: { value: "" } });
    await waitFor(() => expect(screen.getByText("Dependencies point inward")).toBeInTheDocument());
    fireEvent.click(screen.getByRole("button", { name: /^required/ }));
    expect(screen.getByText("Dependencies point inward")).toBeInTheDocument();
    expect(screen.queryByText("Ports belong to the domain")).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /^all/ }));
    fireEvent.change(screen.getByLabelText("Filter by scope"), {
      target: { value: "organisation" },
    });
    expect(screen.getByText("Ports belong to the domain")).toBeInTheDocument();
    expect(screen.queryByText("Dependencies point inward")).not.toBeInTheDocument();
  });

  /**
   * F38. The Corpus panel was four counts and not one of them was a control — *a count is a
   * control or it is not on screen*. `Required` restated a number the strength filter twenty
   * lines above already owned as a button, and `Showing` restated the length of the list
   * beneath it.
   */
  it("puts the corpus counts on the filters they belong to", async () => {
    render(wrap(<PoliciesPage />));

    const required = await screen.findByRole("button", { name: /^required/ });
    expect(required).toHaveTextContent("1");
    expect(screen.getByRole("button", { name: /^Authored here/ })).toHaveTextContent("1");
    expect(screen.queryByText("Corpus")).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /^Authored here/ }));
    expect(screen.getByText("Team convention")).toBeInTheDocument();
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

  /**
   * F31. A policy is one of the three things `--mark` links to, and the review cites one by
   * id in every bearing it prints — so the expanded policy has to be an address, not
   * component state. It must survive a refresh and arrive from a link.
   */
  it("puts the open policy in the address, in both directions", async () => {
    render(wrap(<PoliciesPage />, ["/policies?open=ports-and-adapters"]));

    expect(await screen.findByText("Prefer a port defined by the domain.")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /Ports belong to the domain/ }));
    await waitFor(() => expect(screen.getByTestId("address").textContent).toBe(""));

    fireEvent.click(screen.getByRole("button", { name: /Team convention/ }));
    await waitFor(() =>
      expect(screen.getByTestId("address")).toHaveTextContent("open=team-convention"),
    );
  });

  it("says which reviews cited the policy, and links to them", async () => {
    render(wrap(<PoliciesPage />, ["/policies?open=dependency-direction"]));

    const cited = (await screen.findByText("Cited by")).parentElement!;
    expect(within(cited).getByRole("link", { name: /payments-platform · review 1/ })).toHaveAttribute(
      "href",
      "/reviews/review-1",
    );
  });

  /**
   * F32. Every review loads its corpus with a repository root, which adds
   * `<repo>/.archcompass/policies`. This page asked without one, so a team keeping its rules
   * in the repository saw them applied in every finding and absent from the page called
   * Policies.
   */
  it("reads the corpus for the repository of the newest review", async () => {
    render(wrap(<PoliciesPage />));

    await screen.findByText("Dependencies point inward");
    expect(api.policies).toHaveBeenCalledWith(
      expect.objectContaining({ repositoryRoot: "/work/payments-platform" }),
    );

    fireEvent.change(screen.getByLabelText("Corpus repository"), { target: { value: "" } });
    await waitFor(() =>
      expect(api.policies).toHaveBeenCalledWith(
        expect.objectContaining({ repositoryRoot: null }),
      ),
    );
  });

  /**
   * F33, the half that lives here. `PolicyContext` decides applicability, and nothing set
   * it — so you could filter the page to organisation policies, read them, and never learn
   * that no judgement can retrieve one.
   */
  it("says whether the current case can reach a scoped policy", async () => {
    render(wrap(<PoliciesPage />, ["/policies?open=ports-and-adapters"]));

    expect(await screen.findByText("out of scope for this case")).toBeInTheDocument();
    expect(
      screen.getByText(/The current case pins no organisation, so retrieval never selects/),
    ).toBeInTheDocument();

    vi.mocked(api.cases).mockResolvedValue([
      { ...architectureCase, policy_context: { organisation: "acme" } },
    ]);
  });

  /**
   * The sources panel described a capability and withheld it: a read-only list of something
   * nobody could add to, whose empty state read as a limit of the product rather than as a
   * thing you had not done yet. The server refuses it on the hosted demo, so there the field
   * is not shown and one line says why.
   */
  it("registers a folder of policies, and says why it cannot on the hosted demo", async () => {
    const add = vi.spyOn(api, "addPolicySource").mockResolvedValue({
      canonical_path: "/work/architecture/policies",
      registered_at: "2026-01-01T00:00:00Z",
    });
    const { unmount } = render(wrap(<PoliciesPage />));

    await screen.findByText("Dependencies point inward");
    fireEvent.change(screen.getByLabelText("Add a folder"), {
      target: { value: "/work/architecture/policies" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Register source" }));
    await waitFor(() => expect(add).toHaveBeenCalledWith("/work/architecture/policies"));

    unmount();
    vi.mocked(api.workspace).mockResolvedValue({
      workspace: "/home/engineer/.archcompass",
      models: { pinned: false, embedding_pinned: false },
      hosted: true,
      source_hosts: [],
    });
    render(wrap(<PoliciesPage />));

    expect(
      await screen.findByText(/a folder on the server cannot be registered/),
    ).toBeInTheDocument();
    expect(screen.queryByLabelText("Add a folder")).not.toBeInTheDocument();
  });

  it("previews the Markdown while it is being authored", async () => {
    const create = vi.spyOn(api, "createPolicy").mockResolvedValue(corpus[2]);
    const body = `${authoredBody()}\n\n## Rule\n\nAdapters **translate**.\n`;
    render(wrap(<PoliciesPage />));

    // The header stays mounted while the corpus loads, so wait for the list rather than
    // for the button.
    await screen.findByText("Dependencies point inward");
    fireEvent.click(screen.getByRole("button", { name: "Author policy" }));
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

    // The header stays mounted while the corpus loads, so wait for the list rather than
    // for the button.
    await screen.findByText("Dependencies point inward");
    fireEvent.click(screen.getByRole("button", { name: "Author policy" }));
    fireEvent.change(screen.getByLabelText("Title"), { target: { value: "Keep adapters thin" } });
    fireEvent.change(screen.getByLabelText("Description"), { target: { value: "Thin adapters." } });
    fireEvent.change(screen.getByLabelText("Policy body"), {
      target: { value: "## Intent\n\nKeep adapters thin.\n" },
    });

    expect(screen.getByRole("button", { name: "Create policy" })).toBeDisabled();
    expect(screen.getByText(/Still to write: Guidance/)).toBeInTheDocument();
    expect(create).not.toHaveBeenCalled();

    fireEvent.change(screen.getByLabelText("Policy body"), { target: { value: authoredBody() } });
    expect(screen.getByRole("button", { name: "Create policy" })).not.toBeDisabled();
  });

  /**
   * F08. The scaffold wrote each heading with its own prompt sentence underneath, and a
   * section counted as written the moment it had any text at all — so an untouched template
   * reported nine of nine written, and a title, a description and one click shipped *"What
   * this policy protects, in one or two sentences."* nine times into the retrieval corpus,
   * where the judge reads it as authored guidance.
   */
  it("will not let the scaffold, or its prompts, be saved as the policy", async () => {
    const create = vi.spyOn(api, "createPolicy");
    render(wrap(<PoliciesPage />));

    // The header stays mounted while the corpus loads, so wait for the list rather than
    // for the button.
    await screen.findByText("Dependencies point inward");
    fireEvent.click(screen.getByRole("button", { name: "Author policy" }));
    fireEvent.change(screen.getByLabelText("Title"), { target: { value: "Keep adapters thin" } });
    fireEvent.change(screen.getByLabelText("Description"), { target: { value: "Thin adapters." } });

    const scaffold = screen.getByLabelText("Policy body") as HTMLTextAreaElement;
    expect(scaffold.value).toBe(policyTemplate());
    expect(scaffold.value).not.toContain(SECTION_PROMPTS.Intent);
    expect(screen.getByRole("button", { name: "Create policy" })).toBeDisabled();
    // The prompt is on screen, where it guides the writing rather than becoming it.
    expect(screen.getByText(SECTION_PROMPTS.Intent)).toBeInTheDocument();

    // Pasting the prompt back into the box is not writing the section either.
    fireEvent.change(scaffold, {
      target: {
        value: REQUIRED_SECTIONS.map((name) => `## ${name}\n\n${SECTION_PROMPTS[name]}`).join("\n\n"),
      },
    });
    expect(screen.getByRole("button", { name: "Create policy" })).toBeDisabled();
    expect(screen.getByText(/Still to write: Intent/)).toBeInTheDocument();
    expect(create).not.toHaveBeenCalled();
  });

  it("edits an existing workspace policy through the same form", async () => {
    const update = vi.spyOn(api, "updatePolicy").mockResolvedValue(corpus[2]);
    render(wrap(<PoliciesPage />));

    fireEvent.click(await screen.findByRole("button", { name: /Team convention/ }));
    fireEvent.click(screen.getByRole("button", { name: "Edit" }));

    const title = screen.getByLabelText("Title") as HTMLInputElement;
    expect(title.value).toBe("Team convention");
    fireEvent.change(title, { target: { value: "Team convention, revised" } });
    fireEvent.change(screen.getByLabelText("Policy body"), { target: { value: authoredBody() } });
    fireEvent.click(screen.getByRole("button", { name: "Save changes" }));

    await waitFor(() =>
      expect(update).toHaveBeenCalledWith(
        "team-convention",
        expect.objectContaining({ title: "Team convention, revised", strength: "guidance" }),
      ),
    );
  });

  /**
   * The editor lost a draft four ways with no warning: Cancel, the header button — which
   * still read "Author policy" while an existing policy was open and remounted the form
   * empty — pressing Edit on a different policy, and leaving the page. The experience doc:
   * *never navigate away from unsaved input*.
   */
  it("does not throw away a draft when a control would unmount the editor", async () => {
    render(wrap(<PoliciesPage />));

    // The header stays mounted while the corpus loads, so wait for the list rather than
    // for the button.
    await screen.findByText("Dependencies point inward");
    fireEvent.click(screen.getByRole("button", { name: "Author policy" }));
    fireEvent.change(screen.getByLabelText("Title"), { target: { value: "Half a thought" } });

    // The header button says what it now does, and asks before doing it.
    fireEvent.click(screen.getByRole("button", { name: "Close editor" }));
    expect(screen.getByText("This policy has changes that have not been saved.")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Keep writing" }));
    expect((screen.getByLabelText("Title") as HTMLInputElement).value).toBe("Half a thought");

    // So does Cancel.
    fireEvent.click(screen.getByRole("button", { name: "Cancel" }));
    fireEvent.click(screen.getByRole("button", { name: "Keep writing" }));
    expect((screen.getByLabelText("Title") as HTMLInputElement).value).toBe("Half a thought");

    // And so does opening a different policy in the same form.
    fireEvent.click(screen.getByRole("button", { name: /Team convention/ }));
    fireEvent.click(screen.getByRole("button", { name: "Edit" }));
    expect(screen.getByText("This policy has changes that have not been saved.")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Discard them" }));
    expect((screen.getByLabelText("Title") as HTMLInputElement).value).toBe("Team convention");
  });
});
