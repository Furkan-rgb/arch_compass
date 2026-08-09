/**
 * No text a model or a repository writes may widen the page.
 *
 * The overflow this defends against was met on a phone: a boundary opened, and an
 * unbroken token — a qualified name, a path, a rationale's identifier — pushed the
 * layout past the viewport. jsdom does no layout, so this cannot measure pixels; what
 * it can do is the review that would have caught the bug: render the surfaces that show
 * unowned text with a hostile unbreakable token in every field, then walk every element
 * that ended up holding it and demand a wrap or scroll guard somewhere in its ancestry.
 *
 * The guard list is the contract. A class is a guard only if it actually bounds long
 * content — Tailwind's wrap/scroll utilities, or a class whose bounding rule lives in
 * styles.css (`pre` scrolls, `.mono-path` and `.evidence-list` wrap anywhere). Adding a
 * new way of bounding text means adding it here, which is the point: the sweep fails on
 * the next field somebody renders bare.
 */

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { api } from "./api";
import { FindingSource } from "./finding-source";
import { InvestigationDisclosure } from "./investigation-disclosure";
import { FindingsLedger } from "./review-ledger";
import type { ReviewedBoundary } from "./types";

/** Unbreakable and unmistakable: no spaces, no hyphens, nothing a browser may wrap on. */
const HOSTILE = "OVERFLOWXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX";

const GUARDS = [
  /\boverflow-x-auto\b/,
  /\boverflow-auto\b/,
  /\boverflow-hidden\b/,
  /overflow-wrap:anywhere/,
  /\bbreak-words\b/,
  /\bbreak-all\b/,
  /\btruncate\b/,
  /\btext-ellipsis\b/,
  // Classes whose bounding rule lives in styles.css rather than in the class name.
  /\bmono-path\b/,
  /\bevidence-list\b/,
];

function guarded(element: Element): boolean {
  for (let node: Element | null = element; node; node = node.parentElement) {
    // styles.css bounds every bare `pre` with `overflow-x: auto`.
    if (node.tagName === "PRE") return true;
    const classes = node.getAttribute("class") ?? "";
    if (GUARDS.some((pattern) => pattern.test(classes))) return true;
  }
  return false;
}

/** Every element directly holding the hostile token with no guard above it, described. */
function offenders(container: HTMLElement): string[] {
  return [...container.querySelectorAll<HTMLElement>("*")]
    .filter((element) =>
      [...element.childNodes].some(
        (node) => node.nodeType === Node.TEXT_NODE && (node.textContent ?? "").includes(HOSTILE),
      ),
    )
    .filter((element) => !guarded(element))
    .map(
      (element) =>
        `<${element.tagName.toLowerCase()} class="${(element.getAttribute("class") ?? "").slice(0, 100)}">`,
    );
}

function hostileBoundary(): ReviewedBoundary {
  return {
    reference: "BR-001",
    candidate: {
      pattern: "duplicated_knowledge",
      summary: `${HOSTILE} is stated in 2 modules with the same value.`,
      participants: [
        {
          node_id: "one",
          qualified_name: `package.${HOSTILE}`,
          role: `States the constant ${HOSTILE} beside its comment.`,
          location: { path: `src/${HOSTILE}.py`, start_line: 12, end_line: 30 },
        },
        {
          node_id: "two",
          qualified_name: `package.other.${HOSTILE}`,
          role: `Names ${HOSTILE} on line 12 — a consumer of one of the copies.`,
          location: { path: `src/other/${HOSTILE}.py`, start_line: 12, end_line: 12 },
        },
      ],
      measurements: [{ name: "consumer_sites", value: 2 }],
      limitations: `A sweep for ${HOSTILE} cannot see reflection.`,
    },
    material: true,
    rationale: `The copies agree because both feed ${HOSTILE} into one client.`,
    verdict_label: "Not earning its place",
    recommended_response: `Give ${HOSTILE} one owner.`,
    hinge: {
      unknown: `Whether ${HOSTILE} must move in step.`,
      if_confirmed: `${HOSTILE} gets one owner.`,
      if_denied: `${HOSTILE} stays put.`,
    },
    policy_bearings: [
      {
        policy_id: "one-writer",
        policy_title: `One writer for ${HOSTILE}`,
        how: `Two modules write ${HOSTILE}.`,
      },
    ],
  };
}

describe("overflow guards", () => {
  it("an opened boundary bounds every field a model or repository wrote", () => {
    vi.spyOn(api, "reviewSource").mockResolvedValue([]);
    const { container } = render(
      <QueryClientProvider
        client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}
      >
        <FindingsLedger
          reviewed={[hostileBoundary()]}
          policyCount={7}
          reviewId="rev_1"
          open="BR-001"
          onOpen={() => {}}
          onShowInAtlas={null}
        />
      </QueryClientProvider>,
    );

    expect(offenders(container)).toEqual([]);
  });

  it("the evidence rows bound the names, paths and roles they caption code with", async () => {
    vi.spyOn(api, "reviewSource").mockResolvedValue([
      {
        reference: "BR-001",
        qualified_name: `package.${HOSTILE}`,
        role: `Consumes ${HOSTILE}.`,
        location: { path: `src/${HOSTILE}.py`, start_line: 1, end_line: 2 },
        text: `VALUE = "${HOSTILE}"`,
        provenance: `Read live from ${HOSTILE}.`,
        unavailable: "",
      },
    ]);
    const { container } = render(
      <QueryClientProvider
        client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}
      >
        <FindingSource reviewId="rev_1" reference="BR-001" />
      </QueryClientProvider>,
    );
    await screen.findByText(/The code this was measured from/i);

    expect(offenders(container)).toEqual([]);
  });

  it("the investigation transcript bounds lookups, results and notes", () => {
    const { container } = render(
      <InvestigationDisclosure
        investigation={{
          lookups: [
            {
              tool: "search_source",
              arguments: { query: HOSTILE },
              result: `src/${HOSTILE}.py:1: VALUE = ${HOSTILE}`,
            },
          ],
          closing: `Both copies feed ${HOSTILE}.`,
          abandoned: `the reply about ${HOSTILE} was truncated`,
          prompt_identity: "investigate-for-answer:v1:abc123def456",
        }}
      />,
    );

    expect(offenders(container)).toEqual([]);
  });
});
