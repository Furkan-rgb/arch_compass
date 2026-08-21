import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useMemo, useState } from "react";

import { api, type RepositorySummary } from "../../api";
import { cn } from "../../lib/cn";
import { relativeTime, repositoryName } from "../../lib/format";
import { Tag } from "../../ui/badge";
import { Button } from "../../ui/button";
import { Field, Input, Select } from "../../ui/field";
import { ArrowUp, CheckIcon, FolderIcon, GitBranchIcon } from "../../ui/icons";
import { Mono } from "../../ui/meta";
import { EmptyState, ErrorNotice, Spinner } from "../../ui/states";
import { Tabs, TabPanel } from "../../ui/tabs";

/**
 * Four ways to name a repository, and no typing required for three of them.
 *
 * The path field remains — an absolute path is still the fastest way in for someone who
 * knows it — but "recent", "browse" and "clone" are what a first visit actually uses.
 */
export function RepositoryPicker({
  value,
  onChange,
}: {
  value: string;
  onChange: (root: string) => void;
}) {
  const [tab, setTab] = useState("recent");
  const repositories = useQuery({ queryKey: ["repositories"], queryFn: api.repositories });
  const examples = useQuery({ queryKey: ["examples"], queryFn: api.examples });

  /**
   * One entry per repository, not per time it was indexed.
   *
   * `/api/repositories` answers "which checkouts have been indexed", and every re-index adds
   * a row — which is correct for a version listing and wrong for a chooser. Anyone testing
   * against the same repository ends up picking it out of eight copies of itself, and the
   * eight-item cap then means eight copies of one repository is the whole list.
   *
   * Keyed on `root_path` because that is the only thing this control actually hands back;
   * two paths are two choices even when they are clones of the same repository. The rows
   * arrive newest first, so the first one seen is the one to keep, and the count beside it
   * says how many indexes are behind it rather than hiding them.
   */
  const indexed = useMemo(() => {
    const seen = new Map<string, { repository: RepositorySummary; versions: number }>();
    for (const repository of repositories.data ?? []) {
      const existing = seen.get(repository.root_path);
      if (existing) existing.versions += 1;
      else seen.set(repository.root_path, { repository, versions: 1 });
    }
    return [...seen.values()];
  }, [repositories.data]);

  const hasRecent = Boolean(indexed.length);

  return (
    <div>
      <Tabs
        label="Choose a repository"
        active={tab}
        onChange={setTab}
        variant="solid"
        items={[
          { id: "recent", label: "Indexed", count: indexed.length || undefined },
          { id: "browse", label: "Browse" },
          { id: "clone", label: "Clone" },
          { id: "example", label: "Examples", count: examples.data?.length },
        ]}
      />

      <div className="mt-3">
        <TabPanel id="recent" active={tab}>
          {repositories.isLoading ? (
            <div className="flex items-center gap-2 py-4 text-sm text-ink-3">
              <Spinner /> Loading indexed repositories…
            </div>
          ) : !hasRecent ? (
            <EmptyState title="Nothing indexed yet" className="py-8">
              Browse for a folder on this machine, or clone a repository by address.
            </EmptyState>
          ) : (
            <ul className="grid gap-1.5 sm:grid-cols-2">
              {indexed.slice(0, 8).map(({ repository, versions }) => (
                <li key={repository.root_path}>
                  <button
                    type="button"
                    onClick={() => onChange(repository.root_path)}
                    aria-pressed={value === repository.root_path}
                    className={cn(
                      "w-full rounded-md border px-3 py-2.5 text-left transition",
                      value === repository.root_path
                        ? "border-ink bg-sunken"
                        : "border-rule bg-surface hover:border-rule-strong",
                    )}
                  >
                    <div className="flex items-center gap-2">
                      <FolderIcon className="size-4 shrink-0 text-ink-3" />
                      <span className="truncate text-sm font-semibold text-ink">
                        {repositoryName(repository.root_path)}
                      </span>
                    </div>
                    <Mono className="mt-1 block truncate text-[11px] text-ink-3">
                      {repository.root_path}
                    </Mono>
                    <div className="mt-1.5 flex flex-wrap items-center gap-1.5 text-[11px] text-ink-3">
                      {repository.branch_name ? (
                        <span className="inline-flex items-center gap-1">
                          <GitBranchIcon className="size-3" />
                          {repository.branch_name}
                        </span>
                      ) : null}
                      <span>indexed {relativeTime(repository.created_at)}</span>
                      {versions > 1 ? (
                        <span title={`${versions} atlas versions of this checkout`}>
                          · {versions} indexes
                        </span>
                      ) : null}
                    </div>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </TabPanel>

        <TabPanel id="browse" active={tab}>
          <DirectoryBrowser value={value} onChange={onChange} />
        </TabPanel>

        <TabPanel id="clone" active={tab}>
          <CloneForm onCheckedOut={onChange} />
        </TabPanel>

        <TabPanel id="example" active={tab}>
          <ExampleList value={value} onChange={onChange} />
        </TabPanel>
      </div>
    </div>
  );
}

function DirectoryBrowser({
  value,
  onChange,
}: {
  value: string;
  onChange: (root: string) => void;
}) {
  const [path, setPath] = useState<string | undefined>(undefined);
  const listing = useQuery({
    queryKey: ["directories", path ?? "~"],
    queryFn: () => api.directories(path),
  });

  if (listing.error) {
    return (
      <div className="grid gap-3">
        <ErrorNotice error={listing.error} title="Browsing is unavailable" />
        <PathField value={value} onChange={onChange} />
      </div>
    );
  }

  return (
    <div className="grid gap-3">
      <div className="rounded-md border border-rule bg-surface">
        <div className="flex items-center gap-2 border-b border-rule px-3 py-2">
          <Button
            size="sm"
            variant="ghost"
            disabled={!listing.data?.parent}
            onClick={() => setPath(listing.data?.parent ?? undefined)}
          >
            <ArrowUp className="size-[13px]" /> Up
          </Button>
          <Mono className="min-w-0 flex-1 truncate text-[11px]">
            {listing.data?.path ?? "…"}
          </Mono>
          <Button
            size="sm"
            variant="secondary"
            disabled={!listing.data?.path}
            onClick={() => onChange(listing.data!.path)}
          >
            Use this folder
          </Button>
        </div>
        <ul className="scrollbar-slim max-h-56 overflow-y-auto p-1.5">
          {listing.isLoading ? (
            <li className="flex items-center gap-2 px-2 py-3 text-sm text-ink-3">
              <Spinner /> Reading…
            </li>
          ) : !listing.data?.directories.length ? (
            <li className="px-2 py-3 text-sm text-ink-3">No sub-folders here.</li>
          ) : (
            listing.data.directories.map((entry) => (
              <li key={entry.path}>
                <button
                  type="button"
                  onClick={() => setPath(entry.path)}
                  onDoubleClick={() => onChange(entry.path)}
                  className="flex w-full items-center gap-2 rounded-sm px-2 py-1.5 text-left text-sm text-ink-2 transition hover:bg-sunken hover:text-ink"
                >
                  <FolderIcon className="size-4 shrink-0 opacity-70" />
                  <span className="truncate">{entry.name}</span>
                </button>
              </li>
            ))
          )}
        </ul>
      </div>
      <PathField value={value} onChange={onChange} />
    </div>
  );
}

function PathField({ value, onChange }: { value: string; onChange: (root: string) => void }) {
  return (
    <Field label="Repository path" hint="An absolute path on this machine. Read and indexed locally.">
      {(props) => (
        <Input
          {...props}
          value={value}
          onChange={(event) => onChange(event.target.value)}
          className="font-mono text-[13px]"
          placeholder="/absolute/path/to/repository"
          autoComplete="off"
          spellCheck={false}
        />
      )}
    </Field>
  );
}

/**
 * How long to wait after the last keystroke before asking the remote what it has.
 *
 * `ls-remote` is a network round trip to somebody else's server, so this cannot run per
 * keystroke — and a half-typed address is a request that was always going to fail. Long
 * enough that pasting an address asks once; short enough that it feels like it answered by
 * itself rather than after a pause worth noticing.
 */
const BRANCH_PROBE_DELAY_MS = 600;

/** The option that swaps the chooser back to a text field. Not a branch name anyone has. */
const NAME_IT_MYSELF = "\u0000name-it-myself";

/** Enough of an address to be worth asking about, without being a URL parser. */
const LOOKS_LIKE_AN_ADDRESS = /^(?:https?:\/\/|git@|ssh:\/\/|git:\/\/).+[^/]$/;

function CloneForm({ onCheckedOut }: { onCheckedOut: (root: string) => void }) {
  const client = useQueryClient();
  const [url, setUrl] = useState("");
  const [branch, setBranch] = useState("");
  const [naming, setNaming] = useState(false);

  // The address the branch list belongs to, which trails what is in the field.
  const [probed, setProbed] = useState("");
  useEffect(() => {
    const candidate = url.trim();
    if (!LOOKS_LIKE_AN_ADDRESS.test(candidate)) {
      setProbed("");
      return;
    }
    const timer = setTimeout(() => setProbed(candidate), BRANCH_PROBE_DELAY_MS);
    return () => clearTimeout(timer);
  }, [url]);

  const remoteBranches = useQuery({
    queryKey: ["remote-branches", probed],
    queryFn: () => api.remoteBranches(probed),
    enabled: Boolean(probed),
    // The answer is a property of somebody else's server and does not change while a form is
    // being filled in; refetching on every focus would be a network call for nothing.
    staleTime: 5 * 60 * 1000,
    retry: false,
  });

  const offered = remoteBranches.data ?? [];
  // A branch is chosen from the list wherever there is one to choose from. Typing is the
  // fallback, not the default — but it stays reachable, because "no list" and "no such
  // branch" are different facts and only the first of them is what an empty answer means.
  const choosing = offered.length > 0 && !naming;

  // A branch that is no longer in the list it was chosen from is a stale answer, and leaving
  // it selected would clone the wrong thing quietly.
  useEffect(() => {
    if (offered.length && branch && !offered.includes(branch)) setBranch("");
  }, [offered, branch]);
  const checkout = useMutation({
    mutationFn: () => api.checkoutRepository(url.trim(), branch.trim() || null),
    onSuccess: async (result) => {
      onCheckedOut(result.root_path);
      await client.invalidateQueries({ queryKey: ["repositories"] });
    },
  });

  return (
    <div className="grid gap-3">
      <div className="grid gap-3 sm:grid-cols-[minmax(0,1fr)_180px_auto] sm:items-end">
        <Field label="Repository address">
          {(props) => (
            <Input
              {...props}
              value={url}
              onChange={(event) => setUrl(event.target.value)}
              placeholder="https://github.com/org/repository"
              autoComplete="off"
            />
          )}
        </Field>
        <Field
          label="Branch"
          hint={
            remoteBranches.isFetching
              ? "Reading the remote…"
              : choosing
                ? `${offered.length} on this remote`
                : "Optional"
          }
        >
          {(props) =>
            choosing ? (
              <Select
                {...props}
                value={branch}
                onChange={(event) => {
                  if (event.target.value === NAME_IT_MYSELF) {
                    setNaming(true);
                    setBranch("");
                    return;
                  }
                  setBranch(event.target.value);
                }}
              >
                <option value="">The remote's default</option>
                {offered.map((name) => (
                  <option key={name} value={name}>
                    {name}
                  </option>
                ))}
                <option value={NAME_IT_MYSELF}>Name one myself…</option>
              </Select>
            ) : (
              <Input
                {...props}
                value={branch}
                onChange={(event) => setBranch(event.target.value)}
                placeholder="The remote's default"
                autoComplete="off"
              />
            )
          }
        </Field>
        <Button
          variant="secondary"
          disabled={!url.trim() || checkout.isPending}
          onClick={() => checkout.mutate()}
        >
          {checkout.isPending ? <Spinner /> : "Clone"}
        </Button>
      </div>
      {checkout.data ? (
        <p className="flex min-w-0 items-center gap-1.5 text-xs text-ink-2">
          <CheckIcon className="size-3.5 shrink-0 text-ink" aria-hidden="true" />
          {checkout.data.created ? "Cloned to" : "Updated"}
          <Mono className="min-w-0 truncate text-[11px]">{checkout.data.root_path}</Mono>
        </p>
      ) : null}
      {checkout.error ? <ErrorNotice error={checkout.error} /> : null}
    </div>
  );
}

function ExampleList({ value, onChange }: { value: string; onChange: (root: string) => void }) {
  const examples = useQuery({ queryKey: ["examples"], queryFn: api.examples });
  const load = useMutation({
    mutationFn: async (name: string) => {
      const example = examples.data?.find((item) => item.name === name);
      if (!example) throw new Error("That example is no longer bundled");
      await api.loadExample(name);
      return example.repository_root;
    },
    onSuccess: (root) => onChange(root),
  });

  if (examples.isLoading) {
    return (
      <div className="flex items-center gap-2 py-4 text-sm text-ink-3">
        <Spinner /> Loading bundled examples…
      </div>
    );
  }
  if (!examples.data?.length) {
    return <EmptyState title="No bundled examples">This build ships no example repositories.</EmptyState>;
  }

  return (
    <div className="grid gap-1.5">
      {examples.data.map((example) => (
        <button
          key={example.name}
          type="button"
          onClick={() => load.mutate(example.name)}
          aria-pressed={value === example.repository_root}
          className={cn(
            "rounded-md border px-3 py-2.5 text-left transition",
            value === example.repository_root
              ? "border-ink bg-sunken"
              : "border-rule bg-surface hover:border-rule-strong",
          )}
        >
          <div className="flex items-center justify-between gap-2">
            <span className="text-sm font-semibold text-ink">{example.title}</span>
            <Tag>example</Tag>
          </div>
          <p className="mt-1 text-xs leading-5 text-ink-3">{example.description}</p>
        </button>
      ))}
      {load.error ? <ErrorNotice error={load.error} /> : null}
    </div>
  );
}
