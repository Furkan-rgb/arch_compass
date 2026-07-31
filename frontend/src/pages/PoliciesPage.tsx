import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Search, Trash2, X } from "lucide-react";
import { useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { LedgerBar, LedgerCount, LedgerFoot } from "@/components/ledger";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group";
import { cn } from "@/lib/utils";

import { api } from "../api";
import { EmptyLine, ErrorPanel, humanizeLabel, Loading, PageHeader, page, sheet } from "../components";
import { Markdown } from "../markdown";
import { policyApplicabilityLabel } from "../policy-applicability";
import type { Policy } from "../types";

export function filterPolicies(
  policies: Policy[],
  search: string,
  scope: string,
): Policy[] {
  const term = search.trim().toLocaleLowerCase();
  return policies.filter(
    (policy) =>
      (scope === "all" || policy.scope === scope) &&
      (!term ||
        `${policy.id} ${policy.title} ${policy.description || ""} ${policy.tags.join(" ")} ${policy.body} ${policy.applies_to || ""}`
          .toLocaleLowerCase()
          .includes(term)),
  );
}

/**
 * The row précis for a policy that has no authored `description`.
 *
 * Bundled policies each carry one, so this is the fallback for policies from sources outside
 * this product, where the field may be absent. A policy body opens with a `## …` section whose
 * heading restates the title; the line under it is the rule in the author's own words. That
 * line is the only part of the body a table row has room for, and it is the part that
 * distinguishes one row from the next.
 */
function policyPrecis(body: string): string {
  const first = body.split("##")[1]?.replace(/^[^\n]+\n/, "").trim() || "";
  const line = first.split("\n\n")[0].replaceAll("\n", " ").trim();
  return line.length > 150 ? `${line.slice(0, 150).trimEnd()}…` : line;
}

/**
 * A source path as a table cell: the file, and the directory holding it.
 *
 * These are absolute paths on someone's disk, and printed whole they spent half the table
 * on the half of the path that is identical in every row. The end is the part that differs.
 * Nothing is hidden: the full path is the cell's tooltip and the drawer prints it entire.
 */
function sourceLabel(path: string): string {
  const parts = path.split("/").filter(Boolean);
  return parts.length > 2 ? `…/${parts.slice(-2).join("/")}` : path;
}

/* A path or an identifier in a cell of its own: this product's material, in the face it is
   stored in, on its own line and never wrapped. */
const cellCode = "block text-micro whitespace-nowrap text-ink-3";
/* A fact about the record beside it: an uppercase micro label over a value in the face values
   are stored in. The same pair the review's verdict band draws, down to the ellipsis — a value
   here is a word or two, and one that wrapped would make the row of them uneven. */
const factLabel = "text-micro tracking-[.05em] uppercase text-ink-3";
const factValue =
  "mt-0.5 overflow-hidden font-mono text-meta tabular-nums text-ellipsis whitespace-nowrap text-ink-2";

export function PoliciesPage() {
  const queryClient = useQueryClient();
  const [search, setSearch] = useState("");
  const [scope, setScope] = useState("all");
  const policies = useQuery({ queryKey: ["policies"], queryFn: api.policies });
  /**
   * Which policy is open, kept in the URL rather than in a `useState`.
   *
   * It was local state, which was right while the only way in was clicking a row of this
   * table. The palette can now send a reader straight to a policy by name from anywhere in
   * the app, and a destination that no address can describe is not a destination. As a side
   * effect a policy under discussion is now a link someone can paste.
   *
   * Replaced rather than pushed: the parameter says what is open, and reading four policies
   * in a row should not put four steps between the reader and where they came from.
   */
  const [params, setParams] = useSearchParams();
  const selectedId = params.get("policy");
  const selected = useMemo(
    () => (policies.data || []).find((policy) => policy.id === selectedId) || null,
    [policies.data, selectedId],
  );
  const setSelected = (policy: Policy | null) => {
    setParams(
      (current) => {
        const next = new URLSearchParams(current);
        if (policy) next.set("policy", policy.id);
        else next.delete("policy");
        return next;
      },
      { replace: true },
    );
  };
  const sources = useQuery({ queryKey: ["policy-sources"], queryFn: api.policySources });
  const [source, setSource] = useState("");
  const addSource = useMutation({
    mutationFn: api.addPolicySource,
    onSuccess: () => {
      setSource("");
      void queryClient.invalidateQueries({ queryKey: ["policy-sources"] });
      void queryClient.invalidateQueries({ queryKey: ["policies"] });
    },
  });
  const removeSource = useMutation({
    mutationFn: api.removePolicySource,
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["policy-sources"] });
      void queryClient.invalidateQueries({ queryKey: ["policies"] });
    },
  });
  const scopes = useMemo(
    () => [...new Set((policies.data || []).map((policy) => policy.scope))],
    [policies.data],
  );
  const filtered = useMemo(() => {
    return filterPolicies(policies.data || [], search, scope);
  }, [policies.data, scope, search]);

  /** The first of the four that failed, and the second attempt that belongs to it. */
  const failure = policies.error
    ? {
        error: policies.error,
        retry: () => void policies.refetch(),
        retrying: policies.isFetching,
        retryLabel: undefined,
      }
    : sources.error
      ? {
          error: sources.error,
          retry: () => void sources.refetch(),
          retrying: sources.isFetching,
          retryLabel: undefined,
        }
      : addSource.error
        ? {
            error: addSource.error,
            retry: addSource.variables
              ? () => addSource.mutate(addSource.variables!)
              : undefined,
            retrying: addSource.isPending,
            retryLabel: "Add it again",
          }
        : removeSource.error
          ? {
              error: removeSource.error,
              retry: removeSource.variables
                ? () => removeSource.mutate(removeSource.variables!)
                : undefined,
              retrying: removeSource.isPending,
              retryLabel: "Remove it again",
            }
          : null;

  return (
    <div className={page}>
      {/* No rebuild action. Policies are read from their sources whenever they are asked
          for, so what is on this page is what the next review will be shown, and a button
          to bring an index up to date would be a step that changes nothing (ADR 0013). */}
      <PageHeader title="Policies" />
      {/* One strip for four requests, and the retry belongs to whichever of them failed —
          re-reading the corpus after a source failed to attach would report success at
          having done the wrong thing. The order is the order they are tried in above. */}
      {failure ? (
        <ErrorPanel
          error={failure.error}
          onRetry={failure.retry}
          retrying={failure.retrying}
          retryLabel={failure.retryLabel}
        />
      ) : null}

      {/* One row above the sheet: what to look for, which slice, and how many are left. On a
          phone it becomes a stack, where each control is a row rather than a share of one. */}
      <div className="mb-[var(--gap-lg)] flex flex-wrap items-center gap-2.5 max-[620px]:flex-col max-[620px]:items-stretch">
        <label className="relative flex flex-[1_1_240px] items-center max-[620px]:flex-[0_0_30px]">
          <Search
            size={14}
            aria-hidden
            className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-ink-3"
          />
          <span className="sr-only">Search policies</span>
          {/* The icon sits inside the field's own box, so the text starts after it. */}
          <Input
            className="pr-3 pl-[34px] text-meta"
            value={search}
            onChange={(event) => setSearch(event.target.value)}
            placeholder="Search intent, tags, or guidance…"
          />
        </label>
        <ToggleGroup
          type="single"
          value={scope}
          // A group in single mode clears itself when the current item is pressed again.
          // "No filter" is what `all` already says, so the empty value is the one answer
          // this control refuses.
          onValueChange={(value) => {
            if (value) setScope(value);
          }}
          // Full width on a phone, where the row it sits in has nothing else on it and a
          // filter floating at max-content reads as unfinished.
          className="overflow-x-auto max-[620px]:w-full"
          aria-label="Filter by policy scope"
        >
          <ToggleGroupItem value="all">All</ToggleGroupItem>
          {scopes.map((item) => (
            <ToggleGroupItem key={item} value={item}>
              {humanizeLabel(item)}
            </ToggleGroupItem>
          ))}
        </ToggleGroup>
        {/* Mono with tabular figures, because it changes as you type and a number that
            reflows its own width while being read is worse than no number. */}
        <span className="font-mono text-meta tabular-nums whitespace-nowrap text-ink-3">
          {filtered.length} {filtered.length === 1 ? "policy" : "policies"} ·{" "}
          {sources.data?.length || 0} added{" "}
          {sources.data?.length === 1 ? "source" : "sources"}
        </span>
      </div>

      {/* A table, because these are rows of one shape being compared: what the rule is,
          what it bears on, how hard it binds, and where it was authored. The card wall
          this replaced gave every policy a 255px tile and let four of them fill a screen,
          so a corpus of twenty-seven could not be read as a corpus at all. Only facts the
          policy file actually carries are columns — a citation count is not one of them,
          because nothing counts citations.

          The sheet is the scroller, so the scrollbar sits at its foot rather than between
          the last row and the sentence about the corpus. */}
      <div className={cn(sheet, "overflow-x-auto")}>
        {policies.isLoading ? (
          <div className="min-w-0">
            <Loading label="Reading authored policies…" rows={6} />
          </div>
        ) : (
          <Table
            data-slot="policy-table"
            containerClassName="overflow-visible"
            // What makes the sheet scroll sideways rather than let the columns squeeze:
            // without it a narrow screen breaks a source path one character per line.
            className="min-w-[720px]"
          >
            <TableHeader>
              <TableRow>
                <TableHead>Policy</TableHead>
                <TableHead>Applies to</TableHead>
                <TableHead>Strength</TableHead>
                <TableHead>Source</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {filtered.map((policy) => (
                <TableRow
                  key={policy.id}
                  className="cursor-pointer hover:bg-sunken"
                  onClick={() => setSelected(policy)}
                >
                  <TableCell className="min-w-[24ch]">
                    {/* The row is clickable for the pointer; the title is the control, so
                        the keyboard reaches every policy without the row pretending to be
                        a button it cannot announce itself as. */}
                    <button
                      type="button"
                      data-slot="policy-open"
                      className="cursor-pointer border-0 bg-transparent p-0 text-left text-ui font-[650] tracking-[-.01em] text-ink hover:text-accent-ink"
                      onClick={() => setSelected(policy)}
                    >
                      {policy.title}
                    </button>
                    <p className="m-0 mt-0.5 max-w-[62ch] leading-[1.5] text-ink-2">
                      {policy.description || policyPrecis(policy.body)}
                    </p>
                    <code className={cellCode}>{policy.id}</code>
                  </TableCell>
                  <TableCell title={policy.applies_to || undefined}>
                    {policyApplicabilityLabel(policy.scope, policy.applies_to)}
                  </TableCell>
                  <TableCell>
                    {policy.strength === "required" ? (
                      <Badge variant="material">required</Badge>
                    ) : (
                      <span className="text-ink-3">{policy.strength}</span>
                    )}
                  </TableCell>
                  <TableCell>
                    <code className={cellCode} title={policy.source_path}>
                      {sourceLabel(policy.source_path)}
                    </code>
                  </TableCell>
                </TableRow>
              ))}
              {!filtered.length ? (
                <TableRow>
                  <TableCell colSpan={4}>
                    <EmptyLine className="my-1">
                      Nothing matches that. Clear the search, or add the file these rules
                      live in below.
                    </EmptyLine>
                  </TableCell>
                </TableRow>
              ) : null}
            </TableBody>
          </Table>
        )}
        <LedgerFoot>
          The corpus is presented whole to every boundary judged — nothing is retrieved, so
          nothing can be missed.
        </LedgerFoot>
      </div>

      <section className={sheet}>
        <LedgerBar>
          <strong>Additional policy sources</strong>
          <LedgerCount>files stay authored outside Arch Compass</LedgerCount>
        </LedgerBar>
        <div className="flex flex-wrap items-center gap-2.5 p-[var(--card-pad)]">
          <label className="min-w-0 flex-[1_1_260px]">
            <span className="sr-only">Policy file or directory</span>
            <Input
              value={source}
              onChange={(event) => setSource(event.target.value)}
              placeholder="/absolute/path/to/team-policies"
            />
          </label>
          <Button
            disabled={!source.trim() || addSource.isPending}
            onClick={() => addSource.mutate(source.trim())}
          >
            {addSource.isPending ? "Adding…" : "Add source"}
          </Button>
        </div>
        <ul className="m-0 grid list-none px-[22px] pb-5">
          {sources.data?.map((item) => (
            <li key={item.canonical_path} className={sourceRow}>
              <code className="overflow-hidden text-meta text-ellipsis whitespace-nowrap text-ink-2">
                {item.canonical_path}
              </code>
              <Button
                type="button"
                size="icon"
                aria-label={`Remove ${item.canonical_path}`}
                onClick={() => removeSource.mutate(item.canonical_path)}
              >
                <Trash2 size={14} aria-hidden />
              </Button>
            </li>
          ))}
          {!sources.data?.length ? (
            // Capped at reading width, because this one is a sentence rather than a path.
            <li className={cn(sourceRow, "max-w-[76ch] text-meta leading-[1.5] text-ink-3")}>
              Only the bundled Arch Compass corpus is active. Registering a path here is
              persistent, and the files stay yours.
            </li>
          ) : null}
        </ul>
      </section>

      {/* A policy is a document, so it opens as one: a card at reading width, in the middle
          of the page, with the corpus it came from dimmed behind it. It was a drawer at the
          right edge, which is the shape for a panel opened beside a record to work on it —
          but this one is modal, so nothing beside it was legible anyway, and all the edge
          bought was a reading column with the reader's attention elsewhere.

          The overlay is the scroller, as it is for the case layer: policy bodies run from
          three lines to several screens, and a card that grows past the window and scrolls
          the page it floats on beats a fixed frame with the prose scrolling inside it. */}
      <Dialog
        open={selected !== null}
        onOpenChange={(open) => {
          if (!open) setSelected(null);
        }}
      >
        {selected ? (
          <DialogContent
            data-slot="policy-card"
            // Its own close button, in the head beside the title, rather than the floating
            // one: the head is already a row with the title on one side of it.
            showCloseButton={false}
            aria-labelledby="policy-title"
            // Wider than the dialog's default measure, which is sized for a question. This
            // holds a document — headings, lists, the odd code block — at the width the
            // markdown in the rest of the app is set to.
            className="max-w-[760px]"
            overlayClassName="px-[var(--gutter)] py-6"
          >
            <DialogHeader className="flex-row items-start justify-between gap-3">
              <div>
                <DialogTitle id="policy-title" className="mb-0.5 leading-tight">
                  {selected.title}
                </DialogTitle>
                <code className="text-micro text-ink-3">{selected.id}</code>
              </div>
              <Button
                size="icon"
                type="button"
                className="flex-none"
                aria-label="Close policy"
                onClick={() => setSelected(null)}
              >
                <X size={14} aria-hidden />
              </Button>
            </DialogHeader>
            {/* What this policy is, as facts rather than prose: a well of its own, holding
                the row of facts sized by what is in them rather than by a track — a policy
                with four tags and one with none are the same shape of statement, and equal
                columns would give the empty one as much of the drawer as the full one.
                Pushed to the far end, which is where a row of facts sits everywhere in this
                design, until the drawer is too narrow to have a far end. */}
            <dl className="ml-auto flex flex-wrap gap-x-[26px] gap-y-1 rounded-control border border-rule bg-sunken px-3.5 py-2.5 max-[860px]:ml-0">
              <div className="min-w-0">
                <dt className={factLabel}>Strength</dt>
                <dd className={factValue}>{selected.strength}</dd>
              </div>
              <div className="min-w-0">
                <dt className={factLabel}>Author</dt>
                <dd className={factValue}>{selected.source.author}</dd>
              </div>
              <div className="min-w-0">
                <dt className={factLabel}>Applies to</dt>
                <dd className={factValue}>
                  {policyApplicabilityLabel(selected.scope, selected.applies_to)}
                </dd>
              </div>
              <div className="min-w-0">
                <dt className={factLabel}>Tags</dt>
                <dd className={factValue}>{selected.tags.join(", ") || "—"}</dd>
              </div>
            </dl>
            <div className="markdown border-t border-rule-soft pt-1">
              <Markdown>{selected.body}</Markdown>
            </div>
            <p className="m-0 border-t border-rule-soft pt-3 text-micro text-ink-3 [overflow-wrap:anywhere]">
              <code>{selected.source_path}</code>
            </p>
          </DialogContent>
        ) : null}
      </Dialog>
    </div>
  );
}

/* Every row of the source list: the path, and the one thing that can be done to it. The line
   that says there are none is the same row — including its dividing rule, so the section reads
   as a list with one entry in it rather than as a paragraph with a border. */
const sourceRow =
  "grid grid-cols-[minmax(0,1fr)_auto] items-center gap-2 border-t border-rule-soft py-2";
