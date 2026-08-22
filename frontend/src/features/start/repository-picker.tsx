import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";

import { api } from "../../api";
import { cn } from "../../lib/cn";
import { plural, relativeTime, repositoryName } from "../../lib/format";
import { Tag } from "../../ui/badge";
import { Button } from "../../ui/button";
import { Field, Input, Select } from "../../ui/field";
import { ArrowUp, CheckIcon, FolderIcon, GitBranchIcon } from "../../ui/icons";
import { Mono } from "../../ui/meta";
import { EmptyState, ErrorNotice, Spinner } from "../../ui/states";
import { Tabs, TabPanel } from "../../ui/tabs";
import { isAbsolutePath } from "./scope-picker";

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
  // Which tab the reader chose, and `null` for as long as they have not chosen one.
  const [chosen, setChosen] = useState<string | null>(null);
  const repositories = useQuery({ queryKey: ["repositories"], queryFn: api.repositories });
  const examples = useQuery({ queryKey: ["examples"], queryFn: api.examples });

  const indexed = repositories.data ?? [];
  const hasRecent = Boolean(indexed.length);
  const bundled = examples.data?.length ?? 0;

  /**
   * A workspace with nothing in it opens on the examples rather than on an empty list.
   *
   * `Indexed` is the right first tab for anybody who has indexed something and the wrong one
   * for everybody else: on a first run it is a sentence with no buttons under it, while five
   * ready-made repositories — the shortest route in this product to a real finding — sit
   * unmentioned on the fourth tab. Derived rather than decided once at mount, because at
   * mount nothing has answered yet and a default chosen then would be a guess.
   */
  const tab = chosen ?? (repositories.isSuccess && !hasRecent && bundled ? "example" : "recent");

  return (
    <div>
      <Tabs
        label="Choose a repository"
        active={tab}
        onChange={setChosen}
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
              <Spinner label="" /> Loading indexed repositories…
            </div>
          ) : !hasRecent ? (
            // An empty state that names no way out is a dead end, and this is the first
            // thing a new workspace shows anybody. Both buttons go somewhere real, and the
            // bundled examples lead because they are the fastest route to a finding.
            <EmptyState
              title="Nothing indexed yet"
              className="py-8"
              action={
                <>
                  {bundled ? (
                    <Button onClick={() => setChosen("example")}>Open an example</Button>
                  ) : null}
                  <Button variant="secondary" onClick={() => setChosen("browse")}>
                    Browse this machine
                  </Button>
                </>
              }
            >
              {bundled
                ? `${plural(bundled, "example repository", "example repositories")} ship with ArchCompass and index in seconds. Or point it at a folder on this machine.`
                : "Browse for a folder on this machine, or clone a repository by address."}
            </EmptyState>
          ) : (
            <ul className="grid gap-1.5 sm:grid-cols-2">
              {indexed.slice(0, 8).map((repository) => (
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
                      {/* Said rather than hidden. A repository indexed eight times is one
                          choice here — the listing groups it — and the count is the only
                          thing left that says the workspace holds a history of it. */}
                      {(repository.snapshot_count ?? 1) > 1 ? (
                        <span
                          title={`${repository.snapshot_count} atlas versions of this checkout`}
                        >
                          · {repository.snapshot_count} indexes
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
        <ErrorNotice
          error={listing.error}
          title="Browsing is unavailable"
          action={
            <Button variant="secondary" size="sm" onClick={() => void listing.refetch()}>
              Try again
            </Button>
          }
        />
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
              <Spinner label="" /> Reading…
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

/**
 * How long to wait after the last keystroke before a typed path becomes the chosen one.
 *
 * The same reasoning as `BRANCH_PROBE_DELAY_MS` below, against a cost that is worse than one
 * network round trip. Choosing a path re-keys the repository tree, and that route walks the
 * folder with `rglob("*")` and a `stat()` per file — so every prefix that happened to be a
 * real directory was walked in full as somebody typed, `/Users/me` included, on the way to
 * anything underneath it. Long enough that a pasted path asks once; short enough that it
 * feels like the page answered by itself rather than after a pause worth noticing.
 */
const PATH_COMMIT_DELAY_MS = 600;

/**
 * The path being typed is not the path being reviewed until somebody stops typing.
 *
 * `value` is the choice and the draft is the text, and they are deliberately two things:
 * choosing re-keys the tree query and drops every folder left out of the last choice, which
 * is not something a keystroke may do. The draft becomes the choice when the reader leaves
 * the field, presses Enter, or stops for `PATH_COMMIT_DELAY_MS` — and the last of those only
 * where the text is already an absolute path, because nothing shorter can be read anyway.
 */
function PathField({ value, onChange }: { value: string; onChange: (root: string) => void }) {
  const [draft, setDraft] = useState(value);

  // A repository chosen anywhere else — the browser above this field, another tab of the
  // picker, an arrival with `?root=` — has to appear in the box, or the box contradicts the
  // page it is on.
  useEffect(() => setDraft(value), [value]);

  // Held in a ref for the reason `useFocusTrap` holds `onClose` in one: every call site
  // passes a fresh arrow, so a dependency on it would restart the wait on every render the
  // page happens to do — and this page polls what is already running.
  const commit = useRef(onChange);
  useEffect(() => {
    commit.current = onChange;
  });

  function settle(text: string) {
    const typed = text.trim();
    if (typed !== value) commit.current(typed);
  }

  useEffect(() => {
    const typed = draft.trim();
    if (typed === value || !isAbsolutePath(typed)) return;
    const timer = setTimeout(() => commit.current(typed), PATH_COMMIT_DELAY_MS);
    return () => clearTimeout(timer);
  }, [draft, value]);

  return (
    <Field label="Repository path" hint="An absolute path on this machine. Read and indexed locally.">
      {(props) => (
        <Input
          {...props}
          value={draft}
          onChange={(event) => setDraft(event.target.value)}
          onBlur={(event) => settle(event.target.value)}
          onKeyDown={(event) => {
            if (event.key !== "Enter") return;
            event.preventDefault();
            settle(draft);
          }}
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

/**
 * Enough of an address to be worth asking about, without being a URL parser.
 *
 * The scheme is optional, because `github.com/org/repo` is what most people paste — and
 * requiring one meant that address quietly sent no request at all, leaving the Branch hint on
 * its default, which looks exactly like a remote that answered with nothing. Three different
 * facts rendered as one blank.
 */
const LOOKS_LIKE_AN_ADDRESS = /^(?:(?:https?|ssh|git):\/\/|git@|[\w-]+(?:\.[\w-]+)+[/:])\S*[^/\s]$/;

/**
 * `github.com/org/repo` is a host and a path with the scheme left off, and `git` cannot read
 * it. So it is completed here rather than refused.
 *
 * Anything that already says how to reach the remote is passed through exactly as typed —
 * `git@host:org/repo` most of all, which is scp syntax rather than a URL and must not be
 * given a scheme it would then have to carry into the clone.
 */
function addressOf(text: string): string {
  const trimmed = text.trim();
  return /^(?:https?|ssh|git):\/\//.test(trimmed) || trimmed.startsWith("git@")
    ? trimmed
    : `https://${trimmed}`;
}

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
    const timer = setTimeout(() => setProbed(addressOf(candidate)), BRANCH_PROBE_DELAY_MS);
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
    mutationFn: () => api.checkoutRepository(addressOf(url), branch.trim() || null),
    onSuccess: async (result) => {
      onCheckedOut(result.root_path);
      await client.invalidateQueries({ queryKey: ["repositories"] });
    },
  });

  /**
   * What the remote said, said back. Four different facts used to render as the same blank.
   *
   * An empty list is a real answer and not a failure — the route's own docstring says so —
   * but "the remote published no list", "this is not an address yet" and "the request did not
   * get through" are three different things to know, and only one of them is about the
   * address being wrong. The field stays fillable in every one of them, because being unable
   * to list the branches says nothing about whether the branch the reader has in mind exists.
   */
  const answered = Boolean(probed) && !remoteBranches.isFetching;
  const branchHint = !url.trim()
    ? "Optional"
    : !probed
      ? "Not an address yet"
      : remoteBranches.isFetching
        ? "Reading the remote…"
        : remoteBranches.isError
          ? "The remote would not answer"
          : offered.length
            ? `${offered.length} on this remote`
            : "The remote published no list";

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
        <Field label="Branch" hint={branchHint}>
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
      {answered && remoteBranches.isError ? (
        <p className="text-xs leading-5 text-ink-3">
          The workspace could not read{" "}
          <Mono className="text-[11px] wrap-anywhere">{probed}</Mono> —{" "}
          {remoteBranches.error instanceof Error
            ? remoteBranches.error.message
            : String(remoteBranches.error)}{" "}
          Clone it anyway if the address is right; name a branch if you know one.
        </p>
      ) : answered && !offered.length ? (
        <p className="text-xs leading-5 text-ink-3">
          <Mono className="text-[11px] wrap-anywhere">{probed}</Mono> published no branch list.
          A private remote, a wrong address and a deployment with no git all look like this,
          so the clone is still worth trying — name a branch if you know one, or leave it on
          the remote's default.
        </p>
      ) : null}
      {checkout.data ? (
        <p className="flex min-w-0 items-center gap-1.5 text-xs text-ink-2">
          <CheckIcon className="size-3.5 shrink-0 text-ink" aria-hidden="true" />
          {checkout.data.created ? "Cloned to" : "Updated"}
          <Mono className="min-w-0 truncate text-[11px]">{checkout.data.root_path}</Mono>
        </p>
      ) : null}
      {checkout.error ? (
        <ErrorNotice
          error={checkout.error}
          action={
            <Button variant="secondary" size="sm" onClick={() => checkout.mutate()}>
              Try again
            </Button>
          }
        />
      ) : null}
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

  // Which one is being indexed. Loading an example is a server-side index that takes seconds,
  // and none of that reached the screen: no spinner, no disabled state, and `aria-pressed`
  // that only ever reflected the finished choice. The reasonable reading of a click that
  // shows nothing is that it did nothing, so people clicked a second example and the two
  // loads raced. Every neighbouring path in this file already answers a pending mutation.
  const loading = load.isPending ? load.variables : null;

  if (examples.isLoading) {
    return (
      <div className="flex items-center gap-2 py-4 text-sm text-ink-3">
        <Spinner label="" /> Loading bundled examples…
      </div>
    );
  }
  if (!examples.data?.length) {
    return <EmptyState title="No bundled examples">This build ships no example repositories.</EmptyState>;
  }

  return (
    <div className="grid gap-1.5">
      {examples.data.map((example) => {
        const pressed = loading === example.name || value === example.repository_root;
        return (
          <button
            key={example.name}
            type="button"
            onClick={() => load.mutate(example.name)}
            disabled={load.isPending}
            aria-pressed={pressed}
            className={cn(
              "rounded-md border px-3 py-2.5 text-left transition",
              pressed
                ? "border-ink bg-sunken"
                : "border-rule bg-surface hover:border-rule-strong",
              // The others stop offering while one is being indexed; the one being indexed
              // stays at full strength, because it is the one saying what is happening.
              load.isPending && loading !== example.name && "opacity-50",
            )}
          >
            <div className="flex items-center justify-between gap-2">
              <span className="text-sm font-semibold text-ink">{example.title}</span>
              {loading === example.name ? (
                <span className="inline-flex shrink-0 items-center gap-1.5 text-[11px] text-ink-3">
                  <Spinner label="" /> indexing…
                </span>
              ) : (
                <Tag>example</Tag>
              )}
            </div>
            <p className="mt-1 text-xs leading-5 text-ink-3">{example.description}</p>
          </button>
        );
      })}
      {load.error ? (
        <ErrorNotice
          error={load.error}
          action={
            load.variables ? (
              <Button
                variant="secondary"
                size="sm"
                onClick={() => load.mutate(load.variables as string)}
              >
                Try again
              </Button>
            ) : undefined
          }
        />
      ) : null}
    </div>
  );
}
