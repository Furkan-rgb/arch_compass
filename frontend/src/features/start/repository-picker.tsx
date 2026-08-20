import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { api } from "../../api";
import { cn } from "../../lib/cn";
import { relativeTime, repositoryName } from "../../lib/format";
import { Tag } from "../../ui/badge";
import { Button } from "../../ui/button";
import { Field, Input } from "../../ui/field";
import { FolderIcon, GitBranchIcon } from "../../ui/icons";
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

  const hasRecent = Boolean(repositories.data?.length);

  return (
    <div>
      <Tabs
        label="Choose a repository"
        active={tab}
        onChange={setTab}
        variant="solid"
        items={[
          { id: "recent", label: "Indexed", count: repositories.data?.length },
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
              {repositories.data?.slice(0, 8).map((repository) => (
                <li key={repository.version_id}>
                  <button
                    type="button"
                    onClick={() => onChange(repository.root_path)}
                    aria-pressed={value === repository.root_path}
                    className={cn(
                      "w-full rounded-md border px-3 py-2.5 text-left transition",
                      value === repository.root_path
                        ? "border-accent bg-accent-soft"
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
            ↑ Up
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

function CloneForm({ onCheckedOut }: { onCheckedOut: (root: string) => void }) {
  const client = useQueryClient();
  const [url, setUrl] = useState("");
  const [branch, setBranch] = useState("");
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
        <Field label="Branch" hint="Optional">
          {(props) => (
            <Input
              {...props}
              value={branch}
              onChange={(event) => setBranch(event.target.value)}
              placeholder="main"
              autoComplete="off"
            />
          )}
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
        <p className="text-xs text-cleared">
          {checkout.data.created ? "Cloned to " : "Updated "}
          <Mono className="text-cleared">{checkout.data.root_path}</Mono>
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
              ? "border-accent bg-accent-soft"
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
